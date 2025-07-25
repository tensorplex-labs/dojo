import asyncio
import aiohttp
import os

from typing import List, Dict, Any
from loguru import logger

from neurons.validator import Validator
from dojo.objects import ObjectManager

from dojo.utils import source_dotenv
from dojo.external_tasks_pool.types import Task

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
        except Exception as e:
            logger.error(f"Error while checking health: {e}")

    async def get_task(self) -> List[Task]:
        try:
            health = await self._health()
            if not health.get("success", False):
                raise Exception("External Task Pool is not healthy")

            params = {"unscored": "true"}
            tasks = await self._fetch_task(params=params)
            if not tasks.get("success", False):
                print("No tasks available")
                return []
            result = []
            for task in tasks:
                task_data = task.get("data", {})

                if not task_data:
                    print("No task data found")
                    continue
                task_obj = Task(**task_data)
                result.append(task_obj)
            return result
        except Exception as e:
            logger.error(f"Error in ExternalTaskPool run: {e}")
        finally:
            await self._close()

    async def run(self, validator: Validator) -> None:
        while True:
            try:
                # Process the task here
                active_miners = validator._active_miner_uids
                if not active_miners:
                    logger.info("No active miners found")
                    return
                tasks = await self.get_task()
                if not tasks:
                    logger.info("No tasks available")
                    await asyncio.sleep(60)  # Wait before retrying
                    continue
                logger.info(f"Fetched {len(tasks)} tasks from the external task pool")
                await asyncio.sleep(60)  # wait before polling
            except Exception as e:
                logger.error(f"Error in ExternalTaskPool run: {e}")
                await asyncio.sleep(60)
