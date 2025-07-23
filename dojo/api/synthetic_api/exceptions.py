class FeedbackImprovementError(Exception):
    """Raised when there's an error with the Synthetic API integration."""

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

    pass


class FatalSyntheticGenerationError(Exception):
    """
    Raised when
    - synthetic QA generation still fails even after retry attempts
    - synthetic API health check still fails even after retry attempts
    """

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class SyntheticGenerationError(Exception):
    """Raised when synthetic QA generation fails"""

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)
