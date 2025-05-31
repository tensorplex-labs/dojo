from typing import Awaitable, Callable, Tuple, Type, TypeVar

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_combine,
    wait_exponential,
    wait_random,
)

from dojo.logging import tenacity_retry_log

T = TypeVar("T")


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

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
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
            before_sleep=tenacity_retry_log,
        )

        return tenacity_retry(func)

    return decorator
