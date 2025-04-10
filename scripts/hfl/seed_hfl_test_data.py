#!/usr/bin/env python3
# seed_hfl_test_data.py - Script to seed test data for Human Feedback Loop testing

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
from database.prisma.enums import CriteriaTypeEnum, TaskTypeEnum
from database.prisma.models import MinerResponse
from database.prisma.types import (
    CompletionCreateInput,
    CriterionCreateInput,
    MinerScoreCreateInput,
)
from dojo.protocol import Result, TaskResult

# Default configuration
DEFAULT_NUM_TASKS = 5
DEFAULT_NUM_COMPLETIONS_PER_TASK = 4
DEFAULT_NUM_MINER_RESPONSES_PER_TASK = 10
DEFAULT_TARGET_HIGHEST_PERCENTAGE = 70  # 70% should be within the 50-90% range

# Path to the completion.json file
COMPLETION_JSON_PATH = os.path.join(os.path.dirname(__file__), "completion.json")


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
        await cleanup_test_data()

    # Create validator tasks with completions and miner responses
    created_tasks = await create_validator_tasks(
        num_tasks, num_completions, num_responses, target_percentage
    )

    logger.info(
        f"Test data seeding completed successfully with {len(created_tasks)} tasks created"
    )

    return created_tasks


async def cleanup_test_data():
    """Remove any existing test data created by this script."""
    try:
        # Find test validator tasks
        test_tasks = await prisma.validatortask.find_many()

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

        logger.info(f"Cleaned up {len(test_tasks)} test tasks and related data")

    except Exception as e:
        logger.error(f"Error cleaning up test data: {e}")
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
        dojo_task_id = f"test-dojo-task-{task_id}-{i}"
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
                "hotkey": Json(hotkey),
                "coldkey": Json(coldkey),
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

    args = parser.parse_args()

    try:
        # Connect to the database
        logger.info("Connecting to the database...")
        await prisma.connect()

        if args.cleanup_only:
            await cleanup_test_data()
        else:
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
