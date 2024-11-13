import os
import json
import redis
import traceback
from neurons.miner import Miner
from bittensor.btlogging import logging as logger
from dojo.protocol import (
    FeedbackRequest,
    TaskResultRequest,
    TaskResult,
    Result
)


class MinerSim(Miner):
    def __init__(self):
        super().__init__()
        try:
            host = os.getenv("REDIS_HOST", "localhost")
            port = int(os.getenv("REDIS_PORT", 6379))
            self.redis_client = redis.Redis(
                host=host,
                port=port,
                db=0,
                decode_responses=True
            )
            logger.info("Redis connection established")
            logger.info("Starting Miner Simulator")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def forward_feedback_request(self, synapse: FeedbackRequest) -> FeedbackRequest:
        try:
            # Validate that synapse, dendrite, dendrite.hotkey, and response are not None
            if not synapse or not synapse.dendrite or not synapse.dendrite.hotkey:
                logger.error("Invalid synapse: dendrite or dendrite.hotkey is None.")
                return synapse

            if not synapse.completion_responses:
                logger.error("Invalid synapse: response field is None.")
                return synapse

            # Empty out completion response since not need in simulator
            synapse.completion_responses = []

            synapse.dojo_task_id = synapse.request_id
            self.hotkey_to_request[synapse.dendrite.hotkey] = synapse

            redis_key = f"feedback:{synapse.request_id}"
            await self.redis_client.set(
                redis_key,
                json.dumps(synapse),
                ex=36000  # expire after 10 hours
            )
            logger.info(f"Stored feedback request {synapse.request_id}")

            synapse.ground_truth = {}
            return synapse

        except Exception as e:
            logger.error(f"Error handling FeedbackRequest: {e}")
            traceback.print_exc()
            return synapse

    async def forward_task_result_request(self, synapse: TaskResultRequest) -> TaskResultRequest:
        try:
            logger.info(f"Received TaskResultRequest for task id: {synapse.task_id}")
            if not synapse or not synapse.task_id:
                logger.error("Invalid TaskResultRequest: missing task_id")
                return synapse

            redis_key = f"feedback:{synapse.task_id}"
            request_data = self.redis_client.get(redis_key)
            feedback_request = FeedbackRequest(**request_data)

            if feedback_request:
                task_results = [
                    TaskResult(
                        id=feedback_request.dojo_task_id,
                        status='COMPLETED',
                        result_data=[
                            Result(
                                type=feedback_request.criteria_types[0].type,
                                value=feedback_request.ground_truth
                            )
                        ],
                        task_id=synapse.task_id
                    )
                ]

                synapse.task_results = task_results

                await self.redis_client.delete(redis_key)
                logger.debug(f"Processed task result for task {synapse.task_id}")
            else:
                logger.debug(f"No task result found for task id: {synapse.task_id}")

            return synapse

        except Exception as e:
            traceback.print_exc()
            logger.error(f"Error handling TaskResultRequest: {e}")
            return synapse

    def __del__(self):
        """Cleanup Redis connection on object destruction"""
        try:
            self.redis_client.close()
            logger.info("Redis connection closed")
        except:
            pass
