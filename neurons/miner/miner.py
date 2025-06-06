import asyncio
import copy
import os
import time
import traceback
from http import HTTPStatus

import pydantic
from bittensor.utils.networking import ip_to_int, ip_version
from fastapi import HTTPException
from kami import AxonInfo, KamiClient, ServeAxonPayload, SubnetMetagraph
from loguru import logger
from messaging import HOTKEY_HEADER, PydanticModel, Request, Server

from commons.objects import ObjectManager
from commons.utils import aget_effective_stake, aobject
from commons.worker_api.dojo import DojoAPI
from dojo.constants import MinerConstant, ValidatorConstant
from dojo.protocol import (
    Heartbeat,
    ScoreResultSynapse,
    SyntheticTaskSynapse,
    TaskResult,
    TaskResultSynapse,
)
from dojo.utils import get_config

from .types import ServedRequest


def optimize_payload_for_transport(
    synapse: SyntheticTaskSynapse,
) -> SyntheticTaskSynapse:
    synapse_copy = copy.deepcopy(synapse)
    for response in synapse_copy.completion_responses or []:
        response.completion = None
    return synapse_copy


class Miner(aobject):
    async def __init__(self):
        self.config = ObjectManager.get_config()
        logger.info(self.config)

        self.kami: KamiClient = KamiClient(port=self.config.kami.port)
        logger.info(f"Connecting to kami: {self.kami.url}")

        logger.info("Setting up bittensor objects....")
        self.server = Server(kami=self.kami)
        self.keyringpair = await self.kami.get_keyringpair()
        await self.register_synapse_handlers()
        await self.init_metagraphs()
        # log all incoming requests

    async def register_synapse_handlers(self):
        """Register handler functions for server as first parameter for handler
        is currently `self`"""

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

        async def task_result_adapter(request: Request, synapse: TaskResultSynapse):
            blacklist_reason = self.blacklist_function(request, synapse)
            if blacklist_reason:
                # we've received the req, but you're blacklisted and don't retry
                raise HTTPException(status_code=HTTPStatus.OK, detail=blacklist_reason)

            return await self.task_result_handler(request, synapse)

        self.server.serve_synapse(
            synapse=TaskResultSynapse, handler=task_result_adapter
        )

        async def score_result_adapter(request: Request, synapse: ScoreResultSynapse):
            blacklist_reason = self.blacklist_function(request, synapse)
            if blacklist_reason:
                # we've received the req, but you're blacklisted and don't retry
                raise HTTPException(status_code=HTTPStatus.OK, detail=blacklist_reason)
            return await self.score_result_handler(request, synapse)

        self.server.serve_synapse(
            synapse=ScoreResultSynapse, handler=score_result_adapter
        )

    async def start_server(self):
        """Wrapper around starting the blocking call to server that calls
        uvicorn.Serve so that a different process may acquire the task handle"""
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
        logger.info(f"KamiClient initialized, {self.kami.url}")
        logger.info("Root metagraph initialized")
        logger.info("Subnet metagraph initialized")

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
        external_ip = await self.server.get_external_ip()
        uid = self.subnet_metagraph.hotkeys.index(self.keyringpair.hotkey)
        logger.info(f"hotkey: {self.keyringpair.hotkey}, uid: {uid}")
        logger.info(
            f"Broadcasting miner server at: ip: {external_ip}, port: {self.config.axon.port} with netuid: {self.config.netuid}"
        )

        axon_payload = ServeAxonPayload(
            netuid=self.config.netuid,
            port=self.config.axon.port,
            ip=ip_to_int(external_ip),
            ipType=ip_version(external_ip),
            protocol=ip_version(external_ip),
        )

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
        await self.server.close()
        await self.kami.close()

    async def heartbeat_handler(
        self, request: Request, synapse: Heartbeat
    ) -> Heartbeat:
        caller_hotkey = request.headers.get(HOTKEY_HEADER)
        logger.info(f"⬇️ Received heartbeat synapse from {caller_hotkey}")
        synapse.ack = True
        logger.info(f"⬆️ Respondng to heartbeat synapse: {synapse}")
        return synapse

    async def score_result_handler(self, request: Request, synapse: ScoreResultSynapse):
        caller_hotkey = request.headers.get(HOTKEY_HEADER)
        synapse_name = synapse.__class__.__name__
        logger.info(
            f"⬇️ Received {synapse_name} from {caller_hotkey} with {synapse.validator_task_id=}"
        )
        if all(val is None for val in synapse.model_dump().values()):
            logger.warning(f"All scores in {synapse_name} are None")

        logger.info(
            f"Task {synapse.validator_task_id}"
            f"\n\tGround Truth Score: {synapse.scores.ground_truth_score}"
            f"\n\tCosine Similarity: {synapse.scores.cosine_similarity_score}"
            f"\n\tNormalised Cosine Similarity: {synapse.scores.normalised_cosine_similarity_score}"
            f"\n\tCubic Reward Score: {synapse.scores.cubic_reward_score}"
            f"\n\tHFL Score: {synapse.scores.icc_score}"
        )

    async def synthetic_task_handler(
        self, request: Request, synapse: SyntheticTaskSynapse
    ) -> SyntheticTaskSynapse:
        caller_hotkey = request.headers.get(HOTKEY_HEADER)
        synapse_name = synapse.__class__.__name__
        logger.info(
            f"⬇️ Received {synapse_name} from {caller_hotkey} with expire_at: {synapse.expire_at}"
        )

        if not synapse.completion_responses:
            raise HTTPException(
                status_code=HTTPStatus.OK,
                detail="Invalid synapse: missing completion_responses",
            )

        try:
            if task_ids := await DojoAPI.create_task(synapse):
                dojo_task_id = task_ids[0]
                served_request = ServedRequest(
                    validator_task_id=synapse.task_id, dojo_task_id=dojo_task_id
                )
                try:
                    served_request.save()
                    served_request.expire(num_seconds=MinerConstant.REDIS_OM_TTL)
                except pydantic.ValidationError as e:
                    logger.error(e)
                except Exception as e:
                    logger.error(f"Error while trying to set TTL on redis data: {e}")
                synapse.ack = True
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
            served_request = ServedRequest.find(
                ServedRequest.validator_task_id == synapse.validator_task_id
            ).first()
            if not served_request:
                message = f"Did not serve request from validator with {synapse.validator_task_id}"
                logger.error(message)
                raise HTTPException(status_code=HTTPStatus.OK, detail=message)
            dojo_task_id = served_request.dojo_task_id  # type: ignore
            task_results = await DojoAPI.get_task_results_by_dojo_task_id(dojo_task_id)
            if not task_results:
                logger.debug(
                    f"No task result found for {synapse.validator_task_id=} and {dojo_task_id=}"
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
            return None

        effective_stake = aget_effective_stake(caller_hotkey, self.subnet_metagraph)
        if effective_stake < float(ValidatorConstant.VALIDATOR_MIN_STAKE):
            message = f"Blacklisting hotkey: {caller_hotkey} with insufficient stake, minimum effective stake required: {ValidatorConstant.VALIDATOR_MIN_STAKE}, current effective stake: {effective_stake}"
            logger.warning(message)
            return message

        return None

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
            hotkey=str(self.keyringpair.hotkey),
            # block=int(self.block),
        )
        if not is_member:
            logger.error(
                f"Hotkey: {self.keyringpair.hotkey} is not registered on netuid {self.config.netuid}."
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
        hotkey = self.keyringpair.hotkey
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

    async def block_updater(self):
        while True:
            try:
                block = await self.kami.get_current_block()
                if block and block != self.block:
                    self.block = block
                    logger.debug(f"Updated block to {self.block}")

                if os.getenv("FAST_MODE"):
                    continue

                logger.info(f"Updated block to {self.block}")

                await asyncio.sleep(12)
            except Exception as e:
                logger.error(
                    f"Error updating block... Waiting for kami to reset. Error: {e}"
                )
                await asyncio.sleep(5)
