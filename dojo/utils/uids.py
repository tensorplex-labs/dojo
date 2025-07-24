import random
from ast import main

import bittensor as bt

from dojo.constants import BucketConfig
from dojo.utils import get_effective_stake


def is_uid_available(metagraph: bt.metagraph, uid: int) -> bool:
    """Check if uid is available."""
    # filter non serving axons.
    if not metagraph.axons[uid].is_serving:
        return False
    return True


# TODO: refactor to use kami
def is_miner(metagraph: bt.metagraph, uid: int) -> bool:
    """Check if uid is a validator."""
    from dojo import ValidatorConstant

    hotkey = metagraph.hotkeys[uid]
    effective_stake = get_effective_stake(hotkey, metagraph.subtensor)
    return effective_stake < ValidatorConstant.VALIDATOR_MIN_STAKE


def get_bucket_uids(
    miner_uids, bucket_size: int = BucketConfig.BUCKET_SIZE.value
) -> list[list[int]]:
    """
    Get axons for a given bucket size.

    Args:
        bucket_size: The size of the bucket to get axons for

    Returns:
        List of axons for the given bucket size
    """

    if len(miner_uids) < bucket_size:
        return [miner_uids]

    shuffled_uids = miner_uids.copy()
    random.shuffle(shuffled_uids)

    base_size = len(shuffled_uids) // bucket_size
    remainder = len(shuffled_uids) % bucket_size

    buckets = []
    start_idx = 0

    for i in range(bucket_size):
        bucket_size = base_size + (1 if i < remainder else 0)
        end_idx = start_idx + bucket_size
        buckets.append(shuffled_uids[start_idx:end_idx])
        start_idx = end_idx

    return buckets


if __name__ == "__main__":
    import asyncio

    async def main():
        uids = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        print(get_bucket_uids(uids))

    asyncio.run(main())
