"""Utility functions for the Human Feedback Loop module."""

import json
from datetime import datetime, timedelta, timezone

from bittensor.utils.btlogging import logging as logger

from commons.dataset.types import HumanFeedbackResponse
from commons.utils import datetime_as_utc, get_new_uuid, set_expire_time
from database.client import prisma
from database.prisma import Json
from database.prisma.models import Criterion, HFLState, MinerScore, ValidatorTask
from database.prisma.types import (
    MinerScoreCreateInput,
    MinerScoreUpdateInput,
    MinerScoreWhereInput,
    ValidatorTaskInclude,
)
from dojo import HFL_TASK_DEADLINE
from dojo.protocol import (
    CodeAnswer,
    CompletionResponse,
    ScoreCriteria,
    TaskResult,
    TaskSynapseObject,
    TaskTypeEnum,
    TextFeedbackScore,
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
    response_data: HumanFeedbackResponse,
) -> TaskSynapseObject | None:
    """
    Map the HumanFeedbackResponse to a TaskSynapseObject.

    Args:
        response_data: HumanFeedbackResponse object from Synthetic API

    Returns:
        A TaskSynapseObject ready to be sent to miners, or None if conversion fails
    """
    try:
        # Create a new synthetic task for scoring
        task_synapse = TaskSynapseObject(
            task_id=get_new_uuid(),
            prompt=response_data.base_prompt,
            task_type=TaskTypeEnum.SCORE_FEEDBACK,
            expire_at=set_expire_time(HFL_TASK_DEADLINE),
        )

        # Map the completion responses - create proper CompletionResponse objects
        completion_responses: list[CompletionResponse] = []

        # First add the original (base) code as a completion for reference
        original_completion = CodeAnswer.model_validate(response_data.base_code)
        # create original completion
        completion_responses.append(
            CompletionResponse(
                model="original",  # Use a default model name for base code
                completion=original_completion,
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
        for feedback_task in response_data.human_feedback_tasks:
            if (
                hasattr(feedback_task, "generated_code")
                and feedback_task.generated_code
            ):
                completion_responses.append(
                    CompletionResponse(
                        model=feedback_task.model
                        if hasattr(feedback_task, "model")
                        else "unknown",
                        completion=feedback_task.generated_code,
                        completion_id=feedback_task.completion_id,
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


async def evaluate_miner_consensus(
    task_id: str,
    min_threshold: float | None = None,
    max_threshold: float | None = None,
) -> tuple[dict[str, float], str | None, str | None]:
    """
    Evaluate miner consensus on a task by analyzing which completions miners scored highest.

    Args:
        task_id: The validator task ID to evaluate
        min_threshold: Minimum percentage threshold for consensus (e.g., 50%)
        max_threshold: Maximum percentage threshold for consensus (e.g., 90%)

    Returns:
        Tuple containing:
        - Dictionary of completion_id -> percentage of miners who scored it highest
        - Completion ID that meets the min/max threshold criteria, or None if none meet criteria
        - Completion ID that has high consensus (above max_threshold), or None if none exists
    """
    try:
        # Get all miner scores for this validator task
        miner_scores = await MinerScore.prisma().find_many(
            where=MinerScoreWhereInput(
                {"miner_response_relation": {"is": {"validator_task_id": task_id}}}
            ),
            include={
                "criterion_relation": {"include": {"completion_relation": True}},
                "miner_response_relation": True,
            },
        )

        if not miner_scores:
            logger.debug(f"No miner scores found for task {task_id}")
            return {}, None, None

        # Group scores by miner response ID and completion ID
        # map of miner_response_id -> completion_id
        miner_best_completions = {}
        # map of completion_id -> list of miners and their raw scores
        completion_scores = {}

        for score in miner_scores:
            if (
                not score.scores
                or not score.criterion_relation
                or not score.criterion_relation.completion_relation
            ):
                continue

            # Parse the scores JSON
            scores_dict = json.loads(score.scores)
            miner_raw_score = scores_dict.get("raw_score")
            if miner_raw_score is None:
                continue

            completion_id = score.criterion_relation.completion_relation.completion_id
            miner_response_id = score.miner_response_id

            # Store score for this completion
            if completion_id not in completion_scores:
                completion_scores[completion_id] = []
            completion_scores[completion_id].append(
                (miner_response_id, miner_raw_score)
            )

        # Find highest scored completion for each miner
        for completion_id, scores in completion_scores.items():
            for miner_response_id, score in scores:
                current_best = miner_best_completions.get(miner_response_id)
                if current_best is None:
                    miner_best_completions[miner_response_id] = completion_id
                    continue

                # Find the current best score
                current_best_score = None
                for c_scores in completion_scores.get(current_best, []):
                    if c_scores[0] == miner_response_id:
                        current_best_score = c_scores[1]
                        break

                if current_best_score is None or score > current_best_score:
                    miner_best_completions[miner_response_id] = completion_id

        total_miners = len(set(miner_best_completions.keys()))
        if total_miners == 0:
            return {}, None, None

        # Count how many miners scored each completion as best
        completion_counts = {}
        for best_completion in miner_best_completions.values():
            completion_counts[best_completion] = (
                completion_counts.get(best_completion, 0) + 1
            )

        # Calculate percentages for each completion
        completion_percentages = {}
        high_consensus_completion = None
        threshold_met_completion = None

        for completion_id, count in completion_counts.items():
            percentage = (count / total_miners) * 100
            completion_percentages[completion_id] = percentage

            # Check for high consensus (above max_threshold)
            if max_threshold is not None and percentage >= max_threshold:
                high_consensus_completion = completion_id

            # Check for threshold criteria
            if min_threshold is not None and max_threshold is not None:
                if min_threshold <= percentage < max_threshold:
                    threshold_met_completion = completion_id
                    logger.info(
                        f"Found eligible completion {completion_id} with {percentage:.1f}% "
                        f"of miners ({count}/{total_miners}) scoring it highest"
                    )
            elif min_threshold is not None and percentage >= min_threshold:
                threshold_met_completion = completion_id
            elif max_threshold is not None and percentage < max_threshold:
                threshold_met_completion = completion_id

        # Return the results
        return (
            completion_percentages,
            threshold_met_completion,
            high_consensus_completion,
        )

    except Exception as e:
        logger.error(f"Error evaluating miner consensus for task {task_id}: {e}")
        return {}, None, None


async def check_improvement_threshold(
    current_sf_task_id: str,
    previous_task_id: str,  # Could be a previous SF task or the original task
    min_improvement_percentage: float = 10.0,
) -> tuple[bool, float]:
    """
    Check if the improvement meets the minimum threshold.

    Args:
        current_sf_task_id: Current score feedback task ID
        previous_task_id: Previous task ID (SF task or original task for first iteration)
        is_first_iteration: Whether this is the first iteration (comparing to original task)
        min_improvement_percentage: Minimum percentage improvement required

    Returns:
        Tuple containing:
        - Boolean indicating if the threshold is met
        - Actual improvement percentage
    """
    try:
        # Get percentages from current iteration
        current_percentages, _, _ = await evaluate_miner_consensus(
            task_id=current_sf_task_id,
        )

        # Get percentages from previous task
        previous_percentages, _, _ = await evaluate_miner_consensus(
            task_id=previous_task_id,
        )

        # Compare percentages for the best completion in each iteration
        current_best = (
            max(current_percentages.items(), key=lambda x: x[1])
            if current_percentages
            else (None, 0)
        )

        previous_best = (
            max(previous_percentages.items(), key=lambda x: x[1])
            if previous_percentages
            else (None, 0)
        )

        if current_best[0] and previous_best[0]:
            current_percentage = current_best[1]
            previous_percentage = previous_best[1]

            # Calculate improvement percentage
            improvement = (
                (current_percentage - previous_percentage) / previous_percentage * 100
            )

            logger.info(
                f"Improvement from {previous_task_id}: {improvement:.1f}% "
                f"(from {previous_percentage:.1f}% to {current_percentage:.1f}%)"
            )

            # Return if improvement is sufficient
            return improvement >= min_improvement_percentage, improvement

        return False, 0.0

    except Exception as e:
        logger.error(f"Error checking improvement threshold: {e}")
        return False, 0.0


async def should_continue_hfl(
    hfl_state: HFLState,
    latest_sf_task_id: str,
    max_iterations: int = 3,
    consensus_threshold: float = 90.0,
    min_improvement_percentage: float = 10.0,
) -> tuple[bool, str | None]:
    """
    Determine if the HFL workflow should continue or stop.
    """
    try:
        # Condition 1: Maximum iterations reached
        if hfl_state.current_iteration >= max_iterations:
            logger.info(
                f"Maximum iterations reached: {hfl_state.current_iteration}/{max_iterations}"
            )
            return False, "max_iterations_reached"

        # Condition 2: Consensus threshold reached; for example, 90% of miners scored the same completion highest
        (
            completion_percentages,
            _,
            high_consensus_completion,
        ) = await evaluate_miner_consensus(
            task_id=latest_sf_task_id,
            max_threshold=consensus_threshold,
        )

        if high_consensus_completion:
            logger.info(
                f"Consensus threshold of {consensus_threshold}% reached for completion {high_consensus_completion}, with {completion_percentages[high_consensus_completion]:.1f}% of miners scoring it highest"
            )
            return False, "consensus_reached"

        # TODO: KIV
        # Condition 3: Improvement threshold reached; for example, 10% improvement over the previous task
        # try:
        #     # Get the previous task (original or parent SF) using existing ORM function
        #     previous_task = await ORM.get_original_or_parent_sf_task(latest_sf_task_id)

        #     if previous_task and previous_task.id:
        #         # Use the specialized function to check improvement
        #         meets_threshold, improvement = await check_improvement_threshold(
        #             current_sf_task_id=latest_sf_task_id,
        #             previous_task_id=previous_task.id,
        #             min_improvement_percentage=min_improvement_percentage,
        #         )

        #         if not meets_threshold:
        #             return (
        #                 False,
        #                 f"insufficient_improvement_{improvement:.1f}_percent",
        #             )
        #     else:
        #         logger.warning(
        #             f"Could not find previous task for SF task {latest_sf_task_id}"
        #         )
        # except Exception as e:
        #     logger.error(f"Error checking improvement threshold: {e}")
        #     # Continue with other checks if improvement calculation fails

        # If no stopping conditions met, continue
        return True, None

    except Exception as e:
        logger.error(f"Error in should_continue_hfl: {e}")
        return False, f"error: {str(e)}"


def extract_criteria_values_by_model_and_type(task_results: list[TaskResult]) -> dict:
    """
    Extract and group criterion values by model ID and criterion type from task results.

    Example input:
    task_results = [
        {
            "result_data": [
                {
                    "model": "model_123",
                    "criteria": [
                        {"type": "score", "value": 80},
                        {"type": "text", "value": "Good code"}
                    ]
                },
                {
                    "model": "model_456",
                    "criteria": [
                        {"type": "score", "value": 90}
                    ]
                }
            ]
        },
        {
            "result_data": [
                {
                    "model": "model_123",
                    "criteria": [
                        {"type": "score", "value": 70},
                        {"type": "text", "value": "Needs improvement"}
                    ]
                }
            ]
        }
    ]

    Example output:
    {
        "model_123": {
            "score": [80, 70],
            "text": ["Good code", "Needs improvement"]
        },
        "model_456": {
            "score": [90]
        }
    }

    Args:
        task_results: List of task results from miners

    Returns:
        Dictionary mapping model IDs to criterion types to lists of values
    """
    model_to_criteria_values = {}

    for result in task_results:
        # Each task result contains result_data for multiple models
        for result_data in result.result_data:
            model_id = getattr(result_data, "model", None)
            criteria_list = getattr(result_data, "criteria", [])

            if not model_id or not criteria_list:
                continue

            # Initialize dictionary for this model if not exists
            if model_id not in model_to_criteria_values:
                model_to_criteria_values[model_id] = {}

            # TODO: need validation method
            # Group criteria by type and collect values
            for criterion in criteria_list:
                criterion_type = criterion.get("type")
                if not criterion_type:
                    logger.warning(f"No criterion type found for criterion {criterion}")
                    continue

                if criterion_type == "text":
                    criterion_value = criterion.get("text_feedback", {})
                else:
                    criterion_value = criterion.get("value", {})

                # Only proceed if we have a value
                if criterion_value is not None:
                    # Initialize the list for this criterion type if not exists
                    if criterion_type not in model_to_criteria_values[model_id]:
                        model_to_criteria_values[model_id][criterion_type] = []

                    # Now append the value
                    model_to_criteria_values[model_id][criterion_type].append(
                        criterion_value
                    )

    return model_to_criteria_values


def calculate_criteria_averages(model_to_criteria_values: dict) -> dict:
    """
    Calculate average values for each criterion type by model, focusing on numeric types like "score".

    Example input:
    {
        "model_123": {
            "score": [80, 70],
            "text": ["Good code", "Needs improvement"]
        },
        "model_456": {
            "score": [90]
        }
    }

    Example output:
    {
        "model_123": {
            "score": 75.0,         # Average of [80, 70]
            "text": ["Good code", "Needs improvement"]  # Text values are kept as-is
        },
        "model_456": {
            "score": 90.0          # Average of [90]
        }
    }

    Args:
        model_to_criteria_values: Dictionary mapping model IDs to criterion types to lists of values

    Returns:
        Dictionary mapping model IDs to criterion types to averaged values (for numeric types)
    """
    model_criteria_type_to_avg = {}

    for model_id, criteria_types in model_to_criteria_values.items():
        model_criteria_type_to_avg[model_id] = {}

        for criterion_type, values in criteria_types.items():
            if not values:
                logger.warning(
                    f"No values found for model {model_id} and criterion type {criterion_type}"
                )
                continue

            # For score type, calculate average
            if criterion_type == "score" and all(
                isinstance(v, int | float) for v in values
            ):
                avg_value = sum(values) / len(values)
                model_criteria_type_to_avg[model_id][criterion_type] = avg_value
            elif criterion_type == "text":
                # For non-numeric types like text, just pass through the values
                model_criteria_type_to_avg[model_id][criterion_type] = " ".join(values)

    return model_criteria_type_to_avg


@staticmethod
async def create_initial_miner_scores(
    validator_task_id: str,
    miner_hotkey: str,
    task_results: list[TaskResult],
) -> bool:
    """
    Create initial miner scores based on task results for a specific miner.

    This function:
    1. Extracts criteria values from task results grouped by model and criterion type
    2. Calculates averages for numeric criterion types (e.g., "score")
    3. Maps these to the corresponding completion and criterion records in the database
    4. Creates or updates MinerScore records with the appropriate values

    Args:
        sf_task_id: Score feedback task ID
        miner_hotkey: Hotkey of the miner to update scores for
        task_results: List of task results containing score information

    Returns:
        Tuple containing success flag and error message (if any)
    """
    logger.info(
        f"Creating initial miner scores +++++++++++++++++++++++++++++ {validator_task_id} and miner {miner_hotkey}"
    )
    try:
        # Step 1: Find the miner response for this task and miner
        db_miner_response = await prisma.minerresponse.find_first(
            where={
                "validator_task_id": validator_task_id,
                "hotkey": miner_hotkey,
            },
        )

        if not db_miner_response:
            logger.error(
                f"No miner response found for task {validator_task_id} and miner {miner_hotkey}"
            )
            return False

        # Step 2: Get the SF task with completions and criteria
        sf_task = await ValidatorTask.prisma().find_unique(
            where={"id": validator_task_id},
            include=ValidatorTaskInclude(
                {"completions": {"include": {"criterion": True}}}
            ),
        )

        if not sf_task or not sf_task.completions:
            logger.error(f"No completions found for SF task {validator_task_id}")
            return False

        # Step 3: Extract and group criteria values from task results
        # Example result: {"model_123": {"score": [80, 70], "text": ["Good code", "Needs improvement"]}}

        from commons.human_feedback.utils import (
            extract_criteria_values_by_model_and_type,
        )

        model_to_criteria_values = extract_criteria_values_by_model_and_type(
            task_results
        )
        logger.info(f"Model to criteria values: {model_to_criteria_values}")

        # Step 4: Calculate averages for numeric criteria (e.g., scores)
        # Example result: {"model_123": {"score": 75.0, "text": ["Good code", "Needs improvement"]}}

        from commons.human_feedback.utils import calculate_criteria_averages

        model_criteria_type_to_values = calculate_criteria_averages(
            model_to_criteria_values
        )

        logger.info(f"Processed criteria values: {model_criteria_type_to_values}")

        # Step 5: Create mapping from completion_id and criterion type to criterion object
        # Example: {"completion_123": {"score": <Criterion object>, "text": <Criterion object>}}
        completion_criteria_map: dict[str, dict[str, Criterion]] = {}
        for completion in sf_task.completions:
            completion_id = completion.completion_id
            completion_criteria_map[completion_id] = {}

            if not completion.criterion:
                logger.warning(f"No criterion found for completion {completion_id}")
                continue

            for criterion in completion.criterion:
                criterion_type = (
                    criterion.criteria_type.lower()
                )  # Ensure lowercase comparison
                completion_criteria_map[completion_id][criterion_type] = criterion

        # Step 6: Update database records in a transaction
        async with prisma.tx() as tx:
            updates_count = 0

            # Process each model's criteria values
            for model_id, criteria_values in model_criteria_type_to_values.items():
                if model_id not in completion_criteria_map:
                    logger.warning(f"No matching completion found for model {model_id}")
                    continue

                model_criteria: dict[str, Criterion] = completion_criteria_map[model_id]

                # Process each criterion type (score, text, etc.)
                for criterion_type, values in criteria_values.items():
                    if criterion_type not in model_criteria:
                        logger.warning(
                            f"No criterion of type '{criterion_type}' found for model {model_id}"
                        )
                        continue

                    criterion = model_criteria[criterion_type]
                    scores_data = {}

                    # Create appropriate scores object based on criterion type
                    if criterion_type == "score":
                        # For score type, create a structured Scores object
                        from dojo.protocol import Scores

                        scores_obj = Scores(
                            raw_score=values,  # This is the calculated average
                            # Initialize other scores as None
                            rank_id=None,
                            normalised_score=None,
                            ground_truth_score=None,
                            cosine_similarity_score=None,
                            normalised_cosine_similarity_score=None,
                            cubic_reward_score=None,
                            icc_score=None,
                        )
                        scores_data = scores_obj.model_dump()
                    elif criterion_type == "text":
                        # For text type, store as a list or join into a single string
                        scores_data = TextFeedbackScore(
                            tf_score=None, text_feedback=values
                        ).model_dump()
                    else:
                        # For other criterion types, store the value directly
                        pass

                    # Use upsert to create or update the score record
                    upserted_score = await tx.minerscore.upsert(
                        where={
                            "criterion_id_miner_response_id": {
                                "criterion_id": criterion.id,
                                "miner_response_id": db_miner_response.id,
                            }
                        },
                        data={
                            "create": MinerScoreCreateInput(
                                miner_response_id=db_miner_response.id,
                                criterion_id=criterion.id,
                                scores=Json(json.dumps(scores_data)),
                            ),
                            "update": MinerScoreUpdateInput(
                                scores=Json(json.dumps(scores_data)),
                            ),
                        },
                    )

                    logger.debug(
                        f"Upserted score {upserted_score.id} for criterion type {criterion_type}"
                    )
                    updates_count += 1

            logger.info(
                f"Successfully updated {updates_count} scores for miner {miner_hotkey} on task {validator_task_id}"
            )
            return updates_count > 0

    except Exception as e:
        logger.error(
            f"Error updating scores for miner {miner_hotkey} on task {validator_task_id}: {e}"
        )
        return False
