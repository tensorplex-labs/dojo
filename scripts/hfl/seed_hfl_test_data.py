#!/usr/bin/env python3
"""
Seed Test Data for Human Feedback Loop Testing

This script creates test data for testing the Human Feedback Loop (HFL) system.
It can create both regular CODE_GENERATION tasks with completions and scores,
as well as TEXT_FEEDBACK tasks for testing different feedback scenarios.

Usage Examples:
--------------

1. Regular HFL Testing:
   # Create 5 CODE_GENERATION tasks with completions and miner responses
   python scripts/hfl/seed_hfl_test_data.py

2. TEXT_FEEDBACK Testing (All Scenarios):
   # Create 1 task for each TEXT_FEEDBACK scenario (sufficient, insufficient, max_retry)
   python scripts/hfl/seed_hfl_test_data.py --text-feedback

3. Testing Specific TEXT_FEEDBACK Scenarios:
   # Create only tasks with sufficient feedback (≥3 valid responses)
   python scripts/hfl/seed_hfl_test_data.py --text-feedback --scenario sufficient

   # Create only tasks with insufficient feedback (<3 responses, retry needed)
   python scripts/hfl/seed_hfl_test_data.py --text-feedback --scenario insufficient

   # Create only tasks with max retry count reached
   python scripts/hfl/seed_hfl_test_data.py --text-feedback --scenario max_retry

4. Cleaning Up:
   # Clean up all test data
   python scripts/hfl/seed_hfl_test_data.py --cleanup-only

   # Clean up only TEXT_FEEDBACK test data
   python scripts/hfl/seed_hfl_test_data.py --cleanup-only --text-feedback

See --help for all available options.
"""

import argparse
import asyncio
import json
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from bittensor.utils.btlogging import logging as logger

from commons.utils import datetime_as_utc, get_new_uuid
from database.client import prisma
from database.prisma import Json
from database.prisma.enums import CriteriaTypeEnum, HFLStatusEnum, TaskTypeEnum
from database.prisma.models import MinerResponse
from database.prisma.types import (
    CompletionCreateInput,
    CriterionCreateInput,
    MinerScoreCreateInput,
    ValidatorTaskWhereInput,
)
from dojo.protocol import Result, TaskResult

# Default configuration
DEFAULT_NUM_TASKS = 5
DEFAULT_NUM_COMPLETIONS_PER_TASK = 4
DEFAULT_NUM_MINER_RESPONSES_PER_TASK = 10
DEFAULT_TARGET_HIGHEST_PERCENTAGE = 70  # 70% should be within the 50-90% range

# Path to the completion.json file
COMPLETION_JSON_PATH = os.path.join(os.path.dirname(__file__), "completion.json")

# TEXT_FEEDBACK configuration
DEFAULT_TF_SCENARIO_TASKS = 1
MAX_RETRY_ATTEMPTS = 5

# Real miner hotkeys from testnet
DEFAULT_MINER_HOTKEYS = [
    "5CBFxnF2MKYrS6LMr48wQTFhqmch2G9pS3AQkFm4RF8Jd1qe",  # miner_test
    "5CiZRMrKCxM7zW4uuq3be39T7KAjYXC2BjB5cBqRhEEnSUd6",  # miner_test1
    "5EbaEE3sCpNq5WezaiyKaA7jX3bvphYdwqD5b3bkzPELvxZY",  # miner_test2
]


async def seed_test_data(
    num_tasks: int = DEFAULT_NUM_TASKS,
    num_completions: int = DEFAULT_NUM_COMPLETIONS_PER_TASK,
    num_responses: int = DEFAULT_NUM_MINER_RESPONSES_PER_TASK,
    target_percentage: int = DEFAULT_TARGET_HIGHEST_PERCENTAGE,
    cleanup: bool = True,
):
    """Seed the database with test data for human feedback loop testing.

    Args:
        num_tasks: Number of validator tasks to create
        num_completions: Number of completions per task
        num_responses: Number of miner responses per task
        target_percentage: Percentage of miners that should score a specific completion highest
        cleanup: Whether to clean up existing test data before seeding
    """
    logger.info("Starting to seed test data for human feedback loop")

    # Clean up any existing test data if requested
    if cleanup:
        await cleanup_test_data()  # No task_type parameter cleans up all tasks

    # Create validator tasks with completions and miner responses
    created_tasks = await create_validator_tasks(
        num_tasks, num_completions, num_responses, target_percentage
    )

    logger.info(
        f"Test data seeding completed successfully with {len(created_tasks)} tasks created"
    )

    return created_tasks


