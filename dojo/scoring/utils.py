import numpy as np
import torch


def minmax_scale(tensor: torch.Tensor | np.ndarray) -> torch.Tensor:
    if isinstance(tensor, np.ndarray):
        tensor = torch.from_numpy(tensor)
    min = tensor.min()
    max = tensor.max()

    # If max == min, return a tensor of ones
    if max == min:
        return torch.ones_like(tensor)

    return (tensor - min) / (max - min)
