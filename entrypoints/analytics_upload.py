"""
analytics_upload.py
    contains code to query and upload analytics data to analytics_endpoint.py
"""

import asyncio
import gc
import json
import os
import traceback
from datetime import datetime, timedelta, timezone
from typing import List

import bittensor as bt
import httpx
from loguru import logger

from commons.exceptions import NoProcessedTasksYet
from commons.objects import ObjectManager
from commons.orm import ORM
from commons.utils import aget_effective_stake, datetime_to_iso8601_str
from database.client import connect_db
from database.prisma.enums import TaskTypeEnum
from database.prisma.models import ValidatorTask
from dojo.constants import AnalyticsConstants, ValidatorConstant
from dojo.kami import Kami, SubnetMetagraph
from dojo.protocol import AnalyticsData, AnalyticsPayload

VALIDATOR_API_BASE_URL = os.getenv("VALIDATOR_API_BASE_URL")


async def _get_all_miner_hotkeys(subnet_metagraph: SubnetMetagraph) -> List[str]:
    """
    returns a list of all metagraph hotkeys with stake less than VALIDATOR_MIN_STAKE
    """
    return [
        hotkey
        for hotkey in subnet_metagraph.hotkeys
        if aget_effective_stake(hotkey, subnet_metagraph=subnet_metagraph)
        < ValidatorConstant.VALIDATOR_MIN_STAKE
    ]


async def _get_task_data(
    validator_hotkey: str,
    all_miner_hotkeys: List[str],
    expire_from: datetime,
    expire_to: datetime,
) -> AnalyticsPayload:
    """
    Retrieves and formats processed validator tasks within a specified time window for analytics upload.
    
    Queries the database for processed `ValidatorTask` records of type `SCORE_FEEDBACK` and `CODE_GENERATION` between `expire_from` and `expire_to`. Each task is converted into an `AnalyticsData` object. For `SCORE_FEEDBACK` tasks with a linked previous task, the corresponding `TextFeedback` task is also included. Returns an `AnalyticsPayload` containing all formatted tasks.
    
    Args:
        validator_hotkey: The hotkey of the validator.
        all_miner_hotkeys: List of miner hotkeys registered to the metagraph at execution time.
        expire_from: Start of the time window for querying processed tasks.
        expire_to: End of the time window for querying processed tasks.
    
    Returns:
        An `AnalyticsPayload` object containing analytics data for all relevant tasks.
    
    Raises:
        NoProcessedTasksYet: If no processed tasks are found in the specified window.
        Exception: For any other errors encountered during processing.
    """
    processed_tasks = []
    await connect_db()
    logger.debug(f"retrieving processed tasks from {expire_from} to {expire_to}")
    try:
        # get processed score_feedback & code_generation tasks in batches from db
        async for task_batch, has_more_batches in ORM.get_processed_tasks(
            expire_from=expire_from,
            expire_to=expire_to,
            task_types=[
                TaskTypeEnum.SCORE_FEEDBACK,
                TaskTypeEnum.CODE_GENERATION,
            ],
        ):
            if task_batch is None:
                continue
            for task in task_batch:
                formatted_task = await _parse_task_to_analytics_data(
                    task, all_miner_hotkeys, validator_hotkey
                )
                processed_tasks.append(formatted_task)

                # if current task is a ScoreFeedback task, also pull the corresponding TextFeedback task
                if task.task_type == TaskTypeEnum.SCORE_FEEDBACK:
                    if task.previous_task_id:
                        tf_task = await ORM.get_task_by_id(task.previous_task_id)
                        if tf_task is None:
                            logger.error(
                                f"TF task not found for ScoreFeedback task: {task.id}"
                            )
                            continue
                        formatted_tf_task = await _parse_task_to_analytics_data(
                            tf_task, all_miner_hotkeys, validator_hotkey
                        )
                        processed_tasks.append(formatted_tf_task)
            # clean up memory after processing all tasks
            if not has_more_batches:
                gc.collect()
                break
        payload = AnalyticsPayload(tasks=processed_tasks)
        return payload

    except NoProcessedTasksYet as e:
        logger.info(f"{e}")
        raise
    except Exception as e:
        logger.error(f"Error when _get_task_data(): {e}")
        raise