async def cleanup_test_data(task_type: TaskTypeEnum | None = None):
    """Remove any existing test data created by this script.

    Args:
        task_type: Optional TaskTypeEnum to filter tasks to be cleaned up.
                  If None, cleans up all tasks.
    """
    try:
        # Find test validator tasks, optionally filtered by task_type
        where_input = None
        if task_type:
            where_input = ValidatorTaskWhereInput({"task_type": task_type})
            logger.info(f"Finding {task_type} tasks to clean up")
        else:
            logger.info("Finding all test tasks to clean up")

        test_tasks = await prisma.validatortask.find_many(where=where_input)

        if not test_tasks:
            logger.info("No existing test data found to clean up")
            return

        # Use a transaction to ensure atomicity
        async with prisma.tx() as tx:
            for task in test_tasks:
                task_id = task.id

                # Delete ground_truth records related to this task
                await tx.groundtruth.delete_many(where={"validator_task_id": task_id})

                # Delete miner scores related to this task
                await tx.minerscore.delete_many(
                    where={
                        "miner_response_relation": {
                            "is": {"validator_task_id": task_id}
                        }
                    }
                )

                # Delete criteria related to this task's completions
                await tx.criterion.delete_many(
                    where={
                        "completion_relation": {"is": {"validator_task_id": task_id}}
                    }
                )

                # Delete completions for this task
                await tx.completion.delete_many(where={"validator_task_id": task_id})

                # Delete miner responses for this task
                await tx.minerresponse.delete_many(where={"validator_task_id": task_id})

                # Delete any HFL states that reference this task
                await tx.hflstate.delete_many(where={"original_task_id": task_id})
                await tx.hflstate.delete_many(where={"current_task_id": task_id})

                # Finally delete the validator task
                await tx.validatortask.delete(where={"id": task_id})

        task_type_msg = f"{task_type} " if task_type else ""
        logger.info(
            f"Cleaned up {len(test_tasks)} {task_type_msg}test tasks and related data"
        )

    except Exception as e:
        task_type_msg = f"{task_type} " if task_type else ""
        logger.error(f"Error cleaning up {task_type_msg}test data: {e}")
        raise


async def create_validator_tasks(
    num_tasks: int, num_completions: int, num_responses: int, target_percentage: int
) -> List[Any]:
    """Create test validator tasks with completions, miner responses, and scores.

    Args:
        num_tasks: Number of validator tasks to create
        num_completions: Number of completions per task
        num_responses: Number of miner responses per task
        target_percentage: Percentage of miners that should score a specific completion highest

    Returns:
        List of created validator tasks
    """
    created_tasks = []

    for i in range(num_tasks):
        # Create a task that expired recently
        hours_ago = random.randint(3, 24)  # Random time within last 24 hours
        expire_at = datetime_as_utc(datetime.now(timezone.utc)) - timedelta(
            hours=hours_ago
        )

        # Create the validator task with metadata as JSON
        task = await prisma.validatortask.create(
            data={
                "prompt": Json("This is a test prompt for testing the HFL"),
                "task_type": TaskTypeEnum.CODE_GENERATION,
                "is_processed": True,
                "expire_at": expire_at,
                # "metadata": Json(
                #     {
                #         "is_test": True,
                #         "created_by_seeder": True,
                #         "seed_timestamp": datetime.now().isoformat(),
                #     }
                # ),
            }
        )
        created_tasks.append(task)

        # Create completions for this task
        completions = await create_completions(task.id, num_completions)

        # Create miner responses for this task with scores embedded in task_result
        miner_responses = await create_miner_responses(
            task.id, num_responses, completions, target_percentage
        )

        # Create scores in the database from the miner response task_results
        await create_scores(task.id, completions, miner_responses)

        logger.info(f"Created test task {i+1}/{num_tasks} with ID: {task.id}")

    return created_tasks


