# Essential utilities used everywhere

import os
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone

import numpy as np
import plotext
from loguru import logger
from openai import AsyncOpenAI

from dojo.api_settings import RedisSettings
from dojo.storage.cache import RedisCache


class aobject:
    """Inheriting this class allows you to define an async __init__.

    So you can create objects by doing something like `await MyClass(params)`
    """

    async def __new__(cls, *a, **kw):
        instance = super().__new__(cls)
        await instance.__init__(*a, **kw)
        return instance

    async def __init__(self):
        pass


def terminal_plot(
    title: str, y: np.ndarray, x: np.ndarray | None = None, sort: bool = False
):
    """Plot a scatter plot on the terminal.
    It is crucial that we don't modify the original order of y or x, so we make a copy first.

    Args:
        title (str): Title of the plot.
        y (np.ndarray): Y values to plot.
        x (np.ndarray | None, optional): X values to plot. If None, will use a np.linspace from 0 to len(y).
        sort (bool, optional): Whether to sort the y values. Defaults to False.
    """
    if x is None:
        x = np.linspace(0, len(y), len(y) + 1)

    if sort:
        y_copy = np.copy(y)
        y_copy.sort()
        y = y_copy

    # plot actual points first
    plotext.scatter(x, y, marker="bitcoin", color="orange")  # show the points exactly
    plotext.title(title)
    plotext.ticks_color("red")
    plotext.xfrequency(1)  # Set frequency to 1 for better alignment
    plotext.xticks(x)  # Directly use x for xticks
    plotext.ticks_style("bold")
    plotext.grid(horizontal=True, vertical=True)
    plotext.plotsize(
        width=int(plotext.terminal_width() * 0.75),  # type: ignore[reportOptionalMemberAccess]
        height=int(plotext.terminal_height() * 0.75),  # type: ignore[reportOptionalMemberAccess]
    )
    plotext.canvas_color(color=None)
    plotext.theme("clear")

    plotext.show()
    plotext.clear_figure()


def get_new_uuid():
    return str(uuid.uuid4())


def get_epoch_time():
    return time.time()


def datetime_as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc)


def datetime_to_iso8601_str(dt: datetime) -> str:
    return dt.replace(tzinfo=timezone.utc).isoformat()


def iso8601_str_to_datetime(dt_str: str) -> datetime:
    return datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc)


def loaddotenv(varname: str):
    """Wrapper to get env variables for sanity checking"""
    value = os.getenv(varname)
    if not value:
        raise SystemExit(f"{varname} is not set")
    return value


def log_retry_info(retry_state):
    """Meant to be used with tenacity's before_sleep callback"""
    logger.warning(
        f"Retry attempt {retry_state.attempt_number} failed with exception: {retry_state.outcome.exception()}",
    )


def set_expire_time(expire_in_seconds: int) -> str:
    """
    Sets the expiration time based on the current UTC time and the given number of seconds.

    Args:
        expire_in_seconds (int): The number of seconds from now when the expiration should occur.

    Returns:
        str: The expiration time in ISO 8601 format with 'Z' as the UTC indicator.
    """
    return (
        (datetime.now(timezone.utc) + timedelta(seconds=expire_in_seconds))
        .replace(tzinfo=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


async def validate_openai_config() -> bool:
    """
    Validate OpenAI configuration at startup.
    Returns True if configuration is valid and API is accessible.
    """
    try:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            logger.error("OPENROUTER_API_KEY not found in environment variables")
            return False

        client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )

        from dojo.human_feedback.sanitize import MODERATION_LLM

        # Test API connection with a minimal request
        response = await client.chat.completions.create(
            model=MODERATION_LLM,
            messages=[{"role": "user", "content": "test"}],
        )

        logger.info(f"OpenAI configuration validated successfully: {response}")
        return True

    except Exception as e:
        logger.error(f"Failed to validate OpenAI configuration: {e}")
        return False


async def validate_services() -> bool:
    """Validate all necessary services before startup"""
    try:
        # 1. Check OpenAI/OpenRouter
        logger.info("Validating OpenAI/OpenRouter connection")
        if not await validate_openai_config():
            logger.error("OpenAI/OpenRouter validation failed")
            return False

        # 2. Check Redis using RedisCache
        try:
            logger.info("Validating Redis connection")
            cache = RedisCache(RedisSettings(), is_ssl=False)
            await cache.connect()
            await cache.redis.ping()
            await cache.close()
            logger.info("Redis connection validated successfully")
        except Exception as e:
            logger.error(f"Redis validation failed: {e}")
            return False

        return True
    except Exception as e:
        logger.error(f"Service validation failed: {e}")
        logger.error(traceback.format_exc())
        return False
