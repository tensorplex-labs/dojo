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


def get_validator_constants() -> (
    type[BaseValidatorConstants | MediumValidatorConstants | HighValidatorConstants]
):
    mode = get_mode()
    return {
        Mode.NORMAL: BaseValidatorConstants,
        Mode.HIGH: HighValidatorConstants,
        Mode.MEDIUM: MediumValidatorConstants,
    }[mode]


class ValidatorConstant(IntEnum):
    """Validator-specific constants"""

    VALIDATOR_MIN_STAKE = int(os.getenv("VALIDATOR_MIN_STAKE", "5000"))
    MINER_STATUS = 60
    VALIDATOR_STATUS = 60


# Export the constants directly
ValidatorInterval = get_validator_constants()


# Validation
assert (
    ValidatorInterval.VALIDATOR_UPDATE_SCORE.value
    < ValidatorInterval.TASK_DEADLINE.value
)
