class BoundedDict(dict):
    def __init__(self, max_size=100):
        super().__init__()
        self.max_size = max_size

    def __setitem__(self, key, value):
        if key not in self and len(self) >= self.max_size:
            # Remove the oldest key (first inserted)
            oldest_key = next(iter(self))
            del self[oldest_key]
        super().__setitem__(key, value)