async def create_completions(
    task_id: str, num_completions: int
) -> List[Dict[str, Any]]:
    """Create test completions for a validator task using data from completion.json.

    Args:
        task_id: ID of the validator task
        num_completions: Number of completions to create

    Returns:
        List of dictionaries containing completion and criterion objects
    """
    completions = []

    # Load the completion data from JSON file
    try:
        with open(COMPLETION_JSON_PATH) as f:
            completion_data = json.load(f)

        available_completions = completion_data.get("completions", [])

        if not available_completions:
            logger.error("No completions found in the JSON file")
            raise ValueError("The completion.json file must contain completions")

        # Use the completions from the JSON file (cycle through if we need more)
        for i in range(num_completions):
            # Generate a unique completion ID
            completion_id = get_new_uuid()

            # Use the completion data from JSON, cycling through the available completions
            completion_content = available_completions[i % len(available_completions)][
                "completion"
            ]
            model = available_completions[i % len(available_completions)]["model"]

            # Create the completion with properly serialized JSON
            completion = await prisma.completion.create(
                data=CompletionCreateInput(
                    completion_id=completion_id,
                    validator_task_id=task_id,
                    model=model,
                    completion=Json(completion_content),
                )
            )

            # Create a criterion for this completion
            criterion = await prisma.criterion.create(
                data=CriterionCreateInput(
                    criteria_type=CriteriaTypeEnum.SCORE,
                    config=Json(json.dumps({"min": 1.0, "max": 100.0})),
                    completion_id=completion.id,
                )
            )

            completions.append(
                {
                    "completion": completion,
                    "criterion": criterion,
                    "completion_id": completion_id,
                }
            )

    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        logger.error(f"Error loading completion data from JSON: {str(e)}")
        raise ValueError(f"Failed to load completion data: {str(e)}")

    return completions


async def create_miner_responses(
    task_id: str,
    num_responses: int,
    completions: List[Dict[str, Any]],
    target_percentage: int,
) -> List[MinerResponse]:
    """Create test miner responses for a validator task with scores for completions.

    Args:
        task_id: ID of the validator task
        num_responses: Number of miner responses to create
        completions: List of completions to score
        target_percentage: Percentage of miners that should score a specific completion highest

    Returns:
        List of created MinerResponse objects
    """
    miner_responses: List[MinerResponse] = []

    # Choose which completion should be selected as "best"
    target_completion_index = random.randint(0, len(completions) - 1)
    target_completion = completions[target_completion_index]

    # Calculate how many miners should score the target completion highest
    target_miners_count = int(num_responses * (target_percentage / 100))

    # Randomly select miners to score the target completion highest
    selected_miners = set(random.sample(range(num_responses), target_miners_count))

    for i in range(num_responses):
        # Create unique identifiers
        dojo_task_id = f"test-dojo-task-{i}-{task_id}"
        hotkey = f"test-miner-hotkey-{i}"
        coldkey = f"test-miner-coldkey-{i}"
        miner_result_id = get_new_uuid()
        worker_id = get_new_uuid()
        current_time = datetime.now(timezone.utc)

        # Determine which completion gets the highest score for this miner
        highest_score_goes_to = (
            target_completion_index
            if i in selected_miners
            else random.choice(
                [j for j in range(len(completions)) if j != target_completion_index]
            )
        )

        # Create result_data with criteria for each completion
        result_data = []
        for j, completion_data in enumerate(completions):
            # Assign score - higher for the chosen "best" completion
            raw_score = (
                random.uniform(80, 100)
                if j == highest_score_goes_to
                else random.uniform(1, 70)
            )

            # Create a Result object for each completion
            result = Result(
                model=completion_data["completion_id"],
                criteria=[{"type": "score", "value": round(raw_score, 2)}],
            )
            result_data.append(result)

        # Create a TaskResult object
        task_result = TaskResult(
            id=miner_result_id,
            status="COMPLETED",
            worker_id=worker_id,
            created_at=current_time,
            updated_at=current_time,
            result_data=result_data,
            dojo_task_id=dojo_task_id,
            stake_amount=None,
            finalised_loss=None,
            potential_loss=None,
            finalised_reward=None,
            potential_reward=None,
        )

        # Convert the TaskResult to a JSON string
        task_result_json = Json([task_result.model_dump()])

        # Create the miner response with properly serialized JSON including scores
        miner_response: MinerResponse = await prisma.minerresponse.create(
            data={
                "id": get_new_uuid(),
                "validator_task_id": task_id,
                "dojo_task_id": dojo_task_id,
                "hotkey": hotkey,
                "coldkey": coldkey,
                "task_result": task_result_json,
            }
        )
        miner_responses.append(miner_response)

    # Log stats about the score distribution
    logger.info(f"Created {len(miner_responses)} miner responses for task {task_id}")
    logger.info(
        f"Target completion (ID: {target_completion['completion_id']}, index {target_completion_index}) "
    )
    logger.info(
        f"should be scored highest by {target_miners_count}/{num_responses} miners ({target_percentage}%)"
    )

    return miner_responses


