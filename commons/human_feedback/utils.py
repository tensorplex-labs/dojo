"""Utility functions for the Human Feedback Loop module."""

import json
import random
from datetime import datetime, timedelta, timezone
from typing import List

from bittensor.utils.btlogging import logging as logger

from commons.utils import datetime_as_utc
from database.prisma import Json
from dojo.protocol import TaskResult


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


def sample_miners(miners: List, subset_size: int, min_count: int = 3) -> List | None:
    """
    Safely sample a subset of miners.

    Args:
        miners: List of miners to sample from
        subset_size: Number of miners to return
        min_count: Minimum required miners

    Returns:
        List of sampled miners or None if not enough miners
    """
    if not miners or len(miners) < min_count:
        return None

    actual_size = min(subset_size, len(miners))
    return random.sample(miners, actual_size)
