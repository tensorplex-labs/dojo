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
from http import HTTPStatus
from typing import AsyncGenerator, Dict, List, TypeAlias

import aiohttp
import bittensor as bt
import numpy as np
import torch
from kami import AxonInfo, KamiClient, SetWeightsPayload, SubnetMetagraph
from loguru import logger
from messaging import Client, StdResponse, get_client
from torch.nn import functional as F

from commons.dataset.synthetic import SyntheticAPI
from commons.exceptions import (
    EmptyScores,
    FatalSyntheticGenerationError,
    InvalidMinerResponse,
    NoNewExpiredTasksYet,
    SetWeightsFailed,
    SyntheticGenerationError,
)
from commons.hfl_helpers import HFLManager
from commons.human_feedback import HFLConstants, should_continue_hfl
from commons.objects import ObjectManager
from commons.orm import ORM
from commons.score_storage import ScoreStorage
from commons.scoring import Scoring, hfl
from commons.utils import (
    _terminal_plot,
    aget_effective_stake,
    aobject,
    datetime_as_utc,
    get_epoch_time,
    get_new_uuid,
    set_expire_time,
)
from database.client import connect_db
from database.mappers import map_miner_response_to_completion_responses
from database.prisma.enums import HFLStatusEnum, TaskTypeEnum
from database.prisma.models import HFLState, ValidatorTask
from database.prisma.types import HFLStateUpdateInput
from dojo import get_spec_version
from dojo.constants import ValidatorConstant, ValidatorInterval
from dojo.protocol import (
    CompletionResponse,
    CriteriaType,
    CriteriaTypeEnum,
    DendriteQueryResponse,
    Heartbeat,
    ScoreCriteria,
    ScoreResultSynapse,
    Scores,
    SyntheticQA,
    SyntheticTaskSynapse,
    TaskResult,
    TaskResultSynapse,
    TextFeedbackEvent,
)
from dojo.utils.config import get_config
from dojo.utils.weight_utils import (
    aprocess_weights_for_netuid,
    convert_weights_and_uids_for_emit,
)
from entrypoints.analytics_upload import run_analytics_upload

