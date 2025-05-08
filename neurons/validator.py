import asyncio
import copy
import gc
import math
import os
import random
import time
import traceback
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator, Dict, List, TypeAlias

import aiohttp
import bittensor as bt
import numpy as np
import torch
from loguru import logger
from torch.nn import functional as F

import dojo
from commons.dataset.synthetic import SyntheticAPI
from commons.exceptions import (
    EmptyScores,
    FatalSyntheticGenerationError,
    InvalidMinerResponse,
    NoNewExpiredTasksYet,
    SetWeightsFailed,
    SyntheticGenerationError,
)
from commons.obfuscation.obfuscation_utils import obfuscate_html_and_js
from commons.objects import ObjectManager
from commons.orm import ORM
from commons.score_storage import ScoreStorage
from commons.scoring import Scoring
from commons.utils import (
    _terminal_plot,
    aget_effective_stake,
    aobject,
    datetime_as_utc,
    get_epoch_time,
    get_new_uuid,
    set_expire_time,
)
from dojo import get_spec_version
from dojo.kami import Kami, SetWeightsPayload, SubnetMetagraph
from dojo.protocol import (
    CompletionResponse,
    CriteriaType,
    CriteriaTypeEnum,
    DendriteQueryResponse,
    Heartbeat,
    ScoreCriteria,
    ScoringResult,
    SyntheticQA,
    TaskResult,
    TaskResultRequest,
    TaskSynapseObject,
    TaskTypeEnum,
)
from dojo.utils.config import get_config
from dojo.utils.uids import is_miner
from dojo.utils.weight_utils import (
    aprocess_weights_for_netuid,
    convert_weights_and_uids_for_emit,
)
from entrypoints.analytics_upload import run_analytics_upload

ObfuscatedModelMap: TypeAlias = Dict[str, str]
SyntheticMetadata: TypeAlias = dict[str, str]


# TODO: re-enable before release
# latest_local = get_latest_git_tag()
# latest_remote = get_latest_remote_tag()
# if (
#     latest_local
#     and latest_remote
#     and latest_local.strip("v") != latest_remote.strip("v")
# ):
#     logger.warning("Your repository is not up to date, and may fail to set weights.")
#     logger.warning(
#         f"latest local version: {latest_local}\nlatest remote version: {latest_remote}"
#     )


