"""Exceptions for the Human Feedback Loop module."""


class HFLError(Exception):
    """Base class for all Human Feedback Loop exceptions."""

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class NoNewExpiredTasksYet(HFLError):
    """Raised when there are no new expired tasks ready for processing."""

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

    pass


class HFLProcessingError(HFLError):
    """Raised when there's an error processing feedback loop tasks."""

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

    pass


class InsufficientResponsesError(HFLError):
    """Raised when there aren't enough valid responses to continue."""

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

    pass


class HFLStateNotContinuous(Exception):
    """Raised when the HFL States don't follow the sequence of: TF_PENDING, TF_COMPLETED, SF_PENDING, SF_COMPLETED, HFL_COMPLETED"""

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)
