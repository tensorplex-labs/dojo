"""Exceptions for the Human Feedback Loop module."""


class HFLError(Exception):
    """Base class for all Human Feedback Loop exceptions."""

    pass


class NoNewExpiredTasksYet(HFLError):
    """Raised when there are no new expired tasks ready for processing."""

    pass


class HFLProcessingError(HFLError):
    """Raised when there's an error processing feedback loop tasks."""

    pass


class SyntheticAPIError(HFLError):
    """Raised when there's an error with the Synthetic API integration."""

    pass


class InsufficientResponsesError(HFLError):
    """Raised when there aren't enough valid responses to continue."""

    pass
