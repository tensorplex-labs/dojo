"""Type definitions for Human Feedback Loop functionality."""

from enum import Enum, IntEnum
from typing import TypeAlias

from loguru import logger
from pydantic import BaseModel, Field

from dojo.protocol import SanitizationFailureReason


class SanitizationResult(BaseModel):
    """
    response from sanitize_miner_feedback
    """

    is_safe: bool
    sanitized_feedback: str
    reason: SanitizationFailureReason = Field(
        description="Reason for invalid feedback",
        default=SanitizationFailureReason.VALID,
    )


# Constants as Types
class HFLConstants(Enum):
    """Core HFL constants that don't vary with mode"""

    MAX_ITERATIONS = 3
    MIN_THRESHOLD = 50
    MAX_THRESHOLD = 100  # set max for now to trigger HFL tasks more often
    CONSENSUS_THRESHOLD = 100  # set max for now to trigger HFL tasks more often
    TF_WEIGHT = 0.7
    SF_WEIGHT = 0.3
    TF_MAX_RETRY = 3
    TF_MIN_RESPONSES = 3
    TARGET_NUM_MINERS = 7  # target number of miners to send HFL tasks to
    MIN_NUM_MINERS = 3


class BaseHFLInterval(IntEnum):
    """Base timing constants for Human Feedback Loop"""

    TF_CREATE_INTERVAL = 1800  # 30 minutes for initial TF task creation
    TF_UPDATE_INTERVAL = 900  # 15 minutes for Text Feedback updates
    SF_CREATE_INTERVAL = 800  # 13 minutes for Score Feedback task creation
    SF_UPDATE_INTERVAL = 700  # 11 minutes for Score Feedback updates
    NEXT_TF_INTERVAL = 1200  # 20 minutes for creating next Text Feedback tasks
    TASK_DEADLINE = 2 * 60 * 60  # 2 hours


class MediumHFLInterval(IntEnum):
    """Medium-speed timing constants"""

    TF_CREATE_INTERVAL = 660  # 10 minutes
    TF_UPDATE_INTERVAL = 300  # 5 minutes
    SF_CREATE_INTERVAL = 250  # ~4 minutes
    SF_UPDATE_INTERVAL = 230  # ~4 minutes
    NEXT_TF_INTERVAL = 400  # ~7 minutes
    TASK_DEADLINE = 1800  # 30 minutes


class HighHFLInterval(IntEnum):
    """High-speed timing constants"""

    TF_CREATE_INTERVAL = 180  # 3 minutes
    TF_UPDATE_INTERVAL = 90  # 1.5 minutes
    SF_CREATE_INTERVAL = 80  # 80 seconds
    SF_UPDATE_INTERVAL = 70  # 70 seconds
    NEXT_TF_INTERVAL = 120  # 2 minutes
    TASK_DEADLINE = 180  # 3 minutes


# Type Aliases
HFLIntervalType: TypeAlias = BaseHFLInterval | MediumHFLInterval | HighHFLInterval


def get_hfl_interval() -> HFLIntervalType:
    """Get HFL timing constants based on mode"""
    from dojo.utils.config import get_mode

    mode = get_mode()
    logger.info(f"HFLInterval: {mode.lower()}")
    return {
        "normal": BaseHFLInterval,
        "high": HighHFLInterval,
        "medium": MediumHFLInterval,
    }[mode.lower()]


HFLInterval = get_hfl_interval()
