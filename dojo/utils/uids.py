import bittensor as bt

from commons.utils import get_effective_stake


def is_uid_available(metagraph: bt.metagraph, uid: int) -> bool:
    """Check if uid is available."""
    # filter non serving axons.
    if not metagraph.axons[uid].is_serving:
        return False
    return True


def is_miner(metagraph: bt.metagraph, uid: int) -> bool:
    """Check if uid is a validator."""
    from dojo import VALIDATOR_MIN_STAKE

    hotkey = metagraph.hotkeys[uid]
    effective_stake = get_effective_stake(hotkey, metagraph.subtensor)
    return effective_stake < VALIDATOR_MIN_STAKE
