"""
Once code is more modular, this should exist in validator/tasks.py <- or a better name
This is meant to contain all logic related to synthetic tasks
"""

import http
import random
from asyncio import Semaphore
from typing import Sequence

import aiohttp
import bittensor as bt
from loguru import logger

from dojo.messaging import Client, StdResponse
from dojo.protocol import (
    TaskSynapseObject,
)


# TODO: actually this can be generic
async def send_synthetic_task(
    synapse: TaskSynapseObject,
    metagraph: bt.metagraph,
    client: Client,
    semaphore: Semaphore,
    active_uids: Sequence[int] = None,  # type: ignore[assignment]
) -> list[TaskSynapseObject | BaseException]:
    """Function to send a request to miners, using the provided metagraph and
    client. The function sends the request to all miners in the metagraph if no
    specified indices are provided, and returns a list of responses.

    Args:
        synapse (TaskSynapseObject): synapse
        metagraph (bt.metagraph): metagraph
        client (Client): client
        semaphore (Semaphore): semaphore
        active_uids (Sequence[int], optional): list of active uids. Defaults to None.

    Returns:
        list[TaskSynapseObject | BaseException]:
    """
    if not synapse.completion_responses:
        logger.warning("No completion responses to send... skipping")
        return []

    UNSERVED_AXON_IP = "0.0.0.0"

    # FIXME: fix pyright typing
    axons: list[bt.AxonInfo] = (  # pyright: ignore
        metagraph.axons  # pyright: ignore
        if not active_uids
        else [metagraph.axons[uid] for uid in active_uids]  # pyright: ignore
    )

    urls: list[str] = [
        f"http://{axon.ip}:{axon.port}"  # pyright: ignore
        for axon in axons  # pyright: ignore
        if axon.ip != UNSERVED_AXON_IP  # pyright: ignore
    ]

    synapses: list[TaskSynapseObject] = []
    for _ in range(len(urls)):
        # shuffle synapse Responses

        shuffled_completions = random.sample(
            synapse.completion_responses,
            k=len(synapse.completion_responses),
        )

        shuffled_synapse = TaskSynapseObject(
            epoch_timestamp=synapse.epoch_timestamp,
            task_id=synapse.task_id,
            prompt=synapse.prompt,
            task_type=synapse.task_type,
            expire_at=synapse.expire_at,
            completion_responses=shuffled_completions,
        )
        synapses.append(shuffled_synapse)

    # NOTE: concurrency is handled by the client logic, just provide the
    # semaphore
    responses: Sequence[
        tuple[aiohttp.ClientResponse | None, StdResponse[TaskSynapseObject] | None]
        | BaseException
    ] = await client.batch_send(urls=urls, models=synapses, semaphore=semaphore)
    all_responses: list[TaskSynapseObject | BaseException] = []
    for miner_uid, r in enumerate(responses):
        if isinstance(r, BaseException):
            logger.error(
                f"Error sending request to miner: {miner_uid} at {urls[miner_uid]}, exception: {r}"
            )
            all_responses.append(r)
        else:
            client_response, miner_response = r
            if (
                client_response
                and client_response.status == http.HTTPStatus.OK
                and miner_response
            ):
                all_responses.append(miner_response.body)

    return all_responses
