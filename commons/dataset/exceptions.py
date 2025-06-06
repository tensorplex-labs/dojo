class FeedbackImprovementError(Exception):
    """Raised when there's an error with the Synthetic API integration."""

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

    pass