async def create_scores(
    task_id: str,
    completions: List[Dict[str, Any]],
    miner_responses: List[MinerResponse],
):
    """
    Create scores in the database based on the miner response task_results.

    Args:
        task_id: ID of the validator task
        completions: List of completions (with criteria)
        miner_responses: List of miner responses with scores
    """
    scores_created = 0

    for miner_response in miner_responses:
        try:
            # Get the first task result (there should only be one)
            task_result = TaskResult.model_validate(miner_response.task_result[0])
            logger.info(f"Task result: {task_result}")

            if task_result is None or not hasattr(task_result, "result_data"):
                logger.warning(
                    f"No task_result found in miner_response {miner_response.id}"
                )
                continue

            result_data = (
                task_result.result_data if hasattr(task_result, "result_data") else []
            )

            if not result_data:
                logger.warning(
                    f"No result_data found in task_result for miner_response {miner_response.id}"
                )
                continue

            # Create a dictionary mapping completion_id to score
            completion_scores = {}
            for result in result_data:
                model_id = result.model  # This is the completion_id
                criteria = result.criteria

                if not model_id or not criteria:
                    continue

                # Get the score from the first criterion with type "score"
                for criterion in criteria:
                    if criterion.get("type") == "score":
                        score_value = criterion.get("value")
                        if score_value is not None:
                            completion_scores[model_id] = float(score_value)
                            break

            if not completion_scores:
                logger.warning(
                    f"No valid scores found in task_result for miner_response {miner_response.id}"
                )
                continue

            # Find the highest score
            max_score = max(completion_scores.values())

            # Create score records for each completion
            for completion_data in completions:
                completion_id = completion_data["completion_id"]

                # Get score for this completion (default to 0 if not found)
                raw_score = completion_scores.get(completion_id, 0)

                # Prepare scores data
                scores_data = {
                    "raw_score": raw_score,
                    "rank_id": 1 if raw_score == max_score else 2,
                    "normalised_score": raw_score / 100,
                    "ground_truth_score": None,
                }

                # Create the miner score with properly serialized JSON
                await prisma.minerscore.create(
                    data=MinerScoreCreateInput(
                        criterion_id=completion_data["criterion"].id,
                        miner_response_id=miner_response.id,
                        scores=Json(json.dumps(scores_data)),
                    )
                )
                scores_created += 1

        except Exception as e:
            logger.error(
                f"Error processing miner response {miner_response.id}: {str(e)}"
            )
            continue

    logger.info(f"Created {scores_created} scores for task {task_id}")
    return


