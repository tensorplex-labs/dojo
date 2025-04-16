"""
Once code is more modular, this should exist in validator/comms.py <- or a better name
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


async def send_request_to_miners(
    synapse: TaskSynapseObject,
    metagraph: bt.metagraph,
    client: Client,
    semaphore: Semaphore,
) -> list[TaskSynapseObject | BaseException]:
    if not synapse.completion_responses:
        logger.warning("No completion responses to send... skipping")
        return []

    UNSERVED_AXON_IP = "0.0.0.0"
    # TODO: fix pyright typing
    urls: list[str] = [
        f"http://{axon.ip}:{axon.port}"  # pyright: ignore
        for axon in metagraph.axons  # pyright: ignore
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
