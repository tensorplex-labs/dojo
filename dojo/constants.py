import os
from enum import Enum, IntEnum


class Mode(str, Enum):
    NORMAL = "normal"
    HIGH = "high"
    MEDIUM = "medium"


def get_mode() -> Mode:
    """Get the current mode from environment or config"""
    from dojo.utils.config import get_config

    mode = get_config().fast_mode
    if not mode:
        return Mode.NORMAL
    return Mode(mode.lower())


class CommonConstants(IntEnum):
    """Constants that don't vary with mode"""

    ANALYTICS_UPLOAD = 65 * 60  # 65 minutes


class HFLCommonConstants(Enum):
    MAX_ITERATIONS = 3
    MIN_THRESHOLD = 50
    MAX_THRESHOLD = 101  # turn back to 90 on mainnet
    CONSENSUS_THRESHOLD = 101  # turn back to 90 on mainnet
    TF_WEIGHT = 0.7
    SF_WEIGHT = 0.3


class BaseValidatorConstants(IntEnum):
    """Base constants for synthetic task execution and monitoring"""

    TASK_DEADLINE = 6 * 60 * 60  # 6 hours
    VALIDATOR_RUN = 900  # 15 minutes
    VALIDATOR_HEARTBEAT = 200
    VALIDATOR_UPDATE_TASK = 600  # 10 minutes
    VALIDATOR_UPDATE_SCORE = 3600  # 1 hour
    BUFFER_PERIOD = 2700  # 45 minutes
    MINER_STATUS = 60
    TASK_MONITORING = 300  # 5 minutes
    DOJO_TASK_MONITORING = 300  # 5 minutes


class MediumValidatorConstants(IntEnum):
    """Synthetic task constants for medium-speed testing mode"""

    TASK_DEADLINE = 1200  # 20 minutes
    VALIDATOR_RUN = 600  # 10 minutes
    VALIDATOR_HEARTBEAT = 60  # 1 minute
    VALIDATOR_UPDATE_SCORE = 600  # 10 minutes
    VALIDATOR_UPDATE_TASK = 120  # 2 minutes
    BUFFER_PERIOD = 300  # 5 minutes
    MINER_STATUS = 600  # 10 minutes
    TASK_MONITORING = 60  # 1 minute
    DOJO_TASK_MONITORING = 60  # 1 minute


class HighValidatorConstants(IntEnum):
    """Synthetic task constants for high-speed testing mode"""

    TASK_DEADLINE = 180  # 3 minutes
    VALIDATOR_RUN = 300  # 5 minutes
    VALIDATOR_HEARTBEAT = 15
    VALIDATOR_UPDATE_SCORE = 120  # 2 minutes
    VALIDATOR_UPDATE_TASK = 30
    BUFFER_PERIOD = 90
    TASK_MONITORING = 15
    DOJO_TASK_MONITORING = 15


class BaseHFLTaskConstants(IntEnum):
    """Base Human Feedback Loop task constants"""

    HFL_TF_CREATE_INTERVAL = 3600  # 1 hour for initial TF task creation
    HFL_TF_UPDATE_INTERVAL = 900  # 15 minutes for Text Feedback updates
    HFL_SF_CREATE_INTERVAL = 800  # 13 minutes for Score Feedback task creation
    HFL_SF_UPDATE_INTERVAL = 700  # 11 minutes for Score Feedback updates
    HFL_NEXT_TF_INTERVAL = 1200  # 20 minutes for creating next Text Feedback tasks
    HFL_TASK_DEADLINE = 5 * 60 * 60  # 5 hours


class MediumHFLTaskConstants(IntEnum):
    """HFL task constants for medium-speed testing mode"""

    HFL_TF_CREATE_INTERVAL = 660  # 10 minutes
    HFL_TF_UPDATE_INTERVAL = 300  # 5 minutes
    HFL_SF_CREATE_INTERVAL = 250  # ~4 minutes
    HFL_SF_UPDATE_INTERVAL = 230  # ~4 minutes
    HFL_NEXT_TF_INTERVAL = 400  # ~7 minutes
    HFL_TASK_DEADLINE = 1800  # 30 minutes


class HighHFLTaskConstants(IntEnum):
    """HFL task constants for high-speed testing mode"""

    HFL_TF_CREATE_INTERVAL = 180  # 3 minutes
    HFL_TF_UPDATE_INTERVAL = 90  # 1.5 minutes
    HFL_SF_CREATE_INTERVAL = 80  # 80 seconds
    HFL_SF_UPDATE_INTERVAL = 70  # 70 seconds
    HFL_NEXT_TF_INTERVAL = 120  # 2 minutes
    HFL_TASK_DEADLINE = 180  # 3 minutes


def get_validator_constants() -> (
    type[BaseValidatorConstants | MediumValidatorConstants | HighValidatorConstants]
):
    mode = get_mode()
    return {
        Mode.NORMAL: BaseValidatorConstants,
        Mode.HIGH: HighValidatorConstants,
        Mode.MEDIUM: MediumValidatorConstants,
    }[mode]


def get_hfl_task_constants() -> (
    type[BaseHFLTaskConstants | MediumHFLTaskConstants | HighHFLTaskConstants]
):
    mode = get_mode()
    return {
        Mode.NORMAL: BaseHFLTaskConstants,
        Mode.HIGH: HighHFLTaskConstants,
        Mode.MEDIUM: MediumHFLTaskConstants,
    }[mode]


class ValidatorCommonConstants(IntEnum):
    """Validator-specific constants"""

    VALIDATOR_MIN_STAKE = int(os.getenv("VALIDATOR_MIN_STAKE", "5000"))
    MINER_STATUS = 60
    VALIDATOR_STATUS = 60


# Export the constants directly
ValidatorConstants = get_validator_constants()
HFLTaskConstants = get_hfl_task_constants()


# Validation
assert (
    ValidatorConstants.VALIDATOR_UPDATE_SCORE.value
    < ValidatorConstants.TASK_DEADLINE.value
)