async def _post_task_data(payload, hotkey, signature, message) -> httpx.Response | None:
    """
    _post_task_data() is a helper function that:
    1. POSTs task data to analytics API
    2. returns response from analytics API

    @param payload: the analytics data to be sent to analytics API
    @param hotkey: the hotkey of the validator
    @param message: a message that is signed by the validator
    @param signature: the signature generated from signing the message with the validator's hotkey.
    @returns: httpx.Response or None if no response is received.
    """
    _http_client = httpx.AsyncClient(timeout=300)
    try:
        logger.debug("POST-ing analytics data to validator API")
        response = await _http_client.post(
            url=f"{VALIDATOR_API_BASE_URL}/api/v1/analytics/validators/{hotkey}/tasks",
            json=payload.model_dump(mode="json"),
            headers={
                "X-Hotkey": hotkey,
                "X-Signature": signature,
                "X-Message": message,
                "Content-Type": "application/json",
            },
            timeout=300,
        )

        if not response:
            logger.error("_post_task_data() got no response from analytics API")
            return None
        if response.status_code == 200:
            logger.success(f"Successfully uploaded analytics data for hotkey: {hotkey}")
            return response
        else:
            logger.error(f"_post_task_data() response error {response.status_code}")
            logger.error(traceback.format_exc())
            return response
    except Exception as e:
        logger.error(f"Error when _post_task_data(): {str(e)}")
        logger.error(traceback.format_exc())
        raise


async def run_analytics_upload(
    scores_alock: asyncio.Lock,
    expire_from: datetime | None,
    expire_to: datetime,
    kami: Kami,
) -> datetime | None:
    """
    Uploads processed validator analytics data for a specified time window.
    
    Acquires a lock to ensure analytics upload occurs after scoring is complete, collects processed validator task analytics from the database, and uploads the data to the analytics API. Returns the end time of the upload window if successful, or the last successful upload time if no new data was uploaded.
    
    Args:
        scores_alock: Async lock to synchronize with scoring completion.
        expire_from: Start of the time window for querying processed tasks; typically the last successful upload time.
        expire_to: End of the time window for querying processed tasks.
    
    Returns:
        The datetime of the last successful analytics upload, or None if no upload occurred.
    """
    async with scores_alock:
        last_analytics_upload_time = expire_from
        logger.debug(f"Last analytics upload time: {expire_from}")
        # if there is no last analytics upload time, get tasks from 65 minutes ago.
        if expire_from is None:
            expire_from = datetime.now(timezone.utc) - timedelta(
                seconds=AnalyticsConstants.ANALYTICS_UPLOAD
            )

        logger.info(
            f"Uploading analytics data for processed tasks between {expire_from} and {expire_to}"
        )

        config = ObjectManager.get_config()
        wallet = bt.wallet(config=config)
        validator_hotkey = wallet.hotkey.ss58_address

        subnet_metagraph = await kami.get_metagraph(config.netuid)  # type: ignore
        all_miners = await _get_all_miner_hotkeys(subnet_metagraph)

        # 1. collect processed tasks from db
        anal_data: AnalyticsPayload = await _get_task_data(
            validator_hotkey, all_miners, expire_from, expire_to
        )

        # 2. upload data to analytics API
        message = f"Uploading analytics data for validator hotkey: {validator_hotkey}"
        signature = wallet.hotkey.sign(message).hex()

        if not signature.startswith("0x"):
            signature = f"0x{signature}"

        try:
            res = await _post_task_data(
                payload=anal_data,
                hotkey=validator_hotkey,
                signature=signature,
                message=message,
            )

            # if upload was successful, return new upload time
            # else return last successful upload time
            if res and res.status_code == 200:
                return expire_to
            return last_analytics_upload_time

        except NoProcessedTasksYet:
            logger.info("No processed tasks to upload. Skipping analytics upload.")
            return last_analytics_upload_time
        except Exception as e:
            logger.error(f"Error when run_analytics_upload(): {e}")
            raise


