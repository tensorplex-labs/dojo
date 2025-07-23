import aiohttp

from typing import Optional, Dict, Any


class ExternalTaskPool:
    def __init__(self, config, max_workers: int = 10):
        self.max_workers = max_workers
        self.url = f"{EXTERNAL_TASK_POOL_HOST}/api/v1"
        self.session = aiohttp.ClientSession()

    async def close(self):
        if self.session is not None:
            await self.session.close()

    async def reconnect(self):
        if self.session is not None:
            await self.session.close()
        self.session = aiohttp.ClientSession()

    async def fetch_task(self, params: dict = None) -> Dict[str, Any]:
        try:
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

    async def health(self) -> Dict[str, Any]:
        try:
            async with self.session.get(f"{self.url}/health") as response:
                if response.status != 200:
                    return {}
                return await response.json()
        except aiohttp.ClientError as e:
            raise Exception(f"HTTP error while checking health: {e}")
        except Exception as e:
            raise Exception(f"Error while checking health: {e}")
