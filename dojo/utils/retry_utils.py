import functools
from typing import Awaitable, Callable, ParamSpec, Tuple, Type, TypeVar

from loguru import logger
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_combine,
    wait_exponential,
    wait_random,
)

T = TypeVar("T")
P = ParamSpec("P")


def async_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    jitter: bool = False,
    exceptions: Type[Exception] | Tuple[Type[Exception], ...] = Exception,
):
    """
    Simple async retry decorator using Tenacity

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        backoff_factor: Exponential backoff multiplier
        jitter: Whether to add random jitter to delays
        exceptions: Exception type(s) to retry on
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        wait_strategy = wait_exponential(
            multiplier=base_delay, max=max_delay, exp_base=backoff_factor
        )

        # NOTE: add 0-1 second jitter
        if jitter:
            wait_strategy = wait_combine(
                wait_strategy,
                wait_random(0, 1),
            )

        tenacity_retry = retry(
            stop=stop_after_attempt(max_retries),
            wait=wait_strategy,
            retry=retry_if_exception_type(exceptions),
            before_sleep=retry_log,
        )

        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return await tenacity_retry(func)(*args, **kwargs)

        return wrapper

    return decorator


def retry_log(retry_state: RetryCallState):
    """Custom retry logger that works well with loguru"""
    func_name = getattr(retry_state.fn, "__name__", "<unknown_function>")
    logger.debug(
        f"Retrying {func_name} attempt {retry_state.attempt_number} "
        f"after {retry_state.seconds_since_start:.1f}s due to: {retry_state.outcome.exception() if retry_state.outcome else ''}"
    )
