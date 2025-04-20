"""
Once code is more modular, this should exist in validator/heartbeats.py <- or a better name
This is meant to contain all logic related to ensuring miners we're about to send
synthetic tasks, etc. are reachable to save bandwidth.
"""

import asyncio
from typing import Sequence

from bittensor.core.async_subtensor import AsyncSubtensor
from bittensor.utils.btlogging import logging as logger

from commons.exceptions import FatalSubtensorConnectionError
from commons.objects import ObjectManager
from commons.utils import aget_effective_stake
from dojo import VALIDATOR_MIN_STAKE


async def get_active_miner_uids(
    subtensor: AsyncSubtensor, semaphore: asyncio.Semaphore = asyncio.Semaphore(20)
) -> Sequence[int]:
    """Retrieves the miner UIDs from the subnet metagraph that are serving and
    checks their stake so they're considered miners."""
    config = ObjectManager.get_config()
    if not subtensor:
        message = (
            "Failed to connect to async subtensor during attempt to extract miner uids"
        )
        logger.error(message)
        raise FatalSubtensorConnectionError(message)

    block = await subtensor.get_current_block()
    subnet_metagraph = await subtensor.metagraph(config.netuid, block=block)
    root_metagraph = await subtensor.metagraph(0, block=block)

    async def _semaphore_get_stake(hotkey: str):
        async with semaphore:
            return await aget_effective_stake(hotkey, root_metagraph, subnet_metagraph)

    tasks = [
        asyncio.create_task(_semaphore_get_stake(hotkey))
        for hotkey in subnet_metagraph.hotkeys
    ]

    effective_stakes = await asyncio.gather(*tasks)

    return [
        uid
        for uid in range(subnet_metagraph.hotkeys)
        if subnet_metagraph.axons[uid].is_serving
        and effective_stakes[uid] < VALIDATOR_MIN_STAKE
    ]
