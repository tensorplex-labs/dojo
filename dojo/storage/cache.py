"""
redis client class to use redis using singleton pattern.
"""

from redis import asyncio as aioredis
from redis.asyncio.client import Redis

from dojo.api_settings import RedisSettings


def build_redis_url(config: RedisSettings, is_ssl: bool = True) -> str:
    """uses redisss for ssl connection; required for production analytics API"""
    host = config.REDIS_HOST
    port = config.REDIS_PORT
    username = config.REDIS_USERNAME
    password = config.REDIS_PASSWORD

    scheme = "rediss" if is_ssl else "redis"
    if username and password:
        return f"{scheme}://{username}:{password}@{host}:{port}"
    elif password:
        return f"{scheme}://:{password}@{host}:{port}"
    else:
        return f"{scheme}://{host}:{port}"


class RedisCache:
    _instance = None
    _anal_prefix_: str = "analytics"
    _upload_key_: str = "uploaded"
    redis: Redis
    config: RedisSettings
    redis_url: str

    def __new__(cls, config: RedisSettings, is_ssl: bool = True):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.config = config
            cls._instance.redis_url = build_redis_url(config, is_ssl)
            cls._instance.redis = aioredis.from_url(url=cls._instance.redis_url)

        return cls._instance

    def _build_key(self, prefix: str, *parts: str) -> str:
        if len(parts) == 0:
            raise ValueError("Must specify at least one redis key")
        return f"{prefix}:{':'.join(parts)}"

    async def connect(self):
        if self.redis is None:
            self.redis = await aioredis.from_url(self.redis_url)

    async def put(self, key: str, value, expire_time: int = 60 * 60 * 24):
        """
        by default will set an expiry time of 1 day
        """
        if self.redis is None:
            await self.connect()
        await self.redis.set(key, value, ex=expire_time)

    async def get(self, key: str):
        if self.redis is None:
            await self.connect()
        value = await self.redis.get(key)
        if value:
            return value
        return None

    async def delete(self, key: str):
        if self.redis is None:
            await self.connect()
        await self.redis.delete(key)

    async def close(self):
        if self.redis is not None:
            await self.redis.aclose()