ObfuscatedModelMap: TypeAlias = Dict[str, str]
SyntheticMetadata: TypeAlias = dict[str, str]

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
    kami: KamiClient

    async def __init__(self):
        await connect_db()
        self.QUALITY_WEIGHT = 0.8
        self._connection_lock = asyncio.Lock()
        # considering the payload of heartbeats we can afford higher concurrency
        # NOTE: the parameter essentially determines the batch size of batch sending requests
        self._semaphore_heartbeats = asyncio.BoundedSemaphore(32)
        self._semaphore_synthetic_task = asyncio.BoundedSemaphore(10)
        self._semaphore_scores = asyncio.BoundedSemaphore(32)

        self.kami = KamiClient()

        self.loop = asyncio.get_event_loop()
        self.config = ObjectManager.get_config()

        logger.info(self.config)

        logger.info("Setting up bittensor objects....")
        self.metagraph = await self.kami.get_metagraph(self.config.netuid)
        logger.info(f"Metagraph Loaded for {self.metagraph.netuid}")

        self.keyringpair = await self.kami.get_keyringpair()
        self.client = Client(hotkey=self.keyringpair.hotkey, session=get_client())
        self.uid = self.metagraph.hotkeys.index(self.keyringpair.hotkey)
        logger.info(
            f"Running neuron on subnet: {self.config.netuid} with uid {self.uid}"
        )

        self.step = 0
        self.last_anal_upload_time: datetime | None = None
        # Set up initial scoring weights for validation
        self.synthetic_score: torch.Tensor = torch.zeros(
            len(self.metagraph.hotkeys), dtype=torch.float32
        )
        self.hfl_scores: torch.Tensor = torch.zeros(
            len(self.metagraph.hotkeys), dtype=torch.float32
        )

        await self.check_registered()
        await self.load_state()

    async def _send_scores(
        self, validator_task_id: str, hotkeys: List[str], scores: List[Scores]
    ):
        """Send scores that taostats, CLI, etc. cannot see for miners who participated."""
        miners_uids = await self.get_active_miner_uids()
        metagraph_axons = self._retrieve_axons(miners_uids)
        axons = [axon for axon in metagraph_axons if axon.hotkey in hotkeys]
        if not axons:
            logger.warning("No axons to send scores back to... skipping")
            return
        logger.info(f"Sending back scores to miners for task id: {validator_task_id}")

        urls = [f"http://{axon.ip}:{axon.port}" for axon in axons]
        models = [
            ScoreResultSynapse(validator_task_id=validator_task_id, scores=miner_scores)
            for miner_scores in scores
        ]

        responses = await self.client.batch_send(
            urls=urls, models=models, semaphore=self._semaphore_scores, timeout_sec=30
        )

        for response, axon in zip(responses, axons):
            if (
                response.client_response
                and response.client_response.status == HTTPStatus.OK
                and not response.error
                and not response.exception
            ):
                logger.success(f"Sent scores to {axon.hotkey} successfully")

    def obfuscate_model_names(
        self, completion_responses: list[CompletionResponse]
    ) -> tuple[dict[str, str], list[CompletionResponse]]:
        """Obfuscate model names for both external requests and synthetic requests to prevent miners from knowing the true model names."""
        obfuscated_model_to_model: dict[str, str] = {}
        for completion in completion_responses:
            if completion.completion_id is None:
                raise ValueError("completion_id is None")
            original_model = completion.model
            completion.model = completion.completion_id
            obfuscated_model_to_model[completion.completion_id] = original_model
        return obfuscated_model_to_model, completion_responses

    def deobfuscate_model_names(
        self,
        completion_responses: list[CompletionResponse],
        obfuscated_model_to_model: dict[str, str],
    ):
        """Deobfuscate model names for both external requests and synthetic requests."""
        for completion in completion_responses:
            # Get the current obfuscated name from the model field
            obfuscated_name = completion.model

            # Look up the original model name
            if obfuscated_name in obfuscated_model_to_model:
                completion.model = obfuscated_model_to_model[obfuscated_name]
            else:
                logger.warning(
                    f"Could not deobfuscate model name: {obfuscated_name} not found in mapping"
                )

        return completion_responses

    async def get_active_miner_uids(self) -> list[int]:
        async with self._uids_alock:
            return sorted(list(self._active_miner_uids))

    async def set_weights(self):
        """
        Sets the validator weights to the metagraph hotkeys based on the scores it has received from the miners.
        The weights determine the trust and incentive level the validator assigns to miner nodes on the network.
        """

        # ensure scores not being written to by other coroutines
        # Check if scores contains any NaN values and log a warning if it does.
        scores = await self.get_combined_score()
        if torch.isnan(scores).any():
            logger.warning(
                "Scores contain NaN values. This may be due to a lack of responses from miners, or a bug in your reward functions."
            )

        logger.info("Attempting to set weights")

        # ensure sum = 1
        normalized_weights = F.normalize(scores.cpu(), p=1, dim=0)

        safe_normalized_weights = normalized_weights
        if isinstance(normalized_weights, np.ndarray):
            safe_normalized_weights = torch.from_numpy(normalized_weights).to("cpu")
        elif isinstance(normalized_weights, torch.Tensor):
            pass

        # we don't read uids from metagraph because polling metagraph happens
        # faster than calling set_weights and scores is already
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

        logger.info(f"Final weights:\n{final_weights}")
        logger.info(f"Final uids:\n{final_uids}")

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
            logger.error(traceback.format_exc())
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

                uids, weights = convert_weights_and_uids_for_emit(
                    uids=uids,
                    weights=weights,
                )

                logger.info(f"Converted uids: {uids}")
                logger.info(f"Converted weights: {weights}")

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
            logger.info("Metagraph axon info has not changed, skipping resync")
            return

        logger.info(
            "Metagraph updated, re-syncing hotkeys, dendrite pool and moving averages"
        )

        # Zero out all hotkeys that have been replaced.
        for uid, hotkey in enumerate(previous_hotkeys):
            if hotkey != current_hotkeys[uid]:
                self.synthetic_score[uid] = 0  # hotkey has been replaced
                self.hfl_scores[uid] = 0  # hotkey has been replaced

        # Check to see if the metagraph has changed size.
        # If so, we need to add new hotkeys and moving averages.
        if len(previous_hotkeys) != len(current_hotkeys):
            # Update the size of the moving average scores.
            async with self._scores_alock:
                synthetic_score = self._resize_score_tensor(self.synthetic_score)
                hfl_scores = self._resize_score_tensor(self.hfl_scores)
                self.synthetic_score = torch.clamp(synthetic_score, min=0.0)
                self.hfl_scores = torch.clamp(hfl_scores, min=0.0)

    def _calculate_incentives(
        self,
        hotkey_to_scores: dict[str, float],
        current_scores_tensor: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        # scores dimensions might have been updated after resyncing... len(uids) != len(self.synthetic_score)
        # same-length initialization is needed for EMA calculation later
        new_incentives = torch.zeros((len(self.metagraph.hotkeys),))
        existing_incentives = torch.zeros((len(self.metagraph.hotkeys),))

        # Handle NaN values
        hotkey_to_scores = {
            key: (0.0 if np.isnan(value) else value)
            for key, value in hotkey_to_scores.items()
        }

        # Copy existing scores for current UIDs
        existing_size = min(len(current_scores_tensor), len(self.metagraph.hotkeys))
        existing_incentives[:existing_size] = current_scores_tensor[:existing_size]

        for hotkey, value in hotkey_to_scores.items():
            # search metagraph for hotkey and grab uid
            try:
                uid: int = self.metagraph.hotkeys.index(hotkey)
                logger.info(f"Score for hotkey {hotkey} is {value}")
                new_incentives[uid] = value
            except ValueError:
                logger.warning("Old hotkey found from previous metagraph")
                continue

        assert (
            existing_incentives.shape == new_incentives.shape
        ), "Existing incentives and new incentives must have same shape for consistency"
        return existing_incentives, new_incentives

    async def update_scores_tensor(
        self,
        hotkey_to_synthetic_scores: dict[str, float],
        hotkey_to_hfl_scores: dict[str, float],
    ):
        """
        Performs exponential moving average on the scores based on the rewards received from the miners.
        Updates synthetic and HFL scores independently.
        """
        # Update synthetic scores if available
        if hotkey_to_synthetic_scores:
            logger.info(f"Updating synthetic scores with {hotkey_to_synthetic_scores}")
            self.synthetic_score = await self._calculate_score_ema(
                hotkey_to_scores=hotkey_to_synthetic_scores,
                current_scores=self.synthetic_score,
                moving_average_alpha=self.config.neuron.moving_average_alpha,
            )
            logger.info(f"Synthetic scores after update: {self.synthetic_score}")
        else:
            logger.warning(
                "hotkey_to_synthetic_scores is empty, skipping synthetic score update"
            )
            async with self._scores_alock:
                self.synthetic_score = self._resize_score_tensor(self.synthetic_score)

        # Update HFL scores if available
        if hotkey_to_hfl_scores:
            logger.info(f"Updating HFL scores with {hotkey_to_hfl_scores}")
            self.hfl_scores = await self._calculate_score_ema(
                hotkey_to_scores=hotkey_to_hfl_scores,
                current_scores=self.hfl_scores,
                moving_average_alpha=self.config.weights.hfl_ema_alpha,
            )
            logger.info(f"HFL scores after update: {self.hfl_scores}")
        else:
            logger.warning("hotkey_to_hfl_scores is empty, skipping HFL score update")
            async with self._scores_alock:
                self.hfl_scores = self._resize_score_tensor(self.hfl_scores)

    async def _calculate_score_ema(
        self,
        hotkey_to_scores: dict[str, float],
        current_scores: torch.Tensor,
        moving_average_alpha: float,
    ) -> torch.Tensor:
        """
        Updates a specific type of score using exponential moving average.

        Args:
            score_type: Type of score being updated ("synthetic" or "hfl")
            hotkey_to_scores: Dictionary mapping hotkeys to their scores
            current_scores: Current tensor of scores to be updated
            moving_average_alpha: Alpha value for the exponential moving average
        """

        # Calculate incentives based on scores
        existing_incentives, new_incentives = self._calculate_incentives(
            hotkey_to_scores=hotkey_to_scores,
            current_scores_tensor=current_scores,
        )

        logger.info(f"Incentives for scores: {new_incentives.shape=} {new_incentives=}")

        # Update scores with lock protection
        async with self._scores_alock:
            _terminal_plot(
                f"Scores before update, block: {self.block}",
                current_scores.numpy(),
            )

            # Apply exponential moving average
            updated_scores = (
                moving_average_alpha * new_incentives
                + (1 - moving_average_alpha) * existing_incentives
            )
            # ensure scores are non-negative
            updated_scores = torch.clamp(updated_scores, min=0.0)

            _terminal_plot(
                f"Scores after update, block: {self.block}",
                updated_scores.numpy(),
            )

        return updated_scores

    async def save_state(
        self,
    ):
        """Saves the state of the validator to the database."""
        if self.step == 0:
            return

        try:
            if np.count_nonzero(self.synthetic_score) == 0:
                logger.warning("Scores are all zeros, but saving anyway!")

            if np.count_nonzero(self.hfl_scores) == 0:
                logger.warning("HFL scores are all zeros, but saving anyway!")

            await ScoreStorage.save(self.synthetic_score, self.hfl_scores)
            logger.success(
                f"📦 Saved validator state with scores: {self.synthetic_score}"
            )
        except EmptyScores as e:
            logger.info(f"No need to to save validator state: {e}")
        except Exception as e:
            logger.error(f"Failed to save validator state: {e}")

    async def _load_state(self):
        try:
            await connect_db()
            synthetic_scores, hfl_scores = await ScoreStorage.load()
            # At upgrade time, we'll have synthetic_scores from previous version but hfl_scores will be None
            # Handle this migration case explicitly with clear logging
            if synthetic_scores is not None and hfl_scores is None:
                logger.info(
                    "Detected upgrade from previous version: loading synthetic scores only, initializing HFL scores to zeros"
                )
                hfl_scores = torch.zeros(len(synthetic_scores), dtype=torch.float32)

            # Neither score was found
            if synthetic_scores is None and hfl_scores is None:
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

            logger.success(
                f"Loaded validator state: synthetic_scores shape={synthetic_scores.shape if synthetic_scores is not None else None}, hfl_scores shape={hfl_scores.shape if hfl_scores is not None else None}"
            )
            async with self._scores_alock:
                # If synthetic_scores is None, initialize it with zeros
                if synthetic_scores is None:
                    synthetic_scores = torch.zeros(len(self.metagraph.hotkeys))
                    logger.warning("Synthetic scores not found, initializing to zeros")

                # If hfl_scores is None, initialize it with zeros
                if hfl_scores is None:
                    hfl_scores = torch.zeros(len(self.metagraph.hotkeys))
                    logger.warning("HFL scores not found, initializing to zeros")

                # If metagraph has more hotkeys than scores, adjust length for synthetic scores
                if len(synthetic_scores) < len(self.metagraph.hotkeys):
                    logger.warning(
                        "Synthetic scores state is less than current metagraph hotkeys length, adjusting length. This should only happen when subnet is not at max UIDs yet."
                    )
                    # Length adjusted scores
                    adjusted_synthetic_scores = torch.zeros(len(self.metagraph.hotkeys))
                    adjusted_synthetic_scores[: len(synthetic_scores)] = (
                        synthetic_scores
                    )
                    logger.info(
                        f"Load state: adjusted synthetic scores shape from {synthetic_scores.shape} to {adjusted_synthetic_scores.shape}"
                    )
                    self.synthetic_score = torch.clamp(adjusted_synthetic_scores, 0.0)
                else:
                    self.synthetic_score = torch.clamp(synthetic_scores, 0.0)

                # If metagraph has more hotkeys than scores, adjust length for HFL scores
                if len(hfl_scores) < len(self.metagraph.hotkeys):
                    logger.warning(
                        "HFL scores state is less than current metagraph hotkeys length, adjusting length. This should only happen when subnet is not at max UIDs yet."
                    )
                    # Length adjusted scores
                    adjusted_hfl_scores = torch.zeros(len(self.metagraph.hotkeys))
                    adjusted_hfl_scores[: len(hfl_scores)] = hfl_scores
                    logger.info(
                        f"Load state: adjusted HFL scores shape from {hfl_scores.shape} to {adjusted_hfl_scores.shape}"
                    )
                    self.hfl_scores = torch.clamp(adjusted_hfl_scores, 0.0)
                else:
                    self.hfl_scores = torch.clamp(hfl_scores, 0.0)

                _terminal_plot(
                    f"synthetic scores on load, block: {self.block}",
                    self.synthetic_score.numpy(),
                )
                _terminal_plot(
                    f"HFL scores on load, block: {self.block}", self.hfl_scores.numpy()
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
        if not hasattr(self, "_block"):
            self._block = 0
        return self._block

    @block.setter
    def block(self, value: int):
        self._block = value

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
            await asyncio.sleep(ValidatorConstant.VALIDATOR_STATUS)

    async def send_heartbeats(self):
        """Perform a health check periodically to ensure and check which miners are reachable"""
        while True:
            await asyncio.sleep(ValidatorInterval.VALIDATOR_HEARTBEAT)
            try:
                axons = self._retrieve_axons()
                urls = [f"http://{axon.ip}:{axon.port}" for axon in axons]
                logger.info(f"Sending heartbeats to {len(axons)} miners")

                responses = await self.client.batch_send(
                    urls,
                    [Heartbeat(ack=False)] * len(urls),
                    self._semaphore_heartbeats,
                    timeout_sec=30,
                )

                active_uids: set[int] = set()
                for uid, (url, response) in enumerate(zip(urls, responses)):
                    if response.exception or response.error:
                        logger.error(
                            f"Failed sending to {url} due to error: {response.error}, exception: {response.exception}"
                        )
                        continue

                    if response.body.ack:
                        active_uids.add(uid)

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
                # Check if there are any active miners. If no active miners, skip the request generation.
                if not self._active_miner_uids:
                    logger.info(
                        f"No active miners to send request to... sleeping for {ValidatorInterval.VALIDATOR_RUN} seconds"
                    )
                    await asyncio.sleep(ValidatorInterval.VALIDATOR_RUN)
                    continue
                (
                    synthetic_task,
                    ground_truth,
                    obfuscated_model_to_model,
                    synthetic_metadata,
                ) = await self._generate_synthetic_request()

                if synthetic_task and ground_truth:
                    await self.send_request(
                        synapse=synthetic_task,
                        ground_truth=ground_truth,
                        obfuscated_model_to_model=obfuscated_model_to_model,
                        synthetic_metadata=synthetic_metadata,
                    )
                self.step += 1

                # Sync metagraph and potentially set weights.
                await self.sync()
                await asyncio.sleep(ValidatorInterval.VALIDATOR_RUN)
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
                await asyncio.sleep(ValidatorInterval.VALIDATOR_RUN)

        # Cleanup on exit
        await self.cleanup()

    async def update_tasks_polling(self):
        """
        Periodically updates task results for expired tasks every 15 minutes.
        Decoupled from scoring function to allow more frequent updates.
        """
        while True:
            await asyncio.sleep(ValidatorInterval.VALIDATOR_UPDATE_TASK)  # 15 minutes
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
            await asyncio.sleep(ValidatorInterval.VALIDATOR_UPDATE_SCORE)
            # for each hotkey, a list of scores from all tasks being scored
            hotkey_to_synthetic_scores = defaultdict(list)
            hotkey_to_hfl_scores = defaultdict(list)
            try:
                # Get tasks that expired between 2 hours ago and 30 minutes ago
                # This creates a 30-minute buffer to ensure tasks have been updated sufficiently
                now = datetime.now(timezone.utc)
                expire_from = datetime_as_utc(now - timedelta(hours=2))
                expire_to = datetime_as_utc(
                    now - timedelta(seconds=ValidatorInterval.BUFFER_PERIOD)
                )

                logger.info(f" Current time: {now}")
                logger.info(
                    f"📝 performing scoring, context: {expire_from}, {expire_to}"
                )
                processed_request_ids = []

                batch_size = 10
                async for task_batch in self._get_task_batches(
                    batch_size,
                    expire_from,
                    expire_to,
                    task_types=[
                        TaskTypeEnum.CODE_GENERATION,
                        TaskTypeEnum.SCORE_FEEDBACK,
                    ],
                ):
                    if not task_batch:
                        continue

                    for task in task_batch:
                        # Check if this is a regular task or an HFL task
                        try:
                            validator_task: SyntheticTaskSynapse = task.validator_task

                            if validator_task.task_type == TaskTypeEnum.CODE_GENERATION:
                                # Regular task flow
                                hotkey_to_score = await self._score_task(task)
                                task_id = task.validator_task.task_id
                                if task_id:
                                    processed_request_ids.append(task_id)
                                for hotkey, score in hotkey_to_score.items():
                                    hotkey_to_synthetic_scores[hotkey].append(score)

                                success = await self.send_scoring_result_to_miners(
                                    task_id
                                )
                                if not success:
                                    logger.error(
                                        f"Failed to send scoring result to miners for task {task_id}"
                                    )

                            elif (
                                validator_task.task_type == TaskTypeEnum.SCORE_FEEDBACK
                            ):
                                # SF task flow - need to check if it's ready for scoring
                                sf_task = await ORM.get_validator_task_by_id(
                                    validator_task.task_id,
                                    include={
                                        "completions": True,
                                        "miner_responses": {
                                            "include": {
                                                "scores": {
                                                    "include": {
                                                        "criterion_relation": True
                                                    }
                                                }
                                            }
                                        },
                                    },
                                )
                                if not sf_task or not sf_task.previous_task_id:
                                    logger.warning(
                                        f"Task {validator_task.task_id} or previous task not found"
                                    )
                                    continue

                                hfl_state = (
                                    await HFLManager.get_state_by_current_task_id(
                                        validator_task.task_id
                                    )
                                )
                                if not hfl_state:
                                    logger.warning(
                                        f"HFL state for task {validator_task.task_id} not found"
                                    )
                                    continue

                                if hfl_state.status != HFLStatusEnum.SF_COMPLETED:
                                    logger.warning(
                                        f"HFL state for task {validator_task.task_id} is not ready for scoring yet. Status: {hfl_state.status}"
                                    )
                                    continue

                                # Calculate TF scores
                                (
                                    hotkey_to_weighted_score,
                                    hotkey_to_tf_score,
                                    hotkey_to_sf_score,
                                ) = await hfl.score_hfl_tasks(sf_task)

                                # TODO: remove this
                                logger.info(
                                    f"Scored HFL task {sf_task.id}, hotkey to weighted score: {hotkey_to_weighted_score}"
                                )
                                logger.info(
                                    f"Scored HFL task {sf_task.id}, hotkey to tf score: {hotkey_to_tf_score}"
                                )
                                logger.info(
                                    f"Scored HFL task {sf_task.id}, hotkey to sf score: {hotkey_to_sf_score}"
                                )
                                # update miner scores in database
                                await ORM.update_hfl_final_scores(
                                    sf_task,
                                    hotkey_to_sf_score,
                                    hotkey_to_tf_score,
                                )
                                success = await self.send_scoring_result_to_miners(
                                    sf_task.id
                                )
                                if not success:
                                    logger.warning(
                                        f"Failed to send scoring result to miners for task {sf_task.id}"
                                    )

                                success = await self.send_scoring_result_to_miners(
                                    sf_task.previous_task_id or ""
                                )
                                if not success:
                                    logger.warning(
                                        f"Failed to send scoring result to miners for task {sf_task.previous_task_id}"
                                    )

                                await self._decide_hfl_continuation(
                                    sf_task.id, hfl_state
                                )

                                # Mark as processed
                                processed_request_ids.append(sf_task.id)
                                # Get the parent TF task ID from the HFL state or task
                                tf_task_id = sf_task.previous_task_id
                                if tf_task_id:
                                    processed_request_ids.append(tf_task_id)
                                    logger.info(
                                        f"Marking parent TF task {tf_task_id} as processed"
                                    )
                                else:
                                    logger.warning(
                                        f"No parent TF task found for SF task {sf_task.id}"
                                    )
                                for hotkey, score in hotkey_to_weighted_score.items():
                                    hotkey_to_hfl_scores[hotkey].append(score)

                                logger.info(
                                    f"Scored HFL task {sf_task.id}, hotkey to hfl score: {hotkey_to_hfl_scores}"
                                )

                        except Exception as e:
                            logger.error(
                                f"Error in scoring task {task.validator_task.task_id}: {e}"
                            )
                            traceback.print_exc()
                            continue

                if processed_request_ids:
                    await ORM.mark_validator_task_as_processed(processed_request_ids)

                logger.success(
                    f"📝 All tasks processed, total tasks: {len(processed_request_ids)}"
                )

                # average scores across all tasks being scored by this trigger to update_scores
                # so miners moving average decay is lower
                # we incentivise both quality and quantity, but quality has higher weight than quantity
                final_hotkey_to_synthetic_score = {
                    hotkey: sum(scores) / len(scores) * self.QUALITY_WEIGHT
                    + sum(scores)
                    / len(processed_request_ids)
                    * (1 - self.QUALITY_WEIGHT)
                    for hotkey, scores in hotkey_to_synthetic_scores.items()
                    if scores
                }

                final_hotkey_to_hfl_score = {
                    hotkey: sum(scores) / len(scores) * self.QUALITY_WEIGHT
                    + sum(scores)
                    / len(processed_request_ids)
                    * (1 - self.QUALITY_WEIGHT)
                    for hotkey, scores in hotkey_to_hfl_scores.items()
                    if scores
                }
                logger.info(
                    f"📝 Got hotkey to score across synthetic tasks between expire_at from:{expire_from} and expire_at to:{expire_to}: {final_hotkey_to_synthetic_score}"
                )
                logger.info(
                    f"📝 Got hotkey to score across HFL tasks between expire_at from:{expire_from} and expire_at to:{expire_to}: {final_hotkey_to_hfl_score}"
                )

                await self.update_scores_tensor(
                    hotkey_to_synthetic_scores=final_hotkey_to_synthetic_score,
                    hotkey_to_hfl_scores=final_hotkey_to_hfl_score,
                )

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
            hotkey=str(self.keyringpair.hotkey),
        )
        if not is_registered:
            logger.error(
                f"Hotkey {self.keyringpair.hotkey} is not registered on netuid {self.config.netuid}."
                f" Please register the hotkey using `btcli s register` before trying again"
            )
            await self.cleanup()
            exit(1)

    # Validator Run helper functions
    async def cleanup(self):
        """Handle cleanup operations when shutting down"""
        logger.success("Validator axon stopped")
        await self.kami.close()
        await self.client.close()

    async def _generate_synthetic_request(
        self,
    ) -> tuple[
        SyntheticTaskSynapse | None,
        dict[str, int] | None,
        ObfuscatedModelMap,
        SyntheticMetadata,
    ]:
        """
        Generate a synthetic request for code generation tasks.

        Returns:
            tuple[SyntheticTaskSynapse | None, dict[str, int] | ObfuscatedModelMap]: Tuple containing the generated task synapse object
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

            obfuscated_model_to_model, completion_responses = (
                self.obfuscate_model_names(data.responses)
            )
            synapse = SyntheticTaskSynapse(
                task_id=task_id,
                prompt=data.prompt,
                task_type=str(TaskTypeEnum.CODE_GENERATION),
                expire_at=set_expire_time(ValidatorInterval.TASK_DEADLINE),
                completion_responses=completion_responses,
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

    def _log_request_failures(self, miner_responses, axons):
        try:
            valid_count = 0
            fails = []
            for response, axon in zip(miner_responses, axons):
                status_code = (
                    response.client_response.status if response.client_response else -1
                )
                try:
                    logger.info(
                        f"Miner hotkey: {axon.hotkey}, ack: {response.ack}, status_code: {status_code}"
                    )
                    if (
                        response.body.ack
                        and response.client_response
                        and response.client_response.status == HTTPStatus.OK
                    ):
                        valid_count += 1
                    else:
                        fails.append((axon.hotkey, status_code, response.body.ack))
                except Exception:
                    fails.append((axon.hotkey, status_code, response))
                    continue

            logger.info(f"Fails: {fails}")
            logger.info(f"Valid miner responses: {valid_count}")
        except Exception as e:
            logger.warning(
                f"Error occurred while trying to log request info, exception: {str(e)}"
            )
            pass

    async def send_request(
        self,
        synapse: SyntheticTaskSynapse,
        ground_truth: dict[str, int],
        obfuscated_model_to_model: ObfuscatedModelMap | None = None,
        synthetic_metadata: dict | None = None,
    ) -> ValidatorTask | None:
        """Send task requests to miners and process their responses.

        Args:
            synapse: Task synapse object containing the request details
            ground_truth: Ground truth data for scoring
            obfuscated_model_to_model: Mapping of obfuscated to real model names
            synthetic_task: Whether this is a synthetic task
            subset_size: Optional size to limit number of miners queried
        """

        if not synapse.completion_responses:
            logger.error("No completion responses to send")
            return

        start = get_epoch_time()
        active_miner_uids = await self.get_active_miner_uids()
        axons = self._retrieve_axons(active_miner_uids)
        if not axons:
            logger.warning("🤷 No axons to query ... skipping")
            return

        logger.info(
            f"⬆️ Sending task request for task id: {synapse.task_id}, miners uids:{active_miner_uids} with expire_at: {synapse.expire_at}"
        )

        miner_responses = await self.send_synthetic_task(synapse, axons)
        self._log_request_failures(miner_responses, axons)

        valid_miner_responses: List[SyntheticTaskSynapse] = []
        for response, axon in zip(miner_responses, axons):
            try:
                if (
                    not response.body.ack
                    or not response.client_response
                    or response.client_response != HTTPStatus.OK
                ):
                    continue

                # NOTE: map obfuscated model names back to the original model names
                if obfuscated_model_to_model and response.body.completion_responses:
                    real_model_ids = []
                    for i, completion in enumerate(response.body.completion_responses):
                        found_model_id = obfuscated_model_to_model.get(
                            completion.model, None
                        )
                        real_model_ids.append(found_model_id)
                        if found_model_id:
                            response.body.completion_responses[i].model = found_model_id
                            synapse.completion_responses[i].model = found_model_id

                    if any(c is None for c in real_model_ids):
                        logger.warning(
                            "Failed to map obfuscated model to original model"
                        )
                        continue

                # NOTE: why do we do this here? why do we really need it?
                response.body.miner_hotkey = axon.hotkey
                response.body.miner_coldkey = axon.coldkey
                if not axon.hotkey or not axon.coldkey:
                    logger.warning(
                        f"Axon hotkey/coldkey information is missing. {axon.coldkey=}, {axon.hotkey=}, check KamiClient client implementation"
                    )
                valid_miner_responses.append(response.body)

            except Exception as e:
                logger.error(f"Error processing miner response: {e}")
                continue

        logger.info(f"⬇️ Received {len(valid_miner_responses)} valid responses")
        if not valid_miner_responses:
            logger.info("No valid miner responses to process... skipping")
            return

        logger.debug("Attempting to saving dendrite response")
        validator_task = await ORM.save_task(
            validator_task=synapse,
            miner_responses=valid_miner_responses,
            ground_truth=ground_truth,
            metadata=synthetic_metadata,
        )
        if not validator_task:
            logger.error("Failed to save dendrite response")
            return

        logger.success(f"Saved dendrite response for task id: {synapse.task_id}")
        logger.info(
            f"Sending request to miners & processing took {get_epoch_time() - start}"
        )

        # clear axons
        axons.clear()

        return validator_task

    async def send_synthetic_task(
        self, synapse: SyntheticTaskSynapse, axons: list[AxonInfo] = []
    ) -> list[StdResponse[SyntheticTaskSynapse]]:
        """
        Send requests to miners in batches for parallel processing.

        Args:
            dendrite: Dendrite instance for network communication
            axons: List of miner axons to send requests to
            synapse: Original task synapse object
        Returns:
            list[SyntheticTaskSynapse]: Flattened list of all miner responses
        """
        if not synapse.completion_responses:
            logger.warning("No completion responses to send... skipping")
            return []

        active_uids = await self.get_active_miner_uids()
        if not axons:
            axons = self._retrieve_axons(uids=active_uids)

        urls = [f"http://{axon.ip}:{axon.port}" for axon in axons]
        logger.info(f"Sending heartbeats to {len(axons)} miners")

        synapses = [
            SyntheticTaskSynapse(
                epoch_timestamp=synapse.epoch_timestamp,
                task_id=synapse.task_id,
                prompt=synapse.prompt,
                task_type=synapse.task_type,
                expire_at=synapse.expire_at,
                completion_responses=random.sample(
                    synapse.completion_responses,
                    k=len(synapse.completion_responses),
                ),
            )
            for _ in range(len(urls))
        ]

        responses = await self.client.batch_send(
            urls,
            synapses,
            self._semaphore_synthetic_task,
            timeout_sec=30,
        )

        return responses

    async def _get_task_batches(
        self,
        batch_size: int,
        expire_from: datetime,
        expire_to: datetime,
        filter_empty_result: bool = False,
        task_types: List[TaskTypeEnum] = [TaskTypeEnum.CODE_GENERATION],
    ) -> AsyncGenerator[List[DendriteQueryResponse], None]:
        """Get task in batches from the database"""
        async for task_batch, has_more_batches in ORM.get_expired_tasks(
            batch_size=batch_size,
            expire_from=expire_from,
            expire_to=expire_to,
            filter_empty_result=filter_empty_result,
            is_processed=False,
            task_types=task_types,
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
    ) -> List[SyntheticTaskSynapse]:
        """
        Returns a list of updated miner responses
        """
        task_id: str = task.validator_task.task_id
        obfuscated_to_real_model_id: Dict[str, str] = await ORM.get_real_model_ids(
            task_id
        )

        updated_miner_responses: List[SyntheticTaskSynapse] = []

        batch_size = 30
        # Returns ceiling of the division to get number of batches to process
        num_batches = math.ceil(len(task.miner_responses) / batch_size)

        for i in range(0, len(task.miner_responses), batch_size):
            batch: list[SyntheticTaskSynapse] = task.miner_responses[i : i + batch_size]

            # Get the miner UIDs and create identifier tuples for logging
            miner_uids: list[
                tuple[str, int | None]
            ] = await self._extract_miners_hotkey_uid(batch, self.metagraph)
            logger.info(
                f"Processing miner responses batch {i // batch_size + 1} of {num_batches} for validator task request: {task.validator_task.task_id} "
                f"to miners: {miner_uids}"
            )

            tasks = [
                self._update_miner_response(
                    miner_response=miner_response,
                    validator_task_id=task_id,
                    obfuscated_to_real_model_id=obfuscated_to_real_model_id,
                )
                for miner_response in batch
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, SyntheticTaskSynapse):
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
        miner_response: SyntheticTaskSynapse,
        validator_task_id: str,
        obfuscated_to_real_model_id: Dict[str, str],
    ) -> SyntheticTaskSynapse | None:
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
            miner_hotkey=miner_response.axon.hotkey, validator_task_id=validator_task_id
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
        model_id_to_avg_score = self._calculate_averages(task_results)

        # Check for completion responses
        if not miner_response.completion_responses:
            logger.info("No completion responses, skipping")
            return None

        for completion in miner_response.completion_responses:
            if completion.completion_id in model_id_to_avg_score:
                completion.score = model_id_to_avg_score[completion.completion_id]

        return miner_response

    async def _get_task_results_from_miner(
        self, miner_hotkey: str, validator_task_id: str, max_retries: int = 3
    ) -> list[TaskResult]:
        """Fetch task results from the miner's Axon using Dendrite.

        Args:
            miner_hotkey (str): The hotkey of the miner to query
            dojo_task_id (str): The ID of the task to fetch results for
            max_retries (int): number of max retries for underlying request to target miner

        Returns:
            list[TaskResult]: List of task results or empty list if request fails
        """

        try:
            miner_axon: AxonInfo | None = next(
                (
                    self.metagraph.axons[i]
                    for i, hotkey in enumerate(self.metagraph.hotkeys)
                    if hotkey.lower() == miner_hotkey.lower()
                ),
                None,
            )
            if not miner_axon:
                logger.warning(f"Axon not found for {miner_hotkey}")
                return []

            url = f"http://{miner_axon.ip}:{miner_axon.port}"
            # TODO: change to validator task id, it's not validator's job to know dojo task id
            model = TaskResultSynapse(validator_task_id=validator_task_id)
            response = await self.client.send(
                url,
                model=model,
                timeout_sec=12,
                max_retries=max_retries,
                max_wait_sec=60,
            )
            if response.error or response.exception:
                logger.error(
                    f"Failed to send request to {url} for {miner_hotkey} due to error: {response.error}, exception: {response.exception}"
                )

            if response.body.task_results:
                logger.success(
                    f"Received task results from miner {miner_hotkey} for task {validator_task_id}"
                )
                return response.body.task_results

            logger.error(
                f"No results from miner {miner_hotkey} for task {validator_task_id} after {max_retries} attempts"
            )
            return []

        except Exception as e:
            logger.error(f"Error fetching from miner {miner_hotkey}: {str(e)}")
            return []

    # TODO: move to utils??
    @staticmethod
    def _calculate_averages(task_results: list[TaskResult]) -> dict[str, float]:
        """Calculate average scores for each model from task results.

        Args:
            task_results: List of task results containing scores
            obfuscated_to_real_model_id: Mapping of obfuscated to real model IDs

        Returns:
            Dictionary mapping model IDs to their average scores
        """
        model_id_to_total_score = defaultdict(float)

        for result in task_results:
            for result_data in result.result_data:
                model = getattr(result_data, "model", None)
                criteria = getattr(result_data, "criteria", None)
                if model is not None and criteria and len(criteria) > 0:
                    # TODO refactor to handle multiple criteria, when we have more than one criterion
                    criterion = criteria[0]
                    if criterion.get("type") == CriteriaTypeEnum.SCORE:
                        model_id_to_total_score[model] += criterion.get("value", 0)

        # Calculate averages
        return {
            model_id: (total_score / len(task_results))
            for model_id, total_score in model_id_to_total_score.items()
        }

    async def _update_miner_raw_scores_batch(
        self,
        task_id: str,
        miner_responses: List[SyntheticTaskSynapse],
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

    async def _score_task(self, task: DendriteQueryResponse) -> Dict[str, float]:
        """Process a task and calculate the scores for the miner responses"""
        if not task.miner_responses:
            logger.warning("📝 No miner responses, skipping task")
            return {}

        hotkey_to_scores = {}
        # NOTE: @scoring, see here for unpacking
        try:
            updated_miner_responses = Scoring.calculate_score(
                validator_task=task.validator_task,
                miner_responses=task.miner_responses,
            )

            # FIXME: to align logic here and in `_prepare_scoring_result`
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
                return {}

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
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return {}

        logger.info(
            f"📝 Received {len(task.miner_responses)} responses from miners. "
            f"Processed {len(hotkey_to_completion_responses.keys())} responses for scoring."
        )

        return hotkey_to_scores

    async def block_updater(self):
        while True:
            block = await self.kami.get_current_block()
            if block and block != self.block:
                self.block = block
                logger.debug(f"Updated block to {self._block}")

            if os.getenv("FAST_MODE"):
                continue

            logger.info(
                f"Updated block to {self.block}"
            )  # log new block if non fast_mode

            await asyncio.sleep(12)

    async def _extract_miners_hotkey_uid(
        self, batch: list[SyntheticTaskSynapse], metagraph: SubnetMetagraph
    ) -> list[tuple[str, int | None]]:
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
            hotkey = (
                miner_response.miner_hotkey if miner_response.miner_hotkey else "None"
            )

            try:
                uid: int | None = metagraph.hotkeys.index(hotkey)
                miner_uids.append((hotkey, uid))
            except ValueError:
                miner_uids.append((hotkey, None))

        return miner_uids

    def _retrieve_axons(self, uids: list[int] = []) -> list[AxonInfo]:
        # Return miner UIDs based on stakes
        logger.debug(f"Retrieving axons for uids: {uids}")

        miner_axons: list[AxonInfo] = []
        for uid, axon in enumerate(self.metagraph.axons):
            if uids and uid not in uids:
                continue

            if not axon.ip or not axon.port:
                continue

            hotkey = self.metagraph.hotkeys[uid]

            # TODO: misleading async
            eff_stake = aget_effective_stake(hotkey, self.metagraph)
            if (
                not get_config().ignore_min_stake
                and eff_stake > ValidatorConstant.VALIDATOR_MIN_STAKE
            ):
                logger.debug(
                    f"{hotkey}, effective stake: {eff_stake} exceeds threshold of {ValidatorConstant.VALIDATOR_MIN_STAKE} to be considered miner"
                )
                continue
            miner_axons.append(axon)

        return miner_axons

    def _classify_miner_results(
        self,
        batch: list[SyntheticTaskSynapse],
        updated_miner_responses: list[SyntheticTaskSynapse],
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

    async def get_combined_score(self) -> torch.Tensor:
        """Combination of both synthetic task score and HFL task score

        Returns:
            torch.FloatTensor: Combined score tensor
        """
        # TODO: shift these to a config
        synthetic_score_weight = 0.5
        hfl_score_weight = 0.5
        logger.info(
            f"Synthetic score: {self.synthetic_score.shape=} {self.synthetic_score=} {len(self.synthetic_score.tolist())=}"
        )
        logger.info(
            f"HFL scores: {self.hfl_scores.shape=} {self.hfl_scores=} {len(self.hfl_scores.tolist())=}"
        )
        async with self._scores_alock:
            # TODO: assignment of self.hfl_score
            assert (
                self.synthetic_score.shape == self.hfl_scores.shape
            ), "Scores and HFL scores must be the same shape"
            combined_score = (
                synthetic_score_weight * self.synthetic_score
                + hfl_score_weight * self.hfl_scores
            )

        return combined_score

    async def _decide_hfl_continuation(self, sf_task_id: str, hfl_state: HFLState):
        """
        Decide whether to continue or end the HFL process after scoring.
        Updates the HFL state accordingly.

        Args:
            sf_task_id: ID of the Score Feedback task that was scored
            hfl_state: Current HFL state

        Returns:
            bool: True if the HFL will continue, False if it's completed
        """
        try:
            # Determine whether to continue the HFL cycle
            continue_hfl, reason = await should_continue_hfl(
                hfl_state=hfl_state,
                latest_sf_task_id=sf_task_id,
                max_iterations=HFLConstants.MAX_ITERATIONS.value,
                consensus_threshold=HFLConstants.CONSENSUS_THRESHOLD.value,
            )

            if continue_hfl:
                # Update HFL state to TF_SCHEDULED
                await HFLManager.update_state(
                    hfl_state_id=hfl_state.id,
                    updates=HFLStateUpdateInput(status=HFLStatusEnum.TF_SCHEDULED),
                    event_data=TextFeedbackEvent(
                        type=HFLStatusEnum.TF_SCHEDULED,
                        task_id=sf_task_id,
                        iteration=hfl_state.current_iteration,
                        message=f"Continuing HFL: {reason}",
                    ),
                )
                logger.info(
                    f"HFL will continue to iteration {hfl_state.current_iteration + 1}: {reason}"
                )
            else:
                # Update HFL state to HFL_COMPLETED
                await HFLManager.update_state(
                    hfl_state_id=hfl_state.id,
                    updates=HFLStateUpdateInput(status=HFLStatusEnum.HFL_COMPLETED),
                    event_data=TextFeedbackEvent(
                        type=HFLStatusEnum.HFL_COMPLETED,
                        task_id=sf_task_id,
                        iteration=hfl_state.current_iteration,
                        message=f"HFL completed: {reason}",
                    ),
                )
                logger.info(
                    f"HFL completed after iteration {hfl_state.current_iteration}: {reason}"
                )

            return continue_hfl

        except Exception as e:
            logger.error(f"Error deciding HFL continuation for task {sf_task_id}: {e}")
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return False  # Default to not continuing in case of error

    async def send_scoring_result_to_miners(self, task_id: str) -> bool:
        """
        Prepare and send scoring results back to miners for a specific task.

        Args:
            task_id: The ID of the task to send results for

        Returns:
            True if successful, False otherwise
        """
        try:
            participating_hotkeys, scores_list = await self._prepare_scoring_result(
                task_id
            )

            if not participating_hotkeys or not scores_list:
                logger.warning(f"No participating hotkeys or scores for task {task_id}")
                return False

            await self._send_scores(
                validator_task_id=task_id,
                hotkeys=participating_hotkeys,
                scores=scores_list,
            )

            logger.info(f"Sent score results back to miners for task {task_id}")
            return True
        except Exception as e:
            logger.error(f"Error sending scoring results for task {task_id}: {e}")
            return False

    async def _prepare_scoring_result(
        self, task_id: str
    ) -> tuple[list[str], list[Scores]]:
        """
        Prepare scoring results for a specific task to send back to miners.

        Args:
            task_id: The ID of the task (TF or SF) to prepare results for

        Returns:
            Tuple containing (participating_hotkeys, scores_list)
        """
        # Get the task with its completions and miner responses with their scores
        task = await ORM.get_validator_task_by_id(
            task_id,
            include={
                "completions": {
                    "include": {"criterion": {"include": {"scores": True}}}
                },
                "miner_responses": True,
            },
        )

        if not task or not task.miner_responses or not task.completions:
            logger.warning(
                f"Cannot prepare scoring result for task {task_id}: task or responses, or completions not found"
            )
            return [], []

        participating_hotkeys = []
        scores_list = []

        for miner_response in task.miner_responses:
            hotkey = miner_response.hotkey
            participating_hotkeys.append(hotkey)

            # Use the mapper to convert to CompletionResponse objects
            completion_responses = map_miner_response_to_completion_responses(
                miner_response=miner_response,
                completions=task.completions,
            )

            # Extract scores from completion responses for this miner
            if completion_responses:
                for completion in completion_responses:
                    if (
                        completion.criteria_types
                        and completion.criteria_types[0].scores
                    ):
                        scores_list.append(completion.criteria_types[0].scores)

        return participating_hotkeys, scores_list

    def _resize_score_tensor(
        self,
        current_tensor: torch.Tensor,
    ) -> torch.Tensor:
        """
        Resize a score tensor to match current metagraph size while preserving existing scores.

        Args:
            current_tensor: The tensor to resize

        Returns:
            torch.Tensor: Resized tensor with preserved scores
        """
        new_tensor = torch.zeros(len(self.metagraph.hotkeys))
        min_size = min(len(current_tensor), len(self.metagraph.hotkeys))
        new_tensor[:min_size] = current_tensor[:min_size]
        return new_tensor
