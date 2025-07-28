import asyncio
import aiohttp
import os
from datetime import datetime, timedelta, timezone

from typing import List, Dict, Any
from loguru import logger

from neurons.validator import Validator
from dojo.objects import ObjectManager
from dojo.protocol import (
    SyntheticTaskSynapse,
    CompletionResponse,
    ScoreCriteria,
    TaskTypeEnum,
    ThreeDAssets,
)
from dojo.utils import source_dotenv, get_new_uuid
from dojo.external_tasks_pool.types import Task, ThreeDTaskMetadata

source_dotenv()


class ExternalTaskPool:
    def __init__(self, max_workers: int = 10):
        self.config = ObjectManager.get_config()
        self.max_workers = max_workers
        self.url = f"{os.getenv('EXTERNAL_TASK_POOL_HOST')}/api/v1"
        self.session = aiohttp.ClientSession()

    async def _close(self):
        if self.session is not None:
            await self.session.close()

    async def _reconnect(self):
        if self.session is not None:
            await self.session.close()
        self.session = aiohttp.ClientSession()

    async def _fetch_task(self, params: dict = None) -> Dict[str, Any]:
        try:
            if not self.session or self.session.closed:
                await self._reconnect()
            if params is None:
                params = {}
            async with self.session.get(f"{self.url}/tasks", params=params) as response:
                if response.status != 200:
                    raise Exception(
                        f"Failed to fetch task from {self.url}: {response.status}"
                    )
                return await response.json()
        except aiohttp.ClientError as e:
            raise Exception(f"HTTP error while fetching task: {e}")
        except Exception as e:
            raise Exception(f"Error while fetching task: {e}")

    async def _health(self) -> Dict[str, Any]:
        try:
            if not self.session or self.session.closed:
                await self._reconnect()
            async with self.session.get(
                f"{os.getenv('EXTERNAL_TASK_POOL_HOST')}/health"
            ) as response:
                if response.status != 200:
                    return {}
                return await response.json()
        except aiohttp.ClientError as e:
            logger.error(f"HTTP error while checking health: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error while checking health: {e}")
            return {}

    async def get_task(self) -> List[Task]:
        try:
            health = await self._health()
            if not health.get("success", False):
                raise Exception("External Task Pool is not healthy")

            params = {"unscored": "true"}
            response = await self._fetch_task(params=params)

            if not response.get("success", False):
                logger.info("No tasks available from external pool")
                return []

            # Extract tasks from response data
            tasks_data = response.get("data", [])
            if not tasks_data:
                logger.info("No task data in response")
                return []

            result = []
            for task_data in tasks_data.get("tasks", []):
                try:
                    print(f"Task data: {task_data}")
                    task_obj = Task(**task_data)
                    result.append(task_obj)
                except Exception as e:
                    logger.error(f"Error parsing task data: {e}")
                    continue

            return result
        except Exception as e:
            logger.error(f"Error in ExternalTaskPool run: {e}")
            raise e
        finally:
            await self._close()

    def _convert_task_to_synapse(self, task: Task) -> SyntheticTaskSynapse:
        """Convert an external Task to SyntheticTaskSynapse format.

        Args:
            task: Task from external pool

        Returns:
            SyntheticTaskSynapse ready to be sent to miners
        """
        # Create CompletionResponse objects from ground truth items
        # Each item in ground_truth represents a model's 3D generation that needs to be scored
        completion_responses = []

        # Create a completion response for each model in ground truth
        for model_id, score in task.task_metadata.ground_truth.items():
            # Extract a meaningful model name from the ID
            completion = CompletionResponse(
                model=model_id,
                completion=ThreeDAssets(
                    url=f"{os.getenv('B2_ENDPOINT')}/{'B2_BUCKET_NAME'}/{task.id}/{model_id}.spz"
                ),
                completion_id=get_new_uuid(),  # Use the original ID as completion_id
                score=None,  # Miners will provide the score
                criteria_types=[
                    ScoreCriteria(
                        min=0.0,
                        max=10.0,  # Assuming 0-10 scale based on the task data
                    )
                ],
            )
            completion_responses.append(completion)

        # Set expiration time (24 hours from now)
        expire_at = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()

        # Create the synapse
        synapse = SyntheticTaskSynapse(
            task_id=task.id,
            prompt=task.task_metadata.prompt,
            task_type=TaskTypeEnum.TEXT_TO_THREE_D,
            expire_at=expire_at,
            completion_responses=completion_responses,
            ground_truth=task.task_metadata.ground_truth,
        )

        return synapse

    async def _update_task_sent_status(self, task_id: str) -> bool:
        """
        Update the task's sent status in the external task pool API.

        Args:
            task_id: The ID of the task to mark as sent

        Returns:
            bool: True if successfully updated, False otherwise
        """
        try:
            if not self.session or self.session.closed:
                await self._reconnect()

            url = f"{self.url}/tasks/{task_id}/sent"
            async with self.session.put(url) as response:
                if response.status == 200:
                    logger.info(f"Successfully marked task {task_id} as sent")
                    return True
                else:
                    logger.error(
                        f"Failed to mark task {task_id} as sent: HTTP {response.status}"
                    )
                    return False
        except aiohttp.ClientError as e:
            logger.error(f"HTTP error while updating task sent status: {e}")
            return False
        except Exception as e:
            logger.error(f"Error updating task sent status: {e}")
            return False

    async def run(self, validator: Validator) -> None:
        while True:
            try:
                # Check if there are active miners
                active_miners = validator._active_miner_uids
                if not active_miners:
                    logger.info("No active miners found for external tasks")
                    await asyncio.sleep(10)
                    continue

                # Fetch tasks from external pool
                tasks = await self.get_task()

                if not tasks:
                    logger.info("No tasks available from external pool")
                    await asyncio.sleep(60)  # Wait before retrying
                    continue

                logger.info(f"Fetched {len(tasks)} tasks from the external task pool")

                # Filter out already sent tasks based on sent_status field
                new_tasks = []
                for task in tasks:
                    if not task.sent_status:
                        new_tasks.append(task)
                    else:
                        logger.debug(f"Skipping already sent task {task.id}")

                if not new_tasks:
                    logger.info(
                        "No new tasks to process (all fetched tasks were already sent)"
                    )
                    await asyncio.sleep(60)
                    continue

                logger.info(
                    f"Processing {len(new_tasks)} new tasks out of {len(tasks)} fetched"
                )

                # Convert and send new tasks to miners
                for task in new_tasks:
                    try:
                        synapse = self._convert_task_to_synapse(task)
                        logger.info(
                            f"Processing external task {task.id} of type {task.task_type}"
                        )

                        # Send to miners using validator's method
                        # This follows the same pattern as synthetic tasks
                        await validator.send_request(
                            synapse=synapse,
                            ground_truth=task.task_metadata.ground_truth,
                        )

                        # Update sent status via API
                        sent_updated = await self._update_task_sent_status(task.id)
                        if sent_updated:
                            logger.info(
                                f"Successfully sent task {task.id} to miners and updated sent status"
                            )
                        else:
                            logger.warning(
                                f"Task {task.id} sent to miners but failed to update sent status in API"
                            )

                    except Exception as e:
                        logger.error(f"Error processing task {task.id}: {e}")
                        continue

                await asyncio.sleep(60)  # wait before polling
            except Exception as e:
                logger.error(f"Error in ExternalTaskPool run: {e}")
                await asyncio.sleep(60)
