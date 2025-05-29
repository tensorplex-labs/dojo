from loguru import logger
from tenacity import RetryCallState


def tenacity_retry_log(retry_state: RetryCallState):
    """Custom retry logger that works well with loguru"""
    func_name = getattr(retry_state.fn, "__name__", "<unknown_function>")
    logger.warning(
        f"Retrying {func_name} attempt {retry_state.attempt_number} "
        f"after {retry_state.seconds_since_start:.1f}s due to: {retry_state.outcome.exception() if retry_state.outcome else ''}"
    )