class Validator(aobject):
    _scores_alock = asyncio.Lock()
    _uids_alock = asyncio.Lock()
    _request_alock = asyncio.Lock()
    _threshold = 0.1
    _active_miner_uids: set[int] = set()
    _forward_semaphore = asyncio.Semaphore(16)  # Limit to 16 concurrent forward calls

    subtensor: bt.subtensor
    wallet: bt.wallet  # type: ignore
    metagraph: SubnetMetagraph
    spec_version: int = get_spec_version()
    kami: Kami

    async def __init__(self):
        self.MAX_BLOCK_CHECK_ATTEMPTS = 3
        self.QUALITY_WEIGHT = 0.8
        self._last_block = None
        self._block_check_attempts = 0
        self._connection_lock = asyncio.Lock()

        self.kami = Kami()

        self.loop = asyncio.get_event_loop()
        self.config = ObjectManager.get_config()

        logger.info(self.config)

        logger.info("Setting up bittensor objects....")
        # The wallet holds the cryptographic key pairs for the miner.
        self.wallet = bt.wallet(config=self.config)
        logger.info(f"Wallet: {self.wallet}")
        self.metagraph = await self.kami.get_metagraph(self.config.netuid)
        logger.info(f"Metagraph Loaded: {self.metagraph}")

        # Save validator hotkey
        self.vali_hotkey: str = self.wallet.hotkey.ss58_address

        # Each miner gets a unique identity (UID) in the network for differentiation.
        self.uid = self.metagraph.hotkeys.index(self.vali_hotkey)
        logger.info(
            f"Running neuron on subnet: {self.config.netuid} with uid {self.uid}"
        )

        self.step = 0
        self.last_anal_upload_time: datetime | None = None
        # Dendrite lets us send messages to other nodes (axons) in the network.
        self.dendrite = bt.dendrite(wallet=self.wallet)
        logger.info(f"Dendrite: {self.dendrite}")
        # Set up initial scoring weights for validation
        self.scores: torch.Tensor = torch.zeros(
            len(self.metagraph.hotkeys), dtype=torch.float32
        )

        await self.check_registered()

        # Run score migration before loading state
        migration_success = await ScoreStorage.migrate_from_db()
        if not migration_success:
            logger.error(
                "Score migration failed - cannot continue without valid scores"
            )
            raise RuntimeError("Score migration failed - validator cannot start")

        await self.load_state()

    async def send_scores(self, synapse: ScoringResult, hotkeys: List[str]):
        """Send consensus score back to miners who participated in the request."""
        miners_uids = await self.get_active_miner_uids()
        metagraph_axons = await self._retrieve_axons(miners_uids)
        axons = [axon for axon in metagraph_axons if axon.hotkey in hotkeys]
        if not axons:
            logger.warning("No axons to send consensus to... skipping")
        else:
            logger.info(f"Sending back scores to miners for task id: {synapse.task_id}")

        await self._semaphore_limited_forward(self.dendrite, axons, synapse, timeout=30)

    def obfuscate_model_names(
        self, completion_responses: list[CompletionResponse]
    ) -> dict[str, str]:
        """Obfuscate model names for both external requests and synthetic requests to prevent miners from knowing the true model names."""
        obfuscated_model_to_model: dict[str, str] = {}
        for completion in completion_responses:
            if completion.completion_id is None:
                raise ValueError("completion_id is None")
            original_model = completion.model
            completion.model = completion.completion_id
            obfuscated_model_to_model[completion.completion_id] = original_model
        return obfuscated_model_to_model

    @staticmethod
    async def _obfuscate_completion_files(
        completion_responses: List[CompletionResponse],
    ):
        """Obfuscate HTML files in each completion response."""
        for completion in completion_responses:
            if hasattr(completion.completion, "files"):
                for file in completion.completion.files:
                    if file.filename.lower().endswith(".html"):
                        try:
                            original_size = len(file.content)
                            logger.debug(
                                f"Original size of {file.filename}: {original_size} bytes"
                            )
                            file.content = await obfuscate_html_and_js(file.content)
                            obfuscated_size = len(file.content)
                            logger.debug(
                                f"Obfuscated size of {file.filename}: {obfuscated_size} bytes"
                            )
                        except Exception as e:
                            logger.error(f"Error obfuscating {file.filename}: {e}")

    async def get_active_miner_uids(self):
        async with self._uids_alock:
            return sorted(list(self._active_miner_uids))

    async def set_weights(self):
        """
        Sets the validator weights to the metagraph hotkeys based on the scores it has received from the miners.
        The weights determine the trust and incentive level the validator assigns to miner nodes on the network.
        """

        # ensure self.scores not being written to by other coroutines
        # Check if self.scores contains any NaN values and log a warning if it does.
        if torch.isnan(self.scores).any():
            logger.warning(
                "Scores contain NaN values. This may be due to a lack of responses from miners, or a bug in your reward functions."
            )

        logger.info("Attempting to set weights")

        # ensure sum = 1
        normalized_weights = F.normalize(self.scores.cpu(), p=1, dim=0)

        safe_normalized_weights = normalized_weights
        if isinstance(normalized_weights, np.ndarray):
            safe_normalized_weights = torch.from_numpy(normalized_weights).to("cpu")
        elif isinstance(normalized_weights, torch.Tensor):
            pass

        # we don't read uids from metagraph because polling metagraph happens
        # faster than calling set_weights and self.scores is already
        # based on uids, adjusted based on metagraph during `resync_metagraph`
        uids = torch.tensor(list(range(len(safe_normalized_weights))))

        (
            final_uids,
            final_weights,
        ) = await aprocess_weights_for_netuid(  # type: ignore
            uids=uids.numpy(),
            weights=safe_normalized_weights.numpy(),
            netuid=self.config.netuid,  # type: ignore
            kami=self.kami,
            metagraph=self.metagraph,
        )

        if isinstance(final_weights, np.ndarray):
            final_weights = torch.from_numpy(final_weights).to("cpu")
        if isinstance(final_uids, np.ndarray):
            final_uids = torch.from_numpy(final_uids).to("cpu")

        logger.info(f"weights:\n{safe_normalized_weights}")
        logger.info(f"uids:\n{uids}")

        _terminal_plot(
            f"pre-processed weights, block: {self.block}",
            safe_normalized_weights.numpy(),
        )

        logger.info(f"final weights:\n{final_weights}")
        logger.info(f"final uids:\n{final_uids}")

        _terminal_plot(
            f"final weights, block: {self.block}",
            final_weights.numpy(),
        )

        # dependent on underlying `set_weights` call
        try:
            result = await asyncio.wait_for(
                self._set_weights(final_uids, final_weights), timeout=90
            )
            if not result:
                logger.error(f"Failed to set weights: {result}")
                return
            if result.get("statusCode", None) == 200:
                logger.success(
                    f"Set weights successfully with hash {result.get('data')}"
                )
        except asyncio.TimeoutError:
            logger.error("Setting weights timed out after 90 seconds")
            return

        return

    async def _set_weights(self, uids: torch.Tensor, weights: torch.Tensor):
        """Wrapper function to set weights so we can ensure set weights happens
        within a timeout.

        Args:
            uids (torch.Tensor): uids to set weights for
            weights (torch.Tensor): weights to set

        Returns:
            tuple[bool, str]: Returns the result of _set_weights function
        """

        max_attempts = 5
        attempt = 0
        result = False
        while attempt < max_attempts and (
            not result or result.get("statusCode", None) != 200
        ):
            message: str = ""
            try:
                logger.info(
                    f"Set weights attempt {attempt + 1}/{max_attempts} at block: {self.block},time: {time.time()}"
                )

                # Disable this for now to check validator hanging issue
                # try:
                #     await asyncio.wait_for(
                #         self._ensure_subtensor_ws_connected(), timeout=10
                #     )
                # except asyncio.TimeoutError:
                #     pass

                logger.info(f"Converting weights and uids for emit: {uids}, {weights}")

                uids, weights = convert_weights_and_uids_for_emit(
                    uids=uids,
                    weights=weights,
                )

                payload = SetWeightsPayload(
                    netuid=self.config.netuid,  # type: ignore
                    dests=uids,
                    weights=weights,
                    version_key=self.spec_version,
                )

                result = await self.kami.set_weights(payload)
                if result.get("statusCode", None) == 200:
                    logger.success(f"Set weights successfully: {result.get('data')}")
                    return result

                raise SetWeightsFailed(f"Failed to set weights with message:{message}")

            except Exception as e:
                logger.warning(
                    f"Failed to set weights with attempt {attempt + 1}/{max_attempts} due to: {e}"
                )

                if attempt == max_attempts:
                    logger.error("Max attempts reached. Could not set weights.")
                    return {"success": False, "data": "Max attempts reached"}

                await asyncio.sleep(12)
            finally:
                attempt += 1

        return {"success": False, "data": "Max attempts reached"}

    async def resync_metagraph(self):
        """Resyncs the metagraph and updates the hotkeys and moving averages based on the new metagraph."""
        # Copies state of metagraph before syncing.
        previous_metagraph = copy.deepcopy(self.metagraph)
        previous_axons = previous_metagraph.axons
        previous_hotkeys = previous_metagraph.hotkeys

        # Sync the metagraph.
        self.metagraph = await self.kami.get_metagraph(self.config.netuid)
        current_axons = self.metagraph.axons
        current_hotkeys = self.metagraph.hotkeys

        # Check if the metagraph axon info has changed.
        if previous_axons == current_axons:
            return

        logger.info(
            "Metagraph updated, re-syncing hotkeys, dendrite pool and moving averages"
        )

        # Zero out all hotkeys that have been replaced.

        for uid, hotkey in enumerate(previous_hotkeys):
            if hotkey != current_hotkeys[uid]:
                self.scores[uid] = 0  # hotkey has been replaced

        # Check to see if the metagraph has changed size.
        # If so, we need to add new hotkeys and moving averages.
        if len(previous_hotkeys) < len(current_hotkeys):
            # Update the size of the moving average scores.
            new_moving_average = torch.zeros(len(current_hotkeys))
            min_len = min(len(previous_hotkeys), len(self.scores))
            new_moving_average[:min_len] = self.scores[:min_len]
            async with self._scores_alock:
                self.scores = torch.clamp(new_moving_average, min=0.0)

    async def update_scores(self, hotkey_to_scores: dict[str, float]):
        """Performs exponential moving average on the scores based on the rewards received from the miners,
        after setting the self.scores variable here, `set_weights` will be called to set the weights on chain.
        """
        if not hotkey_to_scores:
            logger.warning("hotkey_to_scores is empty, skipping score update")
            return

        nan_value_indices = np.isnan(list(hotkey_to_scores.values()))
        if nan_value_indices.any():
            logger.warning(f"NaN values detected in rewards: {hotkey_to_scores}")
            return

        # Compute forward pass rewards, assumes uids are mutually exclusive.
        # scores dimensions might have been updated after resyncing... len(uids) != len(self.scores)
        rewards = torch.zeros((len(self.metagraph.hotkeys),))
        existing_scores = torch.zeros((len(self.metagraph.hotkeys),))
        for index, (key, value) in enumerate(hotkey_to_scores.items()):
            # handle nan values
            if nan_value_indices[index]:
                rewards[key] = 0.0  # type: ignore
            # search metagraph for hotkey and grab uid
            try:
                uid = self.metagraph.hotkeys.index(key)
            except ValueError:
                logger.warning("Old hotkey found from previous metagraph")
                continue

            logger.info(f"Score for hotkey {key} is {value}")
            rewards[uid] = value

            # self.scores is a tensor already based on uids
            # use this logic to ensure
            # 1. rewards and existing_scores are the same length
            # 2. if hotkey is deregistered, the new participant will not benefit from existing scores
            if uid < len(self.scores):
                existing_scores[uid] = self.scores[uid]

        logger.info(f"Rewards: {rewards}")
        # Update scores with rewards produced by this step.
        # shape: [ metagraph.n ]
        alpha: float = self.config.neuron.moving_average_alpha
        # don't acquire lock here because we're already acquiring it in the CALLER
        async with self._scores_alock:
            _terminal_plot(
                f"scores before update, block: {self.block}", self.scores.numpy()
            )
            assert (
                existing_scores.shape == rewards.shape
            ), "Scores and rewards must be the same length when calculating moving average"

            self.scores = alpha * rewards + (1 - alpha) * existing_scores
            self.scores = torch.clamp(self.scores, min=0.0)
            _terminal_plot(
                f"scores after update, block: {self.block}", self.scores.numpy()
            )
        logger.info(f"Updated scores: {self.scores}")

    async def save_state(
        self,
    ):
        """Saves the state of the validator to the database."""
        if self.step == 0:
            return

        try:
            if np.count_nonzero(self.scores) == 0:
                logger.warning("Scores are all zeros, but saving anyway!")

            await ScoreStorage.save(self.scores)
            logger.success(f"📦 Saved validator state with scores: {self.scores}")
        except EmptyScores as e:
            logger.info(f"No need to to save validator state: {e}")
        except Exception as e:
            logger.error(f"Failed to save validator state: {e}")

    async def _load_state(self):
        try:
            scores = await ScoreStorage.load()

            if scores is None:
                num_processed_tasks = await ORM.get_num_processed_tasks()
                if num_processed_tasks > 0:
                    logger.error(
                        "Score record not found, but you have processed tasks."
                    )
                else:
                    logger.warning(
                        "Score record not found, and no tasks processed, this is okay if you're running for the first time."
                    )
                return None

            logger.success(f"Loaded validator state: {scores=}")
            async with self._scores_alock:
                # if metagraph has more hotkeys than scores, adjust length
                if len(scores) < len(self.metagraph.hotkeys):
                    logger.warning(
                        "Scores state is less than current metagraph hotkeys length, adjusting length. This should only happen when subnet is not at max UIDs yet."
                    )
                    # length adjusted scores
                    adjusted_scores = torch.zeros(len(self.metagraph.hotkeys))
                    adjusted_scores[: len(scores)] = scores
                    logger.info(
                        f"Load state: adjusted scores shape from {scores.shape} to {adjusted_scores.shape}"
                    )
                    self.scores = torch.clamp(adjusted_scores, 0.0)
                else:
                    self.scores = torch.clamp(scores, 0.0)

                _terminal_plot(
                    f"scores on load, block: {self.block}", self.scores.numpy()
                )

        except Exception as e:
            logger.error(
                f"Unexpected error occurred while loading validator state: {e}"
            )
            return None

    async def load_state(self):
        """Loads the state of the validator from a file."""
        try:
            await self._load_state()
        except Exception as e:
            logger.error(f"Failed to load validator state: {e}")
            pass

    async def should_sync_metagraph(self):
        """
        Check if enough epoch blocks have elapsed since the last checkpoint to sync.
        """
        return (
            self.block - self.metagraph.lastUpdate[self.uid]
        ) > self.config.neuron.epoch_length

    def should_set_weights(self) -> bool:
        # Don't set weights on initialization.
        if self.step == 0:
            return False

        # Define appropriate logic for when set weights.
        return (
            self.block - self.metagraph.lastUpdate[self.uid]
        ) > self.config.neuron.epoch_length

    async def sync(self):
        await self.check_registered()

        if await self.should_sync_metagraph():
            await self.resync_metagraph()

        if self.should_set_weights():
            await self.set_weights()

        await self.save_state()

    @property
    def block(self):
        return self._last_block

    async def _try_reconnect_subtensor(self):
        self._block_check_attempts += 1
        if self._block_check_attempts >= self.MAX_BLOCK_CHECK_ATTEMPTS:
            logger.error(
                f"Failed to reconnect after {self.MAX_BLOCK_CHECK_ATTEMPTS} attempts"
            )
            return False

        try:
            logger.info(
                f"Attempting to reconnect to subtensor (attempt {self._block_check_attempts}/{self.MAX_BLOCK_CHECK_ATTEMPTS})..."
            )

            self.subtensor = bt.subtensor(config=self.subtensor.config)
            await asyncio.sleep(1)
            return True
        except Exception as e:
            logger.error(f"Failed to reconnect to subtensor: {e}")
            return await self._try_reconnect_subtensor()

    # ---------------------------------------------------------------------------- #
    #                         VALIDATOR CORE FUNCTIONS                             #
    # ---------------------------------------------------------------------------- #
    async def log_validator_status(self):
        """
        Periodically logs the status of the validator, including the current block and time.
        This function runs in a loop until the validator is signaled to exit.
        """
        while True:
            logger.info(
                f"Validator running... block:{str(self.block)} time: {time.time()}"
            )
            await asyncio.sleep(dojo.VALIDATOR_STATUS)

    async def send_heartbeats(self):
        """Perform a health check periodically to ensure and check which miners are reachable"""
        while True:
            await asyncio.sleep(dojo.VALIDATOR_HEARTBEAT)
            try:
                axons = await self._retrieve_axons()
                logger.info(f"Sending heartbeats to {len(axons)} miners")

                # Send heartbeats in batches
                batch_size = 10
                active_hotkeys = set()

                for i in range(0, len(axons), batch_size):
                    batch = axons[i : i + batch_size]
                    responses: List[Heartbeat] = await self.dendrite.forward(
                        axons=batch, synapse=Heartbeat(), deserialize=False, timeout=12
                    )
                    # Process batch responses
                    active_hotkeys.update(
                        r.axon.hotkey for r in responses if r and r.ack and r.axon
                    )

                active_uids: set[int] = {
                    uid
                    for uid, axon in enumerate(self.metagraph.axons)
                    if self.metagraph.hotkeys[uid] in active_hotkeys
                }

                async with self._uids_alock:
                    self._active_miner_uids = active_uids

                logger.info(
                    f"⬇️ Heartbeats acknowledged by active miners: {sorted(active_uids)}"
                )
            except Exception as e:
                logger.error(f"Error in sending heartbeats: {e}", exc_info=True)

    async def run(self):
        logger.info(f"Validator starting at block: {str(self.block)}")

        # This loop maintains the validator's operations until intentionally stopped.
        while True:
            try:
                # Always clear the synapse history to avoid memory leak not just on success
                self.dendrite.synapse_history.clear()

                # Check if there are any active miners. If no active miners, skip the request generation.
                if not self._active_miner_uids:
                    logger.info(
                        f"No active miners to send request to... sleeping for {dojo.VALIDATOR_RUN} seconds"
                    )
                    await asyncio.sleep(dojo.VALIDATOR_RUN)
                    continue
                # Group related operations in a single async context
                async with self._request_alock:
                    (
                        synthetic_task,
                        ground_truth,
                        obfuscated_model_to_model,
                        synthetic_metadata,
                    ) = await self._generate_synthetic_request()

                    if synthetic_task:
                        await self.send_request(
                            synthetic_task,
                            ground_truth,
                            obfuscated_model_to_model,
                            synthetic_metadata,
                        )

                self.step += 1

                # Sync metagraph and potentially set weights.
                await self.sync()
                await asyncio.sleep(dojo.VALIDATOR_RUN)
            except KeyboardInterrupt:
                # Handle shutdown gracefully
                await self.cleanup()
                return
            except FatalSyntheticGenerationError:
                # if synthetic-API is unresponsive, shut down validator.
                logger.error("Synthetic API is unresponsive, shutting down validator")
                await self.cleanup()
                raise
            # In case of unforeseen errors, the validator will log the error and continue operations.
            except Exception as err:
                logger.error(f"Error during validation: {err}")
                logger.debug(traceback.format_exc())
                await asyncio.sleep(dojo.VALIDATOR_RUN)

        # Cleanup on exit
        await self.cleanup()

    async def update_tasks_polling(self):
        """
        Periodically updates task results for expired tasks every 15 minutes.
        Decoupled from scoring function to allow more frequent updates.
        """
        while True:
            await asyncio.sleep(dojo.VALIDATOR_UPDATE_TASK)  # 15 minutes
            try:
                # Grab tasks that were expired TASK_DEADLINE duration ago
                expire_from = datetime_as_utc(datetime.now(timezone.utc)) - timedelta(
                    hours=2
                )
                expire_to = datetime_as_utc(datetime.now(timezone.utc))
                logger.info(
                    f"Updating with expire_from: {expire_from} and expire_to: {expire_to}"
                )

                # Update task results before scoring
                await self.update_task_results(
                    expire_from=expire_from,
                    expire_to=expire_to,
                )

                logger.success("Polling task results completed")
            except Exception:
                logger.error("Error in updating task results")
                traceback.print_exc()
            finally:
                gc.collect()

    async def score_and_send_feedback(self):
        """
        Periodically scores tasks and sends feedback every hour.
        Uses a buffer period to ensure tasks have had sufficient update cycles.
        """
        while True:
            await asyncio.sleep(dojo.VALIDATOR_UPDATE_SCORE)  # 60 minutes
            # for each hotkey, a list of scores from all tasks being scored
            hotkey_to_all_scores = defaultdict(list)
            try:
                # Get tasks that expired between 2 hours ago and 30 minutes ago
                # This creates a 30-minute buffer to ensure tasks have been updated sufficiently
                now = datetime.now()
                expire_from = datetime_as_utc(now - timedelta(hours=2))
                expire_to = datetime_as_utc(now - timedelta(seconds=dojo.BUFFER_PERIOD))

                logger.info(
                    f"📝 performing scoring, context: {expire_from=}, {expire_to=}"
                )
                processed_request_ids = []

                batch_size = 10
                async for task_batch in self._get_task_batches(
                    batch_size, expire_from, expire_to
                ):
                    if not task_batch:
                        continue

                    for task in task_batch:
                        processed_id, hotkey_to_score = await self._score_task(task)
                        if processed_id:
                            processed_request_ids.append(processed_id)
                        for hotkey, score in hotkey_to_score.items():
                            hotkey_to_all_scores[hotkey].append(score)

                if processed_request_ids:
                    await ORM.mark_validator_task_as_processed(processed_request_ids)

                logger.success(
                    f"📝 All tasks processed, total tasks: {len(processed_request_ids)}"
                )

                # average scores across all tasks being scored by this trigger to update_scores
                # so miners moving average decay is lower
                # we incentivise both quality and quantity, but quality has higher weight than quantity
                final_hotkey_to_score = {
                    hotkey: sum(scores) / len(scores) * self.QUALITY_WEIGHT
                    + sum(scores)
                    / len(processed_request_ids)
                    * (1 - self.QUALITY_WEIGHT)
                    for hotkey, scores in hotkey_to_all_scores.items()
                    if scores
                }
                logger.info(
                    f"📝 Got hotkey to score across all tasks between expire_at from:{expire_from} and expire_at to:{expire_to}: {final_hotkey_to_score}"
                )
                await self.update_scores(hotkey_to_scores=final_hotkey_to_score)

                # upload scores to analytics API after updating.
                # record last successful upload time.
                self.last_anal_upload_time = await run_analytics_upload(
                    self._scores_alock, self.last_anal_upload_time, expire_to, self.kami
                )
            except Exception:
                logger.error("Error in score_and_send_feedback")
                traceback.print_exc()
            finally:
                gc.collect()

    async def update_task_results(
        self, expire_from: datetime, expire_to: datetime
    ) -> None:
        try:
            logger.info("Updating Dojo task completions...")
            batch_size: int = 10

            # filter_empty_result=True to avoid processing task's result that has already updated.
            async for task_batch in self._get_task_batches(
                batch_size, expire_from, expire_to, filter_empty_result=True
            ):
                if not task_batch:
                    continue

                # Process multiple tasks concurrently
                tasks = [self._update_task_results(task) for task in task_batch]
                miner_responses_lists = await asyncio.gather(*tasks)

                all_miner_responses = []
                for responses in miner_responses_lists:
                    if responses:
                        all_miner_responses.extend(responses)

                for i in range(0, len(all_miner_responses), batch_size):
                    batch = all_miner_responses[i : i + batch_size]
                    if batch:
                        await self._update_miner_raw_scores_batch(
                            batch[0].task_id,  # Use first response's task_id
                            batch,
                        )

        except NoNewExpiredTasksYet as e:
            logger.info(f"No new expired tasks yet: {e}")
        except Exception as e:
            logger.error(f"Error during Dojo task monitoring: {str(e)}")
            logger.debug(f"Traceback: {traceback.format_exc()}")

    # ---------------------------------------------------------------------------- #
    #                         VALIDATOR HELPER FUNCTIONS                           #
    # ---------------------------------------------------------------------------- #

    # Validator Setup Functions
    async def check_registered(self):
        is_registered = await self.kami.is_hotkey_registered(
            netuid=int(self.config.netuid),  # type: ignore
            hotkey=str(self.wallet.hotkey.ss58_address),
        )
        if not is_registered:
            logger.error(
                f"Wallet: {self.wallet} is not registered on netuid {self.config.netuid}."
                f" Please register the hotkey using `btcli s register` before trying again"
            )
            await self.cleanup()
            exit(1)

    # Validator Run helper functions
    async def cleanup(self):
        """Handle cleanup operations when shutting down"""
        logger.success("Validator axon stopped")
        await self.kami.close()

    async def _generate_synthetic_request(
        self,
    ) -> tuple[
        TaskSynapseObject | None,
        dict[str, int] | None,
        ObfuscatedModelMap,
        SyntheticMetadata,
    ]:
        """
        Generate a synthetic request for code generation tasks.

        Returns:
            tuple[TaskSynapseObject | None, dict[str, int] | ObfuscatedModelMap]: Tuple containing the generated task synapse object
            and ground truth, or None if generation fails
        """
        task_id = get_new_uuid()
        try:
            data: SyntheticQA | None = await SyntheticAPI.get_qa()
            if not data or not data.responses:
                logger.error("Invalid or empty data returned from synthetic data API")
                return None, None, {}, {}

            # Create criteria for each completion response
            criteria: List[CriteriaType] = [
                ScoreCriteria(
                    min=1.0,
                    max=100.0,
                )
            ]

            # Set criteria_types for each completion response
            for response in data.responses:
                response.criteria_types = criteria

            obfuscated_model_to_model = self.obfuscate_model_names(data.responses)
            synapse = TaskSynapseObject(
                task_id=task_id,
                prompt=data.prompt,
                task_type=str(TaskTypeEnum.CODE_GENERATION),
                expire_at=set_expire_time(dojo.TASK_DEADLINE),
                completion_responses=data.responses,
            )

            syn_api_metadata: SyntheticMetadata = data.metadata
            return (
                synapse,
                data.ground_truth,
                obfuscated_model_to_model,
                syn_api_metadata,
            )
        except (
            ValueError,
            aiohttp.ClientError,
            SyntheticGenerationError,
        ) as e:
            logger.error(
                f"Failed to generate synthetic request: {type(e).__name__}: {str(e)}"
            )
        except FatalSyntheticGenerationError as e:
            # propagate FatalSyntheticGenerationError upstream to trigger validator shutdown.
            logger.error("QA generation failed after all retry attempts")
            raise e
        except Exception as e:
            logger.error(f"Unexpected error during synthetic data generation: {e}")
            logger.debug(f"Traceback: {traceback.format_exc()}")

        return None, None, {}, {}

    async def send_request(
        self,
        synapse: TaskSynapseObject | None = None,
        ground_truth: dict[str, int] | None = None,
        obfuscated_model_to_model: ObfuscatedModelMap = {},
        synthetic_metadata: dict | None = None,
    ):
        if not synapse:
            logger.warning("No synapse provided... skipping")
            return

        if not self._active_miner_uids:
            logger.info("No active miners to send request to... skipping")
            return

        if not synapse.completion_responses:
            logger.warning("No completion responses to send... skipping")
            return

        start = get_epoch_time()
        sel_miner_uids = await self.get_active_miner_uids()

        axons = await self._retrieve_axons(sel_miner_uids)

        if not axons:
            logger.warning("🤷 No axons to query ... skipping")
            return

        logger.info(
            f"⬆️ Sending task request for task id: {synapse.task_id}, miners uids:{sel_miner_uids} with expire_at: {synapse.expire_at}"
        )

        miner_responses: List[TaskSynapseObject] = await self._send_shuffled_requests(
            self.dendrite, axons, synapse
        )
        valid_count = 0
        fails = []
        for response in miner_responses:
            try:
                status_code = response.dendrite.status_code
            except Exception:
                status_code = None
            try:
                logger.info(
                    f"Miner hotkey: {response.axon.hotkey}, dojo_task_id: {response.dojo_task_id}, status_code: {status_code}"
                )
                if response.dojo_task_id:
                    valid_count += 1
                else:
                    fails.append(
                        (response.axon.hotkey, status_code, response.dojo_task_id)
                    )
            except Exception as e:
                logger.error(f"Error logging miner response: {e}")
                logger.info("dendrite", response.dendrite)
                fails.append((response.axon.hotkey, status_code, response))
                continue

        logger.info(f"Fails: {fails}")
        logger.info(f"Valid miner responses: {valid_count}")
        valid_miner_responses: List[TaskSynapseObject] = []
        for response in miner_responses:
            try:
                if not response.dojo_task_id:
                    continue

                # map obfuscated model names back to the original model names
                real_model_ids = []
                if response.completion_responses:
                    for i, completion in enumerate(response.completion_responses):
                        found_model_id = obfuscated_model_to_model.get(
                            completion.model, None
                        )
                        real_model_ids.append(found_model_id)
                        if found_model_id:
                            response.completion_responses[i].model = found_model_id
                            synapse.completion_responses[i].model = found_model_id

                if any(c is None for c in real_model_ids):
                    logger.warning("Failed to map obfuscated model to original model")
                    continue

                response.miner_hotkey = response.axon.hotkey if response.axon else None
                # Get coldkey from metagraph using hotkey index
                if response.axon and response.axon.hotkey:
                    try:
                        hotkey_index = self.metagraph.hotkeys.index(
                            response.axon.hotkey
                        )
                        response.miner_coldkey = self.metagraph.coldkeys[hotkey_index]
                    except ValueError:
                        response.miner_coldkey = None
                else:
                    response.miner_coldkey = None
                valid_miner_responses.append(response)

            except Exception as e:
                logger.error(f"Error processing miner response: {e}")
                continue

        logger.info(f"⬇️ Received {len(valid_miner_responses)} valid responses")
        if not valid_miner_responses:
            logger.info("No valid miner responses to process... skipping")
            return

        # include the ground_truth to keep in data manager
        synapse.ground_truth = ground_truth
        synapse.dendrite.hotkey = self.vali_hotkey

        logger.info("Attempting to saving dendrite response")
        if not await ORM.save_task(
            validator_task=synapse,
            miner_responses=valid_miner_responses,
            ground_truth=ground_truth or {},
            metadata=synthetic_metadata or {},
        ):
            logger.error("Failed to save dendrite response")
            return

        logger.success(f"Saved dendrite response for task id: {synapse.task_id}")
        logger.info(
            f"Sending request to miners & processing took {get_epoch_time() - start}"
        )

        # clear axons
        axons.clear()

        return

    async def cleanup_resources(self):
        while True:
            if self.dendrite.synapse_history:
                self.dendrite.synapse_history.clear()
            await asyncio.sleep(300)

    @staticmethod
    async def _send_shuffled_requests(
        dendrite: bt.dendrite, axons: List[bt.AxonInfo], synapse: TaskSynapseObject
    ) -> list[TaskSynapseObject]:
        """
        Send shuffled requests to miners in batches for parallel processing.

        Args:
            dendrite: Dendrite instance for network communication
            axons: List of miner axons to send requests to
            synapse: Original task synapse object

        Returns:
            list[TaskSynapseObject]: Flattened list of all miner responses
        """
        all_responses = []
        batch_size = 10

        if not synapse.completion_responses:
            logger.warning("No completion responses to send... skipping")
            return all_responses

        for i in range(0, len(axons), batch_size):
            batch_axons = axons[i : i + batch_size]
            tasks = []

            for axon in batch_axons:
                # shuffle synapse Responses
                shuffled_completions = random.sample(
                    synapse.completion_responses,
                    k=len(synapse.completion_responses),
                )

                # Apply obfuscation to each completion's files
                # TODO re-nable obfuscation
                # await Validator._obfuscate_completion_files(shuffled_completions)

                shuffled_synapse = TaskSynapseObject(
                    epoch_timestamp=synapse.epoch_timestamp,
                    task_id=synapse.task_id,
                    prompt=synapse.prompt,
                    task_type=synapse.task_type,
                    expire_at=synapse.expire_at,
                    completion_responses=shuffled_completions,
                )

                tasks.append(
                    Validator._semaphore_limited_forward(
                        dendrite,
                        [axon],
                        shuffled_synapse,
                    )
                )

            # Gather results for this batch and flatten the list
            batch_responses = await asyncio.gather(*tasks)
            flat_batch_responses = [
                response for sublist in batch_responses for response in sublist
            ]
            all_responses.extend(flat_batch_responses)

            logger.info(
                f"Processed batch {i // batch_size + 1} of {(len(axons) - 1) // batch_size + 1}"
            )

        return all_responses

    @staticmethod
    async def _semaphore_limited_forward(dendrite, axons, synapse, timeout=12):
        """
        Wrapper around dendrite.forward that limits concurrent calls using a semaphore.
        """
        async with Validator._forward_semaphore:
            return await dendrite.forward(
                axons=axons,
                synapse=synapse,
                deserialize=False,
                timeout=timeout,
            )

    # Validator update_score_and_send_feedback helper functions
    def _get_validator_hotkeys(self) -> List[str]:
        """Get the hotkeys of the validators in the metagraph.

        Returns a list of validator hotkeys.
        """
        validator_hotkeys: List[str] = [
            hotkey
            for uid, hotkey in enumerate(self.metagraph.hotkeys)
            if not is_miner(self.metagraph, uid)
        ]
        if get_config().ignore_min_stake:
            validator_hotkeys.append(self.vali_hotkey)
        return validator_hotkeys

    async def _get_task_batches(
        self,
        batch_size: int,
        expire_from: datetime,
        expire_to: datetime,
        filter_empty_result: bool = False,
    ) -> AsyncGenerator[List[DendriteQueryResponse], None]:
        """Get task in batches from the database"""
        async for task_batch, has_more_batches in ORM.get_expired_tasks(
            batch_size=batch_size,
            expire_from=expire_from,
            expire_to=expire_to,
            filter_empty_result=filter_empty_result,
        ):
            # Yield task batch first before break if no more batches
            yield task_batch

            if not has_more_batches:
                logger.success(
                    "No more unexpired tasks found for processing, exiting task monitoring."
                )
                gc.collect()
                break

    async def _update_task_results(
        self, task: DendriteQueryResponse
    ) -> List[TaskSynapseObject]:
        """
        Returns a list of updated miner responses
        """
        task_id: str = task.validator_task.task_id
        obfuscated_to_real_model_id: Dict[str, str] = await ORM.get_real_model_ids(
            task_id
        )

        updated_miner_responses: List[TaskSynapseObject] = []

        batch_size = 30
        # Returns ceiling of the division to get number of batches to process
        num_batches = math.ceil(len(task.miner_responses) / batch_size)

        for i in range(0, len(task.miner_responses), batch_size):
            batch: list[TaskSynapseObject] = task.miner_responses[i : i + batch_size]

            # Get the miner UIDs and create identifier tuples for logging
            miner_uids: list[tuple[str, int]] = await self._extract_miners_hotkey_uid(
                batch, self.metagraph
            )
            logger.info(
                f"Processing miner responses batch {i // batch_size + 1} of {num_batches} for validator task request: {task.validator_task.task_id} "
                f"to miners: {miner_uids}"
            )

            tasks = [
                self._update_miner_response(miner_response, obfuscated_to_real_model_id)
                for miner_response in batch
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, TaskSynapseObject):
                    updated_miner_responses.append(result)
                elif isinstance(result, InvalidMinerResponse):
                    logger.error(f"Invalid miner response: {result}")
                elif isinstance(result, Exception):
                    logger.error(f"Unexpected error: {result}")

            # After processing all results, determine successful and failed miners
            successful_identifiers, failed_identifiers = self._classify_miner_results(
                batch, updated_miner_responses, miner_uids
            )

            # Log successful and failed miners
            logger.info(
                f"Successful miner responses for validator request id: {task.validator_task.task_id}: {successful_identifiers}"
            )
            if failed_identifiers:
                logger.warning(
                    f"Failed to get miner responses for validator request id: {task.validator_task.task_id}: {failed_identifiers}"
                )

            logger.success(
                f"Completed processing {len(updated_miner_responses)} miner responses in {num_batches} batches"
            )
        return updated_miner_responses

    async def _update_miner_response(
        self,
        miner_response: TaskSynapseObject,
        obfuscated_to_real_model_id: Dict[str, str],
    ) -> TaskSynapseObject | None:
        """
        Gets task results from a miner. Calculates the average across all task results.

        If no task results, return None. Else append it to miner completion response.
        """
        # Validate miner response
        if (
            not miner_response.axon
            or not hasattr(miner_response.axon, "hotkey")
            or not miner_response.axon.hotkey
            or not miner_response.dojo_task_id
        ):
            raise InvalidMinerResponse(
                f"""Missing hotkey, task_id, or axon:
                axon: {miner_response.axon}
                hotkey: {miner_response.axon.hotkey if miner_response.axon else None}
                dojo_task_id: {miner_response.dojo_task_id}"""
            )

        # Fetch task results
        task_results: List[TaskResult] = await self._get_task_results_from_miner(
            miner_response.axon.hotkey, miner_response.dojo_task_id
        )

        if not task_results:
            logger.info(
                f"No task results from miner: {miner_response.axon.hotkey} for dojo task id: {miner_response.dojo_task_id}, skipping"
            )
            return None

        # Update the task results in the database
        success = await ORM.update_miner_task_results(
            miner_hotkey=miner_response.axon.hotkey,
            dojo_task_id=miner_response.dojo_task_id,
            task_results=task_results,
        )

        if not success:
            logger.warning(
                f"Failed to update task_result for miner {miner_response.axon.hotkey}"
            )

        # Calculate average scores
        model_id_to_avg_score = self._calculate_averages(
            task_results, obfuscated_to_real_model_id
        )

        # Check for completion responses
        if not miner_response.completion_responses:
            logger.info("No completion responses, skipping")
            return None

        for completion in miner_response.completion_responses:
            if completion.completion_id in model_id_to_avg_score:
                completion.score = model_id_to_avg_score[completion.completion_id]

        return miner_response

    async def _get_task_results_from_miner(
        self, miner_hotkey: str, dojo_task_id: str
    ) -> list[TaskResult]:
        """Fetch task results from the miner's Axon using Dendrite.

        Args:
            miner_hotkey (str): The hotkey of the miner to query
            dojo_task_id (str): The ID of the task to fetch results for

        Returns:
            list[TaskResult]: List of task results or empty list if request fails
        """
        if not self.dendrite:
            logger.error("Dendrite not initialized")
            return []

        try:
            try:
                axon_index = self.metagraph.hotkeys.index(miner_hotkey)
                coldkey = self.metagraph.coldkeys[axon_index]
            except ValueError:
                logger.warning(f"Miner hotkey {miner_hotkey} not found in metagraph")
                return []

            axon = self.metagraph.axons[axon_index]
            miner_axon = bt.AxonInfo(
                ip=axon.ip,
                port=axon.port,
                hotkey=miner_hotkey,
                coldkey=coldkey,
                version=axon.version,
                ip_type=axon.ipType,
            )

            # Send the request via Dendrite and get the response
            max_retries = 3
            retry_count = 0

            while retry_count < max_retries:
                responses: list[
                    TaskResultRequest
                ] = await self._semaphore_limited_forward(
                    self.dendrite,
                    [miner_axon],
                    TaskResultRequest(dojo_task_id=dojo_task_id),
                    timeout=30,
                )

                if responses and responses[0] and responses[0].task_results:
                    logger.info(
                        f"Received task results from miner {miner_hotkey} for task {dojo_task_id} after {retry_count + 1} attempts"
                    )
                    return responses[0].task_results

                retry_count += 1
                if retry_count < max_retries:
                    logger.info(
                        f"Empty results from miner {miner_hotkey} for task {dojo_task_id}, retry {retry_count}/{max_retries}"
                    )
                    await asyncio.sleep(2**retry_count)  # Exponential backoff

            logger.info(
                f"No results from miner {miner_hotkey} for task {dojo_task_id} after {max_retries} attempts"
            )
            return []

        except Exception as e:
            logger.error(f"Error fetching from miner {miner_hotkey}: {str(e)}")
            return []

    @staticmethod
    def _calculate_averages(
        task_results: list[TaskResult], obfuscated_to_real_model_id
    ) -> dict[str, float]:
        """Calculate average scores for each model from task results.

        Args:
            task_results: List of task results containing scores
            obfuscated_to_real_model_id: Mapping of obfuscated to real model IDs

        Returns:
            Dictionary mapping model IDs to their average scores
        """
        model_id_to_total_score = defaultdict(float)
        num_scores_by_workers = 0

        for result in task_results:
            for result_data in result.result_data:
                model = getattr(result_data, "model", None)
                criteria = getattr(result_data, "criteria", None)
                if model is not None and criteria and len(criteria) > 0:
                    # TODO refactor to handle multiple criteria, when we have more than one criterion
                    criterion = criteria[0]
                    if criterion.get("type") == CriteriaTypeEnum.SCORE:
                        real_model_id = obfuscated_to_real_model_id.get(model, model)
                        model_id_to_total_score[real_model_id] += criterion.get(
                            "value", 0
                        )
                        num_scores_by_workers += 1

        # Calculate averages
        return {
            model_id: (total_score / num_scores_by_workers)
            for model_id, total_score in model_id_to_total_score.items()
        }

    async def _update_miner_raw_scores_batch(
        self,
        task_id: str,
        miner_responses: List[TaskSynapseObject],
        max_retries: int = 20,
    ) -> None:
        """
        Update the miner raw scores in the database in batches

        If there are any failed updates, retry using failed_indices.
        """
        remaining_responses = miner_responses

        for attempt in range(max_retries):
            try:
                (
                    success,
                    failed_indices,
                ) = await ORM.update_miner_raw_scores(remaining_responses)
                if success:
                    logger.success(
                        f"Successfully updated {len(remaining_responses)} miner completions for request {task_id}"
                    )
                    return
                else:
                    if attempt == max_retries - 1:
                        logger.error(
                            f"Failed to update {len(failed_indices)} miner completions after {max_retries} attempts"
                        )
                    else:
                        logger.warning(
                            f"Retrying {len(failed_indices)} failed updates, attempt {attempt + 2}/{max_retries}"
                        )
                        remaining_responses = [
                            remaining_responses[i] for i in failed_indices
                        ]
                        await asyncio.sleep(2**attempt)

            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(
                        f"Error updating miner completions batch after {max_retries} attempts: {e}"
                    )
                else:
                    logger.warning(f"Error during attempt {attempt + 1}, retrying: {e}")
                    await asyncio.sleep(2**attempt)

    async def _score_task(
        self, task: DendriteQueryResponse
    ) -> tuple[str, Dict[str, float]]:
        """Process a task and calculate the scores for the miner responses"""
        if not task.miner_responses:
            logger.warning("📝 No miner responses, skipping task")
            return task.validator_task.task_id, {}

        hotkey_to_scores = {}
        try:
            updated_miner_responses = Scoring.calculate_score(
                validator_task=task.validator_task,
                miner_responses=task.miner_responses,
            )

            # Create hotkey_to_completion_responses mapping and hotkey_to_scores mapping
            hotkey_to_completion_responses = {}
            for miner_response in updated_miner_responses:
                if miner_response.axon and miner_response.axon.hotkey:
                    hotkey_to_completion_responses[miner_response.axon.hotkey] = (
                        miner_response.completion_responses
                    )

                    # Get ground truth score from the first completion response that has one
                    if miner_response.completion_responses:
                        for completion in miner_response.completion_responses:
                            if (
                                completion.criteria_types
                                and completion.criteria_types[0].scores
                                and completion.criteria_types[
                                    0
                                ].scores.ground_truth_score
                                is not None
                            ):
                                hotkey_to_scores[miner_response.axon.hotkey] = (
                                    completion.criteria_types[
                                        0
                                    ].scores.ground_truth_score
                                )
                                break

            if not hotkey_to_completion_responses:
                logger.info("📝 Did not manage to generate a dict of hotkey to score")
                return task.validator_task.task_id, {}

            success, failed_hotkeys = await ORM.update_miner_scores(
                task_id=task.validator_task.task_id,
                miner_responses=updated_miner_responses,
            )

            if not success:
                logger.error(f"Failed to update scores for hotkeys: {failed_hotkeys}")

        except Exception as e:
            logger.error(
                f"📝 Error occurred while calculating scores: {e}. Request ID: {task.validator_task.task_id}"
            )
            return task.validator_task.task_id, {}

        logger.info(
            f"📝 Received {len(task.miner_responses)} responses from miners. "
            f"Processed {len(hotkey_to_completion_responses.keys())} responses for scoring."
        )

        await self.send_scores(
            synapse=ScoringResult(
                task_id=task.validator_task.task_id,
                hotkey_to_completion_responses=hotkey_to_completion_responses,
            ),
            hotkeys=list(hotkey_to_completion_responses.keys()),
        )

        return task.validator_task.task_id, hotkey_to_scores

    async def _get_dojo_task_scores_and_gt(
        self, miner_responses: List[TaskSynapseObject]
    ):
        """Get the scores and ground truth for each miner response"""
        hotkey_to_dojo_task_scores_and_gt = []
        for miner_response in miner_responses:
            if miner_response.dojo_task_id is not None:
                model_to_score_and_gt_map = (
                    await ORM.get_scores_and_ground_truth_by_dojo_task_id(
                        miner_response.dojo_task_id
                    )
                )
                hotkey_to_dojo_task_scores_and_gt.append(
                    {
                        "hotkey": (
                            miner_response.axon.hotkey if miner_response.axon else None
                        ),
                        "dojo_task_id": miner_response.dojo_task_id,
                        "scores_and_gt": model_to_score_and_gt_map,
                    }
                )
        return hotkey_to_dojo_task_scores_and_gt

    # async def block_headers_callback(self, block: dict):
    #     logger.trace(f"Received block headers {block}")
    #     block_header = parse_block_headers(block)
    #     block_number = block_header.number.to_int()
    #     self._last_block = block_number

    async def block_updater(self):
        while True:
            block = await self.kami.get_current_block()
            if block and block != self.block:
                self._last_block = block
                logger.debug(f"Updated block to {self._last_block}")

            if os.getenv("FAST_MODE"):
                continue

            logger.info(
                f"Updated block to {self._last_block}"
            )  # log new block if non fast_mode

            await asyncio.sleep(12)

    async def _extract_miners_hotkey_uid(
        self, batch: list[TaskSynapseObject], metagraph: SubnetMetagraph
    ) -> list[tuple[str, int]]:
        """
        Extract UIDs for miners based on their hotkeys.

        Args:
            batch: List of miner responses
            metagraph: The metagraph containing hotkey information

        Returns:
            List of tuples containing (hotkey_short, uid)
        """
        miner_uids: list[tuple[str, int | None]] = []
        for miner_response in batch:
            hotkey = miner_response.miner_hotkey
            hotkey_short = hotkey if hotkey else "None"

            try:
                uid: int | None = metagraph.hotkeys.index(hotkey)
                miner_uids.append((hotkey_short, uid))
            except ValueError:
                miner_uids.append((hotkey_short, None))

        return miner_uids

    async def _retrieve_axons(self, uids: list[int] = []) -> List[bt.AxonInfo]:
        # Return miner UIDs based on stakes
        logger.debug(f"Retrieving axons for uids: {uids}")

        axons: list[bt.AxonInfo] = []
        for uid, axon in enumerate(self.metagraph.axons):
            if uids and uid not in uids:
                continue

            if not axon.ip or not axon.port:
                continue

            hotkey = self.metagraph.hotkeys[uid]
            coldkey = self.metagraph.coldkeys[uid]

            eff_stake = aget_effective_stake(hotkey, self.metagraph)
            if (
                not get_config().ignore_min_stake
                and eff_stake > dojo.VALIDATOR_MIN_STAKE
            ):
                logger.debug(
                    f"{hotkey}, effective stake: {eff_stake} exceeds threshold of {dojo.VALIDATOR_MIN_STAKE} to be considered miner"
                )
                continue

            new_axon = bt.AxonInfo(
                ip=axon.ip,
                port=axon.port,
                hotkey=hotkey,
                coldkey=coldkey,
                version=axon.version,
                ip_type=axon.ipType,
            )
            axons.append(new_axon)

        return axons

    def _classify_miner_results(
        self,
        batch: list[TaskSynapseObject],
        updated_miner_responses: list[TaskSynapseObject],
        miner_uids: list[tuple[str, int]],
    ) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
        """
        Classify miners as successful or failed based on their responses.

        Args:
            batch: List of original miner responses
            updated_miner_responses: List of successfully processed miner responses
            miner_uids: List of (hotkey_short, uid) tuples from _extract_miners_hotkey_uid

        Returns:
            Tuple of (successful_identifiers, failed_identifiers)
        """
        # Get the hotkeys of successful miners from updated_miner_responses
        successful_hotkeys = {
            miner_response.miner_hotkey
            for miner_response in updated_miner_responses
            if miner_response.miner_hotkey
        }

        # Classify each miner as successful or failed
        successful_identifiers = []
        failed_identifiers = []

        for idx, miner_response in enumerate(batch):
            hotkey = miner_response.miner_hotkey
            if not hotkey:
                continue

            identifier = miner_uids[idx]
            if hotkey in successful_hotkeys:
                successful_identifiers.append(identifier)
            else:
                failed_identifiers.append(identifier)

        return successful_identifiers, failed_identifiers
