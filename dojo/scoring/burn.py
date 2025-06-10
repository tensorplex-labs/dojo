import torch
from kami import SubnetMetagraph

SUBNET_OWNER_HOTKEY = (
    "5EgfUiH6A99dhihMzp7eMM8UDkvmFjCWgM5gnpBN8UgLrVuz"  # gitleaks:allow
)


def build_weights_for_burn(
    metagraph: SubnetMetagraph,
    weights: torch.Tensor,
    uids: list[int],
    factor: float = 0.5,
):
    try:
        burn_uid = metagraph.hotkeys.index(SUBNET_OWNER_HOTKEY)
        burn_amt = 0
        for uid in uids:
            dt = factor * weights[uid]
            burn_amt += dt
            weights[uid] = (1 - factor) * weights[uid]

        weights[burn_uid] = burn_amt
        return weights
    except IndexError as e:
        raise IndexError(
            "Unexpected index error as subnet owner should always be in metagraph"
        ) from e