async def seed_tf_test_data(
    num_tasks: int = DEFAULT_TF_SCENARIO_TASKS,
    cleanup: bool = True,
    scenario: str = "all",
    miner_hotkeys: List[str] = DEFAULT_MINER_HOTKEYS,
):
    """Seed test data specifically for TEXT_FEEDBACK tasks with three scenarios:
    1. Tasks with sufficient feedback responses (>=3)
    2. Tasks with insufficient feedback (<3)
    3. Tasks with insufficient feedback but max retry count reached

    Args:
        num_tasks: Number of tasks to create for each scenario
        cleanup: Whether to clean up existing TEXT_FEEDBACK test data before seeding
        scenario: Which scenario(s) to create - 'all', 'sufficient', 'insufficient', or 'max_retry'
        miner_hotkeys: List of real miner hotkeys to use for responses
    """
    logger.info(f"Starting to seed TEXT_FEEDBACK test data for scenario: {scenario}")
    logger.info(f"Using miner hotkeys: {miner_hotkeys}")

    # Clean up existing TF test data if requested
    if cleanup:
        await cleanup_test_data(TaskTypeEnum.TEXT_FEEDBACK)

    created_tasks = {}

    # Create tasks for each selected scenario
    if scenario in ["all", "sufficient"]:
        sufficient_tasks = await create_tf_tasks(
            num_tasks=num_tasks,
            num_responses=min(
                5, len(miner_hotkeys)
            ),  # Ensure we don't exceed available hotkeys
            scenario="sufficient",
            valid_feedback_count=min(
                3, len(miner_hotkeys)
            ),  # Ensure valid count <= available hotkeys
            retry_count=0,
            miner_hotkeys=miner_hotkeys,
        )
        created_tasks["sufficient"] = sufficient_tasks
        logger.info(f"Created {len(sufficient_tasks)} tasks with sufficient feedback")

    if scenario in ["all", "insufficient"]:
        insufficient_tasks = await create_tf_tasks(
            num_tasks=num_tasks,
            num_responses=min(5, len(miner_hotkeys)),
            scenario="insufficient",
            valid_feedback_count=min(
                2, len(miner_hotkeys) - 1
            ),  # Ensure at least one invalid response
            retry_count=2,
            miner_hotkeys=miner_hotkeys,
        )
        created_tasks["insufficient"] = insufficient_tasks
        logger.info(
            f"Created {len(insufficient_tasks)} tasks with insufficient feedback"
        )

    if scenario in ["all", "max_retry"]:
        max_retry_tasks = await create_tf_tasks(
            num_tasks=num_tasks,
            num_responses=min(5, len(miner_hotkeys)),
            scenario="max_retry",
            valid_feedback_count=min(2, len(miner_hotkeys) - 1),
            retry_count=MAX_RETRY_ATTEMPTS,
            miner_hotkeys=miner_hotkeys,
        )
        created_tasks["max_retry"] = max_retry_tasks
        logger.info(
            f"Created {len(max_retry_tasks)} tasks with max retry count reached"
        )

    return created_tasks


async def create_tf_tasks(
    num_tasks: int,
    num_responses: int,
    scenario: str,
    valid_feedback_count: int,
    retry_count: int = 0,
    miner_hotkeys: List[str] = DEFAULT_MINER_HOTKEYS,
) -> List[Any]:
    """
    Create TEXT_FEEDBACK tasks with varying levels of valid text feedback.

    Args:
        num_tasks: Number of tasks to create
        num_responses: Total number of miner responses to create per task
        scenario: Scenario identifier ("sufficient", "insufficient", or "max_retry")
        valid_feedback_count: Number of responses that should have valid text feedback
        retry_count: Number of retries to simulate (for max_retry scenario)
        miner_hotkeys: List of real miner hotkeys to use (will cycle through if needed)

    Returns:
        List of created validator tasks
    """
    created_tasks = []

    # Find or create a previous task to refer to (original task)
    previous_task = await prisma.validatortask.find_first(
        where={"task_type": TaskTypeEnum.CODE_GENERATION}
    )

    if not previous_task:
        # Create a previous task if none exists
        previous_task = await prisma.validatortask.create(
            data={
                "prompt": Json("This is a previous task for TEXT_FEEDBACK testing"),
                "task_type": TaskTypeEnum.CODE_GENERATION,
                "is_processed": True,
                "expire_at": datetime_as_utc(
                    datetime.now(timezone.utc) - timedelta(hours=2)
                ),
            }
        )

    for i in range(num_tasks):
        # Create a task that expired recently (1 hour ago)
        expire_at = datetime_as_utc(datetime.now(timezone.utc) - timedelta(hours=1))

        # Create the TF task with reference to previous task
        task = await prisma.validatortask.create(
            data={
                "prompt": Json(
                    f"This is a TEXT_FEEDBACK test prompt for scenario: {scenario}"
                ),
                "task_type": TaskTypeEnum.TEXT_FEEDBACK,
                "is_processed": False,
                "expire_at": expire_at,
                "previous_task_id": previous_task.id,
            }
        )

        # Load a completion from completion.json to use
        completion_data = await load_completion_data()
        if not completion_data:
            logger.error("No completion data found in completion.json")
            continue

        completion_content = completion_data[0]["completion"]
        model = completion_data[0]["model"]
        completion_id = get_new_uuid()

        # Create a completion for this task
        completion = await prisma.completion.create(
            data=CompletionCreateInput(
                completion_id=completion_id,
                validator_task_id=task.id,
                model=model,
                completion=Json(completion_content),
            )
        )

        # Create a text criterion for this completion
        criterion = await prisma.criterion.create(
            data=CriterionCreateInput(
                criteria_type=CriteriaTypeEnum.TEXT,
                config=Json(
                    json.dumps(
                        {
                            "query": "What specific improvements could make this output more accurate, complete, or relevant to the prompt?"
                        }
                    )
                ),
                completion_id=completion.id,
            )
        )

        # Create HFL state with events in the correct format
        hfl_state = await prisma.hflstate.create(
            data={
                "original_task_id": previous_task.id,
                "current_task_id": task.id,
                "status": HFLStatusEnum.TF_PENDING,
                "current_iteration": 1,
                "tf_retry_count": retry_count,
                "selected_completion_id": completion_id,
                "events": [
                    Json(
                        {
                            "type": HFLStatusEnum.TF_PENDING.value,
                            "task_id": task.id,
                            "timestamp": datetime_as_utc(
                                datetime.now(timezone.utc)
                            ).isoformat(),
                        }
                    )
                ],
            }
        )

        # Link HFL state to task - using the correct field name
        await prisma.validatortask.update(
            where={"id": task.id}, data={"HFLState": {"connect": {"id": hfl_state.id}}}
        )

        created_tasks.append(task)

        # Create miner responses with varying levels of text feedback
        await create_tf_miner_responses(
            task_id=task.id,
            num_responses=num_responses,
            completion_id=completion_id,
            criterion_id=criterion.id,
            valid_feedback_count=valid_feedback_count,
            miner_hotkeys=miner_hotkeys,
        )

        logger.info(
            f"Created {scenario} TEXT_FEEDBACK task {i+1}/{num_tasks} with ID: {task.id}"
        )

    return created_tasks


