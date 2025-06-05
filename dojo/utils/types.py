from enum import Enum


class Mode(str, Enum):
    """Originally started as fast_mode boolean but now used to determine
    the different timings for various tasks like validator sending tasks to
    miners, etc. for testing purposes.

    This should not be used in production!!!
    """

    NORMAL = "normal"
    HIGH = "high"
    MEDIUM = "medium"


class BoundedDict(dict):
    """Small implementation of dictionary with max size to prevent out of
    memory errors."""

    def __init__(self, max_size=100):
        super().__init__()
        self.max_size = max_size

    def __setitem__(self, key, value):
        if key not in self and len(self) >= self.max_size:
            # Remove the oldest key (first inserted)
            oldest_key = next(iter(self))
            del self[oldest_key]
        super().__setitem__(key, value)
