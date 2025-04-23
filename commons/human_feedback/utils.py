"""Utility functions for the Human Feedback Loop module."""

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from bittensor.utils.btlogging import logging as logger

from commons.utils import datetime_as_utc, get_new_uuid, set_expire_time
from database.prisma import Json
from dojo import TASK_DEADLINE
from dojo.protocol import (
    CompletionResponse,
    ScoreCriteria,
    TaskResult,
    TaskSynapseObject,
    TaskTypeEnum,
)


def extract_text_feedback_from_results(task_results: list[TaskResult] | Json) -> str:
    """
    Extract text feedback from TaskResult objects or JSON data.

    Args:
        task_results: List of TaskResult objects from miner or JSON data from the database

    Returns:
        Extracted text feedback or empty string if not found
    """
    try:
        # Handle different input types
        if isinstance(task_results, str):
            # Parse JSON string
            parsed_results = json.loads(task_results)
        elif isinstance(task_results, list) and all(
            isinstance(item, TaskResult) for item in task_results if item
        ):
            # Original code path for TaskResult objects
            # Use generator expression to flatten the structure and find the first match
            criteria_generator = (
                criterion
                for task_result in task_results
                for result in task_result.result_data
                for criterion in result.criteria
            )

            # Find first matching criterion with text feedback
            text_criterion = next(
                (
                    criterion
                    for criterion in criteria_generator
                    if criterion.get("type") == "text" and "text_feedback" in criterion
                ),
                None,
            )

            return text_criterion["text_feedback"] if text_criterion else ""
        else:
            # Already parsed JSON data
            parsed_results = task_results

        # Process JSON data
        for result in parsed_results:
            if not isinstance(result, dict) or not result.get("result_data"):
                continue

            for result_data in result.get("result_data", []):
                if not isinstance(result_data, dict) or not result_data.get("criteria"):
                    continue

                for criterion in result_data.get("criteria", []):
                    if not isinstance(criterion, dict):
                        continue

                    if (
                        criterion.get("type") == "text"
                        and criterion.get("text_feedback")
                        and criterion["text_feedback"].strip()
                    ):
                        return criterion["text_feedback"]

    except Exception as e:
        logger.debug(f"Error extracting text feedback: {e}")

    return ""


def get_time_window_for_tasks(hours_ago_start: int = 48, hours_ago_end: int = 0):
    """
    Get a time window for selecting tasks.

    Args:
        hours_ago_start: Hours ago to start the window
        hours_ago_end: Hours ago to end the window

    Returns:
        Tuple of (start_time, end_time) as UTC datetimes
    """
    current_time = datetime_as_utc(datetime.now(timezone.utc))
    expire_from = current_time - timedelta(hours=hours_ago_start)
    expire_to = current_time - timedelta(hours=hours_ago_end)
    return expire_from, expire_to


def map_human_feedback_to_task_synapse(
    response_data: dict[str, Any],
) -> TaskSynapseObject | None:
    """
    Map the HumanFeedbackResponse from Redis to a TaskSynapseObject.

    This function handles the Redis response format which includes additional fields
    like success and hf_id that aren't part of our data model.

    Args:
        response_data: The response data from Redis

    Returns:
        A TaskSynapseObject ready to be sent to miners, or None if conversion fails
    """
    try:
        # First, check if the response was successful
        if isinstance(response_data, dict) and not response_data.get("success", True):
            error_message = response_data.get("message", "Unknown error")
            logger.error(f"Error in human feedback response: {error_message}")
            return None

        # Create a new synthetic task for scoring
        task_synapse = TaskSynapseObject(
            task_id=get_new_uuid(),
            prompt=response_data.get("base_prompt", ""),
            task_type=TaskTypeEnum.SCORE_FEEDBACK,
            expire_at=set_expire_time(TASK_DEADLINE),
        )

        # Map the completion responses - create proper CompletionResponse objects
        completion_responses: list[CompletionResponse] = []

        # First add the original (base) code as a completion for reference
        completion_responses.append(
            CompletionResponse(
                model="base_code",
                completion=response_data.get("base_code", ""),
                completion_id=get_new_uuid(),
                criteria_types=[
                    ScoreCriteria(
                        min=1.0,
                        max=100.0,
                    )
                ],
            )
        )

        # Add each generated version from feedback
        for feedback_task in response_data.get("human_feedback_tasks", []):
            if (
                "generated_code" in feedback_task
                and "code" in feedback_task["generated_code"]
            ):
                completion_responses.append(
                    CompletionResponse(
                        model=feedback_task.get("model", "unknown"),
                        completion=feedback_task["generated_code"]["code"],
                        completion_id=get_new_uuid(),
                        criteria_types=[
                            ScoreCriteria(
                                min=1.0,
                                max=100.0,
                            )
                        ],
                    )
                )

        # Set the completion responses on the task
        task_synapse.completion_responses = completion_responses

        return task_synapse

    except Exception as e:
        logger.error(f"Error mapping human feedback to task synapse: {e}")
        return None
