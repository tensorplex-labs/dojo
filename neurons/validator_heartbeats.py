"""
Once code is more modular, this should exist in validator/heartbeats.py <- or a better name
This is meant to contain all logic related to ensuring miners we're about to send
synthetic tasks, etc. are reachable to save bandwidth.
"""

import asyncio
from typing import Sequence

import bittensor as bt
from bittensor.core.async_subtensor import AsyncSubtensor
from bittensor.utils.btlogging import logging as logger

from commons.exceptions import (
    FatalSubtensorConnectionError,
)
from commons.objects import ObjectManager
from commons.utils import aget_effective_stake
from dojo import (
    VALIDATOR_MIN_STAKE,
)
from dojo.chain import get_async_subtensor
from dojo.messaging import Client
from dojo.protocol import (
    Heartbeat,
)


async def _get_served_axon_uids(
    subtensor: AsyncSubtensor, semaphore: asyncio.Semaphore
) -> Sequence[int]:
    """Retrieves the UIDs from the subnet metagraph that are serving and
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


async def send_heartbeats(
    client: Client,
    metagraph: bt.metagraph,
    semaphore: asyncio.Semaphore,
) -> list[int]:
    """Perform a health check periodically, sending heartbeats to all miners to
    check which miners are reachable"""
    try:
        subtensor = await get_async_subtensor()
        if not subtensor:
            logger.error("Failed to connect to async subtensor")
            raise FatalSubtensorConnectionError("Failed to connect to async subtensor")

        served_axon_uids = await _get_served_axon_uids(subtensor, semaphore)

        logger.info(f"Sending heartbeats to {len(served_axon_uids)} miner uids")
        axons: list[bt.AxonInfo] = [metagraph.axons[uid] for uid in served_axon_uids]

        urls: list[str] = [
            f"http://{axon.ip}:{axon.port}"  # pyright: ignore
            for axon in axons  # pyright: ignore
            if axon.ip != "0.0.0.0"  # pyright: ignore
        ]
        heartbeats = [Heartbeat() for _ in range(len(urls))]
        responses = await client.batch_send(
            urls=urls, models=heartbeats, semaphore=semaphore, timeout_sec=60
        )

        active_uids: list[int] = []
        for miner_uid, r in enumerate(responses):
            if isinstance(r, BaseException):
                logger.error(
                    f"Error sending heartbeat to miner: {miner_uid} at {urls[miner_uid]}, exception: {r}"
                )
            elif isinstance(r, Heartbeat):
                if r.ack:
                    active_uids.append(miner_uid)
                else:
                    logger.warning(f"Miner {miner_uid} did not acknowledge heartbeat")

        return active_uids
        logger.info(f"⬇️ Heartbeats acknowledged by miners: {sorted(active_uids)}")
    except Exception as e:
        logger.error(f"Error in sending heartbeats: {e}", exc_info=True)
        return []