async def _parse_task_to_analytics_data(
    task: ValidatorTask, all_miner_hotkeys: List[str], validator_hotkey: str
) -> AnalyticsData:
    """
    Converts a ValidatorTask ORM object into an AnalyticsData schema for analytics upload.
    
    Serializes and filters nested task data, including completions, ground truths, and miner responses, to ensure JSON compatibility and exclude unnecessary fields. Computes lists of miner hotkeys that submitted scores and those that did not. Datetime fields are converted to ISO8601 strings, and metadata is parsed from JSON if present.
    
    Args:
        task: The ValidatorTask ORM object to convert.
        all_miner_hotkeys: List of all miner hotkeys registered at the time of task execution.
        validator_hotkey: The hotkey of the validator submitting the analytics.
    
    Returns:
        An AnalyticsData object containing the formatted and filtered task data.
    """

    # parse miner_responses first so we can calculate scored_hotkey
    _miner_responses = (
        [
            miner_response.model_dump(
                mode="json",
                exclude={
                    "task_result": True,
                    "created_at": True,
                    "updated_at": True,
                    "validator_task_relation": True,
                    "scores": {
                        "__all__": {
                            "created_at",
                            "updated_at",
                            "criterion_relation",
                            "miner_response_relation",
                        }
                    },
                },
            )
            for miner_response in task.miner_responses
        ]
        if task.miner_responses
        else []
    )

    # Get list of miner hotkeys that did not submit scores.
    scored_hotkeys = [
        miner_response["hotkey"]
        for miner_response in _miner_responses
        if miner_response["scores"] != []
    ]
    absent_hotkeys = list(set(all_miner_hotkeys) - set(scored_hotkeys))

    # payload must be convertible to JSON. Hence, serialize any nested objects to JSON and convert datetime to string.
    task_data = AnalyticsData(
        validator_task_id=task.id,
        task_type=task.task_type,
        previous_task_id=task.previous_task_id,
        next_task_id=task.next_task_id,
        validator_hotkey=validator_hotkey,
        prompt=task.prompt,
        completions=[
            completion.model_dump(
                mode="json",
                exclude={
                    "created_at": True,
                    "updated_at": True,
                    "validator_task_relation": True,
                    "validator_task_id": True,
                    "criterion": {
                        "__all__": {
                            "created_at",
                            "updated_at",
                            "scores",
                            "completion_relation",
                        }
                    },
                },
            )
            for completion in task.completions
        ]
        if task.completions
        else [],
        ground_truths=[
            ground_truth.model_dump(
                mode="json",
                exclude={"created_at", "updated_at", "validator_task_relation"},
            )
            for ground_truth in task.ground_truth
        ]
        if task.ground_truth
        else [],
        miner_responses=_miner_responses,
        scored_hotkeys=scored_hotkeys,
        absent_hotkeys=absent_hotkeys,
        created_at=datetime_to_iso8601_str(task.created_at),
        updated_at=datetime_to_iso8601_str(task.updated_at),
        metadata=json.loads(task.metadata) if task.metadata else None,
    )

    return task_data


# # # Main function for testing. Remove / Comment in prod.
# if __name__ == "__main__":
#     import asyncio

#     asyncio.run(main())


# async def main():
#     # for testing
#     from datetime import datetime, timedelta, timezone

#     from commons.utils import datetime_as_utc

#     from_14_days = datetime_as_utc(datetime.now(timezone.utc)) - timedelta(days=14)
#     # # from_24_hours = datetime_as_utc(datetime.now(timezone.utc)) - timedelta(
#     # #     hours=24
#     # # )
#     # # from_1_hours = datetime_as_utc(datetime.now(timezone.utc)) - timedelta(hours=1)
#     to_now = datetime_as_utc(datetime.now(timezone.utc))
#     # res = await run_analytics_upload(asyncio.Lock(), from_14_days, to_now)
#     # print(f"Response: {res}")

#     # payload = AnalyticsPayload(tasks=[])
#     # hotkey = "test_hk"
#     # signature = "0xtest"
#     # message = "test_msg"
#     # res = await _post_task_data(
#     #     payload=payload, hotkey=hotkey, signature=signature, message=message
#     # )
#     # print(f"Response: {res}")

#     # await run_analytics_upload()
#     res = await _get_task_data("test_hk", [], from_14_days, to_now)
#     # print(f"Response: {res}")

#     # with open("analytics_data.json", "w") as f:
#     #     # f.write(formatted, indent=2)
#     #     json.dump(res.model_dump(mode="json"), f, indent=2)

#     # 2. upload data to analytics API
#     message = "Uploading analytics data for validator hotkey: test_hk"
#     signature = "0x12345678"

#     res = await _post_task_data(
#         payload=res,
#         hotkey="test_hk",
#         signature=signature,
#         message=message,
#     )
#     print(f"Response: {res}")
