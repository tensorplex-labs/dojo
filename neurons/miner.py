import asyncio
import os
import time
import traceback
from datetime import datetime
from http import HTTPStatus
from typing import Dict, Tuple

import bittensor
from bittensor.utils.networking import ip_to_int, ip_version
from fastapi import HTTPException
from loguru import logger

from commons.objects import ObjectManager
from commons.utils import aget_effective_stake, aobject, get_epoch_time
from commons.worker_api.dojo import DojoAPI
from dojo.chain import parse_block_headers
from dojo.constants import MinerConstant, ValidatorConstant
from dojo.kami import AxonInfo, Kami, ServeAxonPayload, SubnetMetagraph
from dojo.messaging import HOTKEY_HEADER, PydanticModel, Request, Server
from dojo.protocol import (
    Heartbeat,
    ScoreCriteria,
    ScoringResult,
    SyntheticTaskSynapse,
    TaskResult,
    TaskResultSynapse,
    TextCriteria,
)
from dojo.utils import BoundedDict
from dojo.utils.config import get_config


def optimize_payload_for_transport(synapse: SyntheticTaskSynapse):
    if synapse.completion_responses:
        for response in synapse.completion_responses:
            response.completion = None
    return synapse


class Miner(aobject):
    async def __init__(self):
        self.config = ObjectManager.get_config()
        logger.info(self.config)

        self.kami: Kami = Kami()
        logger.info(f"Connecting to kami: {self.kami.url}")

        logger.info("Setting up bittensor objects....")
        self.wallet = bittensor.wallet(config=self.config)
        logger.info(f"Wallet: {self.wallet}")
        # TODO: replace axon this once all functions done
        self.server = Server()
        self.axon = bittensor.axon(wallet=self.wallet, port=self.config.axon.port)
        logger.info(f"Axon: {self.axon}")

        await self.init_metagraphs()

        # Each miner gets a unique identity (UID) in the network for differentiation.
        self.uid: int = self.subnet_metagraph.hotkeys.index(
            self.wallet.hotkey.ss58_address
        )

        logger.info(
            f"Running neuron on subnet: {self.config.netuid} with uid {self.uid}"
        )

        logger.info("Attaching forward function to miner axon.")
        # TODO: remove completely...
        self.axon.attach(
            forward_fn=self.forward_score_result,
            blacklist_fn=self.blacklist_score_result_request,
        )

        async def heartbeat_adapter(request: Request, synapse: Heartbeat):
            blacklist_reason = self.blacklist_function(request, synapse)
            if blacklist_reason:
                # we've received the req, but you're blacklisted and don't retry
                raise HTTPException(status_code=HTTPStatus.OK, detail=blacklist_reason)

            return await self.heartbeat_handler(request, synapse)

        self.server.serve_synapse(synapse=Heartbeat, handler=heartbeat_adapter)

        async def synthetic_task_adapter(
            request: Request, synapse: SyntheticTaskSynapse
        ):
            blacklist_reason = self.blacklist_function(request, synapse)
            if blacklist_reason:
                # we've received the req, but you're blacklisted and don't retry
                raise HTTPException(status_code=HTTPStatus.OK, detail=blacklist_reason)

            return await self.synthetic_task_handler(request, synapse)

        self.server.serve_synapse(
            synapse=SyntheticTaskSynapse, handler=synthetic_task_adapter
        )

        # TODO: score result request
        async def task_result_adapter(request: Request, synapse: TaskResultSynapse):
            blacklist_reason = self.blacklist_function(request, synapse)
            if blacklist_reason:
                # we've received the req, but you're blacklisted and don't retry
                raise HTTPException(status_code=HTTPStatus.OK, detail=blacklist_reason)

            return await self.task_result_handler(request, synapse)

        self.server.serve_synapse(
            synapse=TaskResultSynapse, handler=task_result_adapter
        )

        self.vali_to_dojo_task_id: BoundedDict = BoundedDict(max_size=1000)
        # log all incoming requests
        self.hotkey_to_request: Dict[str, SyntheticTaskSynapse] = {}

    async def start_server(self):
        """Wrapper around starting the server so that a different process may
        acquire the task handle"""
        await self.server.initialise(port=self.config.axon.port)  # type: ignore

    async def init_metagraphs(self):
        logger.info("Performing async init for miner")

        self.block = await self.kami.get_current_block()
        # The metagraph holds the state of the network, letting us know about other validators and miners.
        self.subnet_metagraph: SubnetMetagraph = await self.kami.get_metagraph(
            self.config.netuid  # type: ignore
        )
        self.root_metagraph: SubnetMetagraph = await self.kami.get_metagraph(0)

        # Check if the miner is registered on the Bittensor network before proceeding further.
        await self.check_registered()
        logger.info(f"Kami initialized, {self.kami.url}")
        logger.info(f"Root metagraph initialized, {self.root_metagraph}")
        logger.info(f"Subnet metagraph initialized, {self.subnet_metagraph}")

    async def run(self):
        """
        Initiates and manages the main loop for the miner on the Bittensor network. The main loop handles graceful shutdown on keyboard interrupts and logs unforeseen errors.

        This function performs the following primary tasks:
        1. Check for registration on the Bittensor network.
        2. Starts the miner's axon, making it active on the network.
        3. Periodically resynchronizes with the chain; updating the metagraph with the latest network state and setting weights.

        During each epoch of its operation, the miner waits for new blocks on the Bittensor network, updates its
        knowledge of the network (metagraph), and sets its weights. This process ensures the miner remains active
        and up-to-date with the network's latest state.

        Note:
            - The function leverages the global configurations set during the initialization of the miner.
            - The miner's axon serves as its interface to the Bittensor network, handling incoming and outgoing requests.

        Raises:
            KeyboardInterrupt: If the miner is stopped by a manual interruption.
            Exception: For unforeseen errors during the miner's operation, which are logged for diagnosis.
        """

        # manually always register and always sync metagraph when application starts
        await self.resync_metagraph()
        await self.sync()

        # Serve passes the axon information to the network + netuid we are hosting on.
        # This will auto-update if the axon port of external ip have changed.
        logger.info(f"Serving miner axon {self.axon} with netuid: {self.config.netuid}")

        axon_payload = ServeAxonPayload(
            netuid=self.config.netuid,
            port=self.axon.external_port,
            ip=ip_to_int(self.axon.external_ip),
            ipType=ip_version(self.axon.external_ip),
            protocol=ip_version(self.axon.external_ip),
            version=1,
        )

        # serve_success = await serve_axon(self.subtensor, self.axon, self.config)

        if not await self.check_if_axon_served(axon_payload):
            serve_success = await self.kami.serve_axon(axon_payload)
            if serve_success.get("statusCode", None) == 200:
                logger.success("Successfully served axon for miner!")
            else:
                logger.error(
                    f"Failed to serve axon for miner, exiting with error message: {serve_success.get('message')}"
                )
                exit()
        else:
            logger.info("Axon already served, no need to serve again.")

        # Start  starts the miner's axon, making it active on the network.
        # TODO: disable this so we can bind axon.port
        # self.axon.start()

        logger.info(f"Miner starting at block: {str(self.block)}")

        # This loop maintains the miner's operations until intentionally stopped.
        try:
            while True:
                # Sync metagraph and potentially set weights.
                await self.sync()
                await asyncio.sleep(12)

        # If someone intentionally stops the miner, it'll safely terminate operations.
        except KeyboardInterrupt:
            logger.success("Miner killed by keyboard interrupt.")
            await self._cleanup()
            exit()

        # In case of unforeseen errors, the miner will log the error and continue operations.
        except Exception:
            logger.error(traceback.format_exc())
        finally:
            await self._cleanup()

    async def _cleanup(self):
        self.axon.stop()
        await self.server.shutdown()
        await self.kami.close()

    async def heartbeat_handler(
        self, request: Request, synapse: Heartbeat
    ) -> Heartbeat:
        caller_hotkey = request.headers.get(HOTKEY_HEADER)
        logger.info(f"⬇️ Received heartbeat synapse from {caller_hotkey}")
        synapse.ack = True
        logger.info(f"⬆️ Respondng to heartbeat synapse: {synapse}")
        return synapse

    async def forward_score_result(self, synapse: ScoringResult) -> ScoringResult:
        logger.info("Received scoring result from validators")
        try:
            # Validate that synapse is not None and has the required fields
            if not synapse or not synapse.hotkey_to_completion_responses:
                logger.error(
                    "Invalid synapse object or missing hotkey_to_completion_responses attribute."
                )
                return synapse

            miner_completion_responses = synapse.hotkey_to_completion_responses.get(
                self.wallet.hotkey.ss58_address, None
            )
            if miner_completion_responses is None:
                logger.error(
                    f"Miner hotkey {self.wallet.hotkey.ss58_address} not found in scoring result but yet was sent the result"
                )
                return synapse

            # Log shared scores once (from first completion that has them)
            shared_scores_logged = False

            # Log scores for each completion response
            for idx, completion in enumerate(miner_completion_responses):
                for criteria in completion.criteria_types:
                    if isinstance(criteria, ScoreCriteria) and criteria.scores:
                        scores = criteria.scores
                        # Log shared scores only once
                        if not shared_scores_logged:
                            logger.info(
                                f"Task {synapse.task_id} shared scores:"
                                f"\n\tGround Truth Score: {scores.ground_truth_score}"
                                f"\n\tCosine Similarity: {scores.cosine_similarity_score}"
                                f"\n\tNormalised Cosine Similarity: {scores.normalised_cosine_similarity_score}"
                                f"\n\tCubic Reward Score: {scores.cubic_reward_score}"
                                f"\n\tHFL Score: {scores.icc_score}"
                            )
                            shared_scores_logged = True

                        # Log individual scores for each completion
                        logger.info(
                            f"Completion {idx + 1} scores:"
                            f"\n\tRaw Score: {scores.raw_score}"
                            f"\n\tNormalised Score: {scores.normalised_score}"
                        )
                    elif isinstance(criteria, TextCriteria) and criteria.score:
                        logger.info(
                            f"Completion {idx + 1} text feedback:"
                            f"\n\tText Feedback Score: {criteria.score.tf_score}"
                        )

        except KeyError as e:
            logger.error(f"KeyError in forward_result: {e}")
        except Exception as e:
            logger.error(f"Error in forward_result: {e}")

        return synapse

    async def synthetic_task_handler(
        self, request: Request, synapse: SyntheticTaskSynapse
    ) -> SyntheticTaskSynapse:
        # Validate that synapse, dendrite, dendrite.hotkey, and response are not None
        caller_hotkey = request.headers.get(HOTKEY_HEADER)
        synapse_name = synapse.__class__.__name__
        logger.info(
            f"⬇️ Received {synapse_name} from {caller_hotkey} with expire_at: {synapse.expire_at}"
        )
        if caller_hotkey:
            self.hotkey_to_request[caller_hotkey] = synapse

        if not synapse.completion_responses:
            raise HTTPException(
                status_code=HTTPStatus.OK,
                detail="Invalid synapse: missing completion_responses",
            )

        try:
            if task_ids := await DojoAPI.create_task(synapse):
                dojo_task_id = task_ids[0]
                # TODO: actually we don't even need this, since LLM API makes it irrelevant
                # touchpoints: validator db as well
                synapse.dojo_task_id = dojo_task_id
                self.vali_to_dojo_task_id[synapse.task_id] = dojo_task_id
                synapse = optimize_payload_for_transport(synapse)
            else:
                logger.error("Failed to create task: no task IDs returned")

        except Exception as e:
            logger.error(
                f"Error processing validator task id: {synapse.task_id}: {str(e)}"
            )
            logger.debug(traceback.print_exc())

        return synapse

    async def task_result_handler(
        self, request: Request, synapse: TaskResultSynapse
    ) -> TaskResultSynapse:
        """Handle a TaskResultRequest from a validator, fetching the task result from the DojoAPI."""
        caller_hotkey = request.headers.get(HOTKEY_HEADER)
        synapse_name = synapse.__class__.__name__
        logger.info(f"⬇️ Received {synapse_name} from {caller_hotkey}")
        if not synapse.validator_task_id:
            message = (
                f"validator_task_id should not be empty {synapse.validator_task_id}"
            )
            logger.error(message)
            raise HTTPException(status_code=HTTPStatus.OK, detail=message)

        try:
            dojo_task_id = self.vali_to_dojo_task_id.get(synapse.validator_task_id)
            if not dojo_task_id:
                message = f"Did not serve request from validator with {synapse.validator_task_id}"
                logger.error(message)
                raise HTTPException(status_code=HTTPStatus.OK, detail=message)

            task_results = await DojoAPI.get_task_results_by_dojo_task_id(dojo_task_id)
            if not task_results:
                logger.debug(
                    f"No task result found for dojo task id: {synapse.validator_task_id}"
                )
                synapse.task_results = []
                return synapse

            synapse.task_results = [
                TaskResult.model_validate(result) for result in task_results
            ]
        except Exception as e:
            logger.error(f"Error while handling {synapse_name}: {e}")
            traceback.print_exc()

        return synapse

    async def blacklist_task_request(
        self, synapse: SyntheticTaskSynapse
    ) -> Tuple[bool, str]:
        return await self.blacklist_function(
            synapse, "validator", "Valid task request received from validator"
        )

    async def blacklist_task_result_request(
        self, synapse: TaskResultSynapse
    ) -> Tuple[bool, str]:
        return await self.blacklist_function(
            synapse, "task result", "Valid task result request from validator"
        )

    async def blacklist_heartbeat_request(self, synapse: Heartbeat) -> Tuple[bool, str]:
        return await self.blacklist_function(
            synapse, "heartbeat", "Valid heartbeat request from validator"
        )

    async def blacklist_score_result_request(
        self, synapse: ScoringResult
    ) -> Tuple[bool, str]:
        return await self.blacklist_function(
            synapse, "scoring result", "Valid scoring result request from validator"
        )

    def blacklist_function(
        self, request: Request, synapse: PydanticModel
    ) -> str | None:
        """
        Common blacklist logic for any forward function to validate an incoming synapse.
        Note: Validate network-level security concerns using the header-based synapse, not the request body data

        Parameters:
            synapse: The incoming synapse object (Heartbeat, ScoringResult, etc.)
            request_tag: A tag used for logging (e.g., "heartbeat", "scoring result").

        Returns:
            str: blacklisted reason
        """
        ip_addr = (
            f"{request.client.host}/{request.client.port}" if request.client else ""
        )
        caller_hotkey = request.headers.get(HOTKEY_HEADER)
        logger.info(
            f"⬇️ Incoming {synapse.__class__.__name__} request from IP: {ip_addr} with hotkey: {caller_hotkey}"
        )

        if not caller_hotkey or caller_hotkey not in self.subnet_metagraph.hotkeys:
            message = f"Blacklisting unrecognized hotkey {caller_hotkey}"
            logger.warning(message)
            return message

        if get_config().ignore_min_stake:
            message = (
                f"Ignoring min stake required: {ValidatorConstant.VALIDATOR_MIN_STAKE} for {caller_hotkey}, "
                "YOU SHOULD NOT SEE THIS when you are running a miner on mainnet"
            )
            logger.warning(message)
            return f"Ignored minimum validator stake requirement of {ValidatorConstant.VALIDATOR_MIN_STAKE}"

        effective_stake = aget_effective_stake(caller_hotkey, self.subnet_metagraph)
        if effective_stake < float(ValidatorConstant.VALIDATOR_MIN_STAKE):
            message = f"Blacklisting hotkey: {caller_hotkey} with insufficient stake, minimum effective stake required: {ValidatorConstant.VALIDATOR_MIN_STAKE}, current effective stake: {effective_stake}"
            logger.warning(message)
            return message

        return None

    async def priority_ranking(self, synapse: SyntheticTaskSynapse) -> float:
        """
        The priority function determines the order in which requests are handled. Higher-priority
        requests are processed before others. Miners may receive messages from multiple entities at
        once. This function determines which request should be processed first.
        Higher values indicate that the request should be processed first.
        Lower values indicate that the request should be processed later.
        """
        current_timestamp = datetime.fromtimestamp(get_epoch_time())
        dt = current_timestamp - datetime.fromtimestamp(synapse.epoch_timestamp)
        priority = float(dt.total_seconds())
        logger.debug(f"Prioritizing {synapse.dendrite.hotkey} with value: {priority}")
        return priority

    async def resync_metagraph(self):
        # Copies state of metagraph before syncing.
        # previous_metagraph = copy.deepcopy(self.subnet_metagraph)

        # Sync the metagraph.
        self.subnet_metagraph = await self.kami.get_metagraph(self.config.netuid)
        self.root_metagraph = await self.kami.get_metagraph(0)

        # Check if the metagraph axon info has changed.
        # if previous_metagraph.axons == self.subnet_metagraph.axons:
        #     return

        logger.info("Metagraph updated")

    async def log_miner_status(self):
        while True:
            logger.info(f"Miner running... block:{str(self.block)} time: {time.time()}")
            await asyncio.sleep(MinerConstant.MINER_STATUS)

    async def sync(self):
        """
        1. check if registered on subnet
        2. check if should sync metagraph
        3. check if should set weights
        """
        await self.check_registered()

        if self.should_sync_metagraph():
            await self.resync_metagraph()

    async def check_registered(self):
        is_member = await self.kami.is_hotkey_registered(
            netuid=int(self.config.netuid),  # type: ignore
            hotkey=str(self.wallet.hotkey.ss58_address),
            # block=int(self.block),
        )
        if not is_member:
            logger.error(
                f"Wallet: {self.wallet} is not registered on netuid {self.config.netuid}."
                f" Please register the hotkey using `btcli s register` before trying again"
            )
            await self._cleanup()
            exit(1)

    def should_sync_metagraph(self):
        """
        Check if enough epoch blocks have elapsed since the last checkpoint to sync.
        """
        # sync every 5 blocks
        return self.block % 5 == 0

    async def check_if_axon_served(self, axon_payload: ServeAxonPayload) -> bool:
        """
        Check if the axon is served successfully.
        """
        hotkey = self.wallet.hotkey.ss58_address
        uid = self.subnet_metagraph.hotkeys.index(hotkey)
        current_axon: AxonInfo = self.subnet_metagraph.axons[uid]
        current_axon_ip: str = current_axon.ip
        current_axon_port = current_axon.port

        if not current_axon_ip:
            logger.info(
                f"Axon not served for hotkey {hotkey} on netuid {self.config.netuid}"
            )
            return False

        if (
            ip_to_int(current_axon_ip) == axon_payload.ip
            and axon_payload.port == current_axon_port
        ):
            return True
        return False

    @property
    def block(self):
        if not hasattr(self, "_block"):
            self._block = 0
        return self._block

    @block.setter
    def block(self, value: int):
        self._block = value

    async def block_headers_callback(self, block: dict):
        logger.trace(f"Received block headers{block}")
        block_header = parse_block_headers(block)
        block_number = block_header.number.to_int()
        self.block = block_number

    async def block_updater(self):
        while True:
            block = await self.kami.get_current_block()
            if block and block != self.block:
                self.block = block
                logger.debug(f"Updated block to {self.block}")

            if os.getenv("FAST_MODE"):
                continue

            logger.info(f"Updated block to {self.block}")

            await asyncio.sleep(12)