async def load_completion_data():
    """Load completion data from the completion.json file."""
    try:
        with open(COMPLETION_JSON_PATH) as f:
            completion_data = json.load(f)

        return completion_data.get("completions", [])
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Error loading completion data: {e}")
        return []


async def create_tf_miner_responses(
    task_id: str,
    num_responses: int,
    completion_id: str,
    criterion_id: str,
    valid_feedback_count: int,
    miner_hotkeys: List[str] = DEFAULT_MINER_HOTKEYS,
):
    """
    Create test miner responses for a TEXT_FEEDBACK task.

    Args:
        task_id: ID of the validator task
        num_responses: Total number of miner responses to create
        completion_id: ID of the completion being evaluated
        criterion_id: ID of the text criterion
        valid_feedback_count: Number of responses that should have valid text feedback
        miner_hotkeys: List of real miner hotkeys to use (will cycle through if needed)
    """
    miner_responses = []

    # Make sure we don't exceed the number of available hotkeys
    num_responses = min(num_responses, len(miner_hotkeys))

    # Shuffle the hotkeys to randomize which ones get valid feedback
    shuffled_hotkeys = random.sample(miner_hotkeys, len(miner_hotkeys))

    for i in range(num_responses):
        # Create unique identifiers
        dojo_task_id = f"real-tf-task-{i}-{task_id}"

        # Use a real hotkey (cycle through the shuffled list)
        hotkey = shuffled_hotkeys[i % len(shuffled_hotkeys)]
        coldkey = (
            f"coldkey-for-{hotkey[:8]}"  # Just use a prefix of the hotkey for coldkey
        )

        # Determine if this response should have valid text feedback
        has_feedback = i < valid_feedback_count

        # Create result_data with text feedback for the completion
        feedback_text = (
            f"This is test feedback from {hotkey[:8]} for improving the completion. Consider changing the background color to purple."
            if has_feedback
            else ""
        )

        result = Result(
            model=completion_id,
            criteria=[
                {
                    "type": "text",
                    "query": "What specific improvements could make this output more accurate, complete, or relevant to the prompt?",
                    "text_feedback": feedback_text,
                }
            ],
        )

        # Create a TaskResult object
        task_result = TaskResult(
            id=get_new_uuid(),
            status="COMPLETED",
            worker_id=get_new_uuid(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            result_data=[result],
            dojo_task_id=dojo_task_id,
            stake_amount=None,
            finalised_loss=None,
            potential_loss=None,
            finalised_reward=None,
            potential_reward=None,
        )

        # Create the miner response with properly serialized JSON
        miner_response = await prisma.minerresponse.create(
            data={
                "id": get_new_uuid(),
                "validator_task_id": task_id,
                "dojo_task_id": dojo_task_id,
                "hotkey": hotkey,
                "coldkey": coldkey,
                "task_result": Json([task_result.model_dump()]),
            }
        )
        miner_responses.append(miner_response)

    logger.info(
        f"Created {num_responses} miner responses for task {task_id} with {valid_feedback_count} valid feedback using real hotkeys"
    )
    return miner_responses


async def main():
    """Parse command line arguments and run the seeding script."""
    parser = argparse.ArgumentParser(
        description="Seed test data for Human Feedback Loop testing"
    )

    parser.add_argument(
        "--tasks",
        type=int,
        default=DEFAULT_NUM_TASKS,
        help=f"Number of validator tasks to create (default: {DEFAULT_NUM_TASKS})",
    )

    parser.add_argument(
        "--completions",
        type=int,
        default=DEFAULT_NUM_COMPLETIONS_PER_TASK,
        help=f"Number of completions per task (default: {DEFAULT_NUM_COMPLETIONS_PER_TASK})",
    )

    parser.add_argument(
        "--responses",
        type=int,
        default=DEFAULT_NUM_MINER_RESPONSES_PER_TASK,
        help=f"Number of miner responses per task (default: {DEFAULT_NUM_MINER_RESPONSES_PER_TASK})",
    )

    parser.add_argument(
        "--percentage",
        type=int,
        default=DEFAULT_TARGET_HIGHEST_PERCENTAGE,
        help=f"Percentage of miners that should score a specific completion highest (default: {DEFAULT_TARGET_HIGHEST_PERCENTAGE})",
    )

    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Skip cleaning up existing test data before seeding",
    )

    parser.add_argument(
        "--cleanup-only",
        action="store_true",
        help="Only clean up existing test data without seeding new data",
    )

    # TEXT_FEEDBACK testing arguments
    parser.add_argument(
        "--text-feedback",
        action="store_true",
        help="Seed data for TEXT_FEEDBACK task testing scenarios",
    )

    parser.add_argument(
        "--tf-tasks",
        type=int,
        default=DEFAULT_TF_SCENARIO_TASKS,
        help=f"Number of tasks to create for each TEXT_FEEDBACK scenario (default: {DEFAULT_TF_SCENARIO_TASKS})",
    )

    # New argument for specifying TEXT_FEEDBACK scenario
    parser.add_argument(
        "--scenario",
        type=str,
        choices=["all", "sufficient", "insufficient", "max_retry"],
        default="all",
        help="Which TEXT_FEEDBACK scenario to seed (default: all)",
    )

    # Add new argument for miner hotkeys
    parser.add_argument(
        "--hotkeys",
        type=str,
        default=",".join(DEFAULT_MINER_HOTKEYS),
        help="Comma-separated list of real miner hotkeys to use for responses",
    )

    args = parser.parse_args()

    try:
        # Connect to the database
        logger.info("Connecting to the database...")
        await prisma.connect()

        # Parse miner hotkeys from command line
        miner_hotkeys = (
            args.hotkeys.split(",") if args.hotkeys else DEFAULT_MINER_HOTKEYS
        )

        if args.cleanup_only:
            # Clean up only the specified task type or all tasks
            if args.text_feedback:
                await cleanup_test_data(TaskTypeEnum.TEXT_FEEDBACK)
            else:
                await cleanup_test_data()  # Clean up all task types
        elif args.text_feedback:
            # Run TEXT_FEEDBACK seeding with specified scenario
            await seed_tf_test_data(
                num_tasks=args.tf_tasks,
                cleanup=not args.no_cleanup,
                scenario=args.scenario,
                miner_hotkeys=miner_hotkeys,
            )
        else:
            # Run regular HFL seeding
            await seed_test_data(
                num_tasks=args.tasks,
                num_completions=args.completions,
                num_responses=args.responses,
                target_percentage=args.percentage,
                cleanup=not args.no_cleanup,
            )
    except Exception as e:
        logger.error(f"Error in main execution: {str(e)}")
        raise
    finally:
        # Always disconnect from the database when done
        logger.info("Disconnecting from the database...")
        await prisma.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
