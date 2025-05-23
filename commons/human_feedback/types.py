"""Type definitions for Human Feedback Loop functionality."""

from dataclasses import dataclass


@dataclass
class SanitizationResult:
    """
    response from sanitize_miner_feedback
    """

    is_safe: bool
    sanitized_feedback: str
