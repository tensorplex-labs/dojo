import asyncio
import json
from typing import List

from bittensor.btlogging import logging as logger

from commons.dataset.synthetic import SyntheticAPI
from commons.human_feedback.dojo import DojoAPI
from commons.obfuscation.obfuscation_utils import obfuscate_html_and_js
from commons.utils import set_expire_time
from dojo.protocol import (
    CompletionResponses,
    FeedbackRequest,
    MultiScoreCriteria,
    TaskType,
)


@staticmethod
async def _obfuscate_completion_files(
    completion_responses: List[CompletionResponses],
):
    """Obfuscate HTML files in each completion response."""
    for completion in completion_responses:
        if hasattr(completion.completion, "files"):
            for file in completion.completion.files:
                if file.filename.lower().endswith(".html"):
                    try:
                        original_size = len(file.content)
                        logger.debug(
                            f"Original size of {file.filename}: {original_size} bytes"
                        )
                        file.content = await obfuscate_html_and_js(file.content)
                        obfuscated_size = len(file.content)
                        logger.debug(
                            f"Obfuscated size of {file.filename}: {obfuscated_size} bytes"
                        )
                    except Exception as e:
                        logger.error(f"Error obfuscating {file.filename}: {e}")


async def main():
    data = await SyntheticAPI.get_qa()
    if data is None:
        logger.error("Failed to generate synthetic data")
        return
    model_names = [response.model for response in data.responses]
    if len(set(model_names)) == len(data.responses):
        logger.info("All responses have a unique model key")
        pass
    else:
        logger.warning(
            "Duplicate model names detected. Appending indices to make them unique."
        )
        for index, response in enumerate(data.responses):
            response.model = f"{response.model}_{index}"
            if data.ground_truth and response.completion_id in data.ground_truth.keys():
                ground_truth_rank = data.ground_truth[response.completion_id]
                response.model = f"{response.model}_{ground_truth_rank}"
            else:
                response.completion_id = f"{response.completion_id}_{index}"

    expire_at = set_expire_time(8 * 3600)
    synapse = FeedbackRequest(
        task_type=str(TaskType.CODE_GENERATION),
        criteria_types=[
            MultiScoreCriteria(
                options=[completion.model for completion in data.responses],
                min=1.0,
                max=100.0,
            ),
        ],
        prompt=data.prompt,
        completion_responses=data.responses,
        expire_at=expire_at,
    )

    # Create a duplicate synapse and obfuscate its completion files
    second_synapse = FeedbackRequest(
        task_type=str(TaskType.CODE_GENERATION),
        criteria_types=[
            MultiScoreCriteria(
                options=[completion.model for completion in data.responses],
                min=1.0,
                max=100.0,
            ),
        ],
        prompt=data.prompt,
        completion_responses=data.responses,
        expire_at=expire_at,
    )

    # Create first synapse
    request_size = len(json.dumps(synapse.model_dump()).encode("utf-8"))
    logger.info(f"First Synapse: {request_size} bytes")
    await DojoAPI.create_task(synapse)

    # Can disable the below if want to test without obfuscation
    # Create obfuscated first synapse
    await _obfuscate_completion_files(synapse.completion_responses)
    request_size = len(json.dumps(synapse.model_dump()).encode("utf-8"))
    logger.info(f"First synapse after obfuscation: {request_size} bytes")
    await DojoAPI.create_task(synapse)

    # Create obfuscated second synapse
    duplicate_request_size = len(
        json.dumps(second_synapse.model_dump()).encode("utf-8")
    )
    logger.info(f"Second synapse: {duplicate_request_size} bytes")
    await _obfuscate_completion_files(second_synapse.completion_responses)
    duplicate_request_size = len(
        json.dumps(second_synapse.model_dump()).encode("utf-8")
    )
    logger.info(f"Second synapse after obfuscation: {duplicate_request_size} bytes")
    await DojoAPI.create_task(second_synapse)

    await DojoAPI._http_client.aclose()


asyncio.run(main())
