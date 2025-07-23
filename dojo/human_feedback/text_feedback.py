"""Text Feedback component of the Human Feedback Loop."""

import asyncio
import traceback
from typing import TYPE_CHECKING, List

from loguru import logger

from database.orm import ORM
from database.prisma.enums import HFLStatusEnum, TaskTypeEnum
from database.prisma.models import HFLState, MinerResponse, ValidatorTask
from database.prisma.types import ValidatorTaskInclude
from dojo.api.synthetic_api import MinerFeedback, SyntheticAPI, TextFeedbackRequest
from dojo.protocol import (
    CriteriaType,
    CriteriaTypeEnum,
    SyntheticTaskSynapse,
    TaskResult,
    TextCriteria,
    TextFeedbackEvent,
)
from dojo.utils import get_new_uuid, set_expire_time

from .hfl_helpers import HFLManager
from .sanitize import sanitize_miner_feedback
from .types import HFLInterval
from .utils import (
    create_initial_miner_scores,
    extract_text_feedback_from_results,
    is_valid_feedback,
)

if TYPE_CHECKING:
    from neurons.validator import Validator


async def create_text_feedback_task(
    validator_task: SyntheticTaskSynapse, completion_id: str
) -> SyntheticTaskSynapse | None:
    """
    Generates a text criteria task based on a selected validator task and completion.
    This task will be used to evaluate the quality of miners' scoring.

    Args:
        validator_task: The original validator task
        completion_id: ID of the selected completion to be evaluated

    Returns:
        A new task for text-based evaluation, or None if generation fails
    """
    try:
        # Find the selected completion from the original task
        selected_completion = next(
            (
                c
                for c in (validator_task.completion_responses or [])
                if c.completion_id == completion_id
            ),
            None,
        )
        if not selected_completion:
            logger.error(
                f"Completion {completion_id} not found in task {validator_task.task_id}"
            )
            return None

        # Set text criteria for completion
        text_criteria: List[CriteriaType] = [
            TextCriteria(
                query="What specific improvements could make this output more accurate, complete, or relevant to the prompt?",
                text_feedback="",
            ),
        ]
        selected_completion.criteria_types = text_criteria

        # Create a new task with the same prompt but different criteria type
        new_tf_task = SyntheticTaskSynapse(
            task_id=get_new_uuid(),
            previous_task_id=validator_task.task_id,
            prompt=validator_task.prompt,
            task_type=TaskTypeEnum.TEXT_FEEDBACK,
            expire_at=set_expire_time(int(HFLInterval.TASK_DEADLINE)),
            completion_responses=[
                selected_completion
            ],  # Only include the selected completion
        )

        logger.info(
            f"Generated text criteria task with ID: {new_tf_task.task_id} "
            f"based on task: {validator_task.task_id}"
        )
        return new_tf_task

    except Exception as e:
        logger.error(f"Error generating text criteria task: {e}")
        return None


async def fetch_miner_feedback_for_task(
    validator: "Validator", task: ValidatorTask
) -> tuple[list[MinerFeedback], list[MinerResponse]]:
    """
    Fetch and process miner feedback for a task.

    Args:
        validator: The Validator instance
        task: The task to fetch feedback for

    Returns:
        Tuple of (miner_feedbacks, valid_responses)
    """
    # Initialize result lists
    miner_feedbacks: List[MinerFeedback] = []
    valid_responses: List[MinerResponse] = []
    responses_needing_fetch: List[MinerResponse] = []

    # Identify valid miner responses
    valid_miner_responses = [resp for resp in task.miner_responses or [] if resp.hotkey]

    if not valid_miner_responses:
        logger.warning(f"No valid miner responses found for task {task.id}")
        return [], []

    # Filter out miner responses that have already been given feedback
    for resp in valid_miner_responses:
        # Extract feedback text directly from the task_result
        feedback_text, _ = extract_text_feedback_from_results(resp.task_result)
        if feedback_text and feedback_text != "" and is_valid_feedback(feedback_text):
            # Valid feedback already exists
            logger.info(f"Feedback text: {feedback_text} from miner {resp.hotkey}")
            miner_feedbacks.append(
                MinerFeedback(
                    hotkey=resp.hotkey,
                    miner_response_id=resp.id,
                    feedback=feedback_text,
                )
            )
            valid_responses.append(resp)
            logger.debug(f"Using existing feedback from miner {resp.hotkey}")
        else:
            # No valid feedback, need to fetch
            logger.info(f"No feedback from miner {resp.hotkey}")
            responses_needing_fetch.append(resp)

    if not responses_needing_fetch:
        logger.info(
            "No miner responses needing fetch, have already fetched all feedback"
        )
        return miner_feedbacks, valid_responses

    logger.info(f"Miner Feedback: {miner_feedbacks}")
    logger.info(
        f"Fetching results for {[(resp.hotkey, resp.task_result) for resp in responses_needing_fetch]}"
    )
    # Create fetch tasks for miner responses that need results
    fetch_tasks = [
        asyncio.create_task(
            validator._get_task_results_from_miner(
                miner_hotkey=resp.hotkey, validator_task_id=task.id
            )
        )
        for resp in responses_needing_fetch
    ]

    # A list of TaskResult gathered from multiple workers for each miner
    task_results_list = await asyncio.gather(*fetch_tasks, return_exceptions=True)

    # A list of miner responses that have been updated with the new results
    for i, results in enumerate(task_results_list):
        if isinstance(results, BaseException):
            logger.warning(
                f"Error fetching results for miner {responses_needing_fetch[i].hotkey}: {results}"
            )
            continue

        if not results:  # Empty or None result
            continue

        miner_response = responses_needing_fetch[i]

        logger.info(f"original result from miners........ {results}")

        sanitized_result = await sanitize_text_feedback(results, task.prompt)
        # Update the database with fresh results
        success = await ORM.update_miner_task_results(
            miner_hotkey=miner_response.hotkey,
            validator_task_id=task.id,
            task_results=sanitized_result,
        )

        if not success:
            logger.error(
                f"Error updating miner task results for miner {miner_response.hotkey}"
            )
            continue

        logger.info(f"Task results for miner {miner_response.hotkey}: {results}")
        # Create initial miner scores with their relations
        # Extract text feedback
        feedback_text, selected_task_result = extract_text_feedback_from_results(
            sanitized_result
        )
        logger.info(
            f"Selected Feedback text: {feedback_text}, and task result: {selected_task_result}"
        )

        if feedback_text:
            miner_feedbacks.append(
                MinerFeedback(
                    hotkey=miner_response.hotkey,
                    miner_response_id=miner_response.id,
                    feedback=feedback_text,
                )
            )
            valid_responses.append(miner_response)

            success = await create_initial_miner_scores(
                validator_task_id=task.id,
                miner_hotkey=miner_response.hotkey,
                task_results=selected_task_result,
            )
            if not success:
                logger.error(
                    f"Error creating initial miner scores for miner {miner_response.hotkey}"
                )

    return miner_feedbacks, valid_responses


async def send_text_feedback_to_synthetic_api(
    validator_task_id: str,
    hfl_state: HFLState,
    miner_feedback: list[MinerFeedback],
) -> str | None:
    """
    Process text feedback and send to the Synthetic API for improvement.

    Args:
        validator_task_id: ID of the current validator task
        hfl_state: HFL state object containing original task info
        miner_feedback: List of miner feedback to send

    Returns:
        Synthetic request ID if successful, None otherwise
    """
    try:
        if not miner_feedback:
            logger.warning(f"No miner feedback provided for task {validator_task_id}")
            return None

        # Get original task
        original_task = await ORM.get_validator_task_by_id(
            task_id=validator_task_id,
            include=ValidatorTaskInclude(
                completions={"include": {"criterion": {"include": {"scores": True}}}}
            ),
        )

        if not original_task or not original_task.completions:
            logger.warning(
                f"Could not find original task or completions for {hfl_state.original_task_id}"
            )
            return None

        # TODO: KIV
        if (
            original_task.completions[0].completion_id
            != hfl_state.selected_completion_id
        ):
            logger.error(
                f"Selected completion ID {hfl_state.selected_completion_id} does not match the original task completion ID {original_task.completions[0].completion_id}"
            )
            return None

        # Get the completion from the original task
        base_completion = original_task.completions[0].completion

        # Create the TextFeedbackRequest object
        text_feedback_request = TextFeedbackRequest(
            base_prompt=original_task.prompt,
            base_code=base_completion,
            miner_feedbacks=miner_feedback,
        )

        # Send to synthetic API
        logger.info(
            f"Sending {len(miner_feedback)} feedback responses to synthetic API"
        )
        syn_req_id = await SyntheticAPI.send_text_feedback(text_feedback_request)

        if not syn_req_id:
            logger.error(
                f"Failed to send text feedback to synthetic API for task {validator_task_id}"
            )
            return None

        # Update HFL state with the synthetic request ID
        hfl_state = await HFLManager.update_state(
            hfl_state_id=hfl_state.id,
            updates={
                "status": HFLStatusEnum.TF_COMPLETED,
                "current_synthetic_req_id": syn_req_id,
            },
            event_data=TextFeedbackEvent(
                task_id=validator_task_id,
                iteration=hfl_state.current_iteration,
                message=f"Sent {len(miner_feedback)} text feedback to synthetic API for task {validator_task_id}, got syn_req_id: {syn_req_id}",
            ),
        )

        logger.info(
            f"Sent text feedback to synthetic API for task {validator_task_id}, got syn_req_id: {syn_req_id}"
        )
        return syn_req_id

    except Exception as e:
        logger.error(f"Error processing text feedback with synthetic API: {str(e)}")
        logger.debug(f"Traceback: {traceback.format_exc()}")
        return None


async def get_task_synapse_for_retry(task_id: str) -> SyntheticTaskSynapse | None:
    """
    Retrieve and convert a validator task to a SyntheticTaskSynapse for retry purposes.

    Args:
        task_id: The task ID to retrieve

    Returns:
        SyntheticTaskSynapse ready for retry or None if conversion fails
    """
    try:
        # Fetch the task from the database
        task = await ORM.get_validator_task_by_id(task_id)

        if not task:
            logger.warning(f"Task with ID {task_id} not found")
            return None

        # Convert to SyntheticTaskSynapse using the existing mapper function
        from database.mappers import map_validator_task_to_task_synapse_object

        task_synapse = map_validator_task_to_task_synapse_object(task)
        task_synapse.expire_at = set_expire_time(int(HFLInterval.TASK_DEADLINE))
        if task_synapse.completion_responses:
            for completion in task_synapse.completion_responses:
                if not completion.criteria_types or len(completion.criteria_types) == 0:
                    # For TEXT_FEEDBACK tasks, add default TextCriteria
                    completion.criteria_types = [
                        TextCriteria(
                            query="What specific improvements could make this output more accurate, complete, or relevant to the prompt?",
                            text_feedback="",
                        )
                    ]
        return task_synapse

    except Exception as e:
        logger.error(f"Error retrieving task {task_id}: {e}")
        logger.debug(f"Traceback: {traceback.format_exc()}")
        return None


async def sanitize_text_feedback(
    results: list[TaskResult], question_prompt: str
) -> list[TaskResult]:
    """
    Sanitize text feedback for each TaskResult.
    Replace invalid text feedback with "invalid" instead of removing.

    Args:
        results (List[TaskResult]): List of task results from miners

    Returns:
        List[TaskResult]: Results with sanitized text feedback
    """
    sanitized_results = []

    for task_result in results:
        # Create a copy of the task result to avoid modifying the original
        sanitized_task_result = task_result.model_copy()

        # Ensure result_data exists and is a list
        if not sanitized_task_result.result_data:
            continue

        sanitized_result_data = []

        for result_item in sanitized_task_result.result_data:
            # Check if criteria exists
            if not hasattr(result_item, "criteria") or not result_item.criteria:
                continue

            sanitized_criteria = []

            for criterion in result_item.criteria:
                # Only process text type criteria
                if criterion.get("type", "") != CriteriaTypeEnum.TEXT.value:
                    logger.debug(
                        f"Skipping sanitization for non-text criteria: {criterion.get('type', 'unknown')}"
                    )
                    sanitized_criteria.append(criterion)
                    continue

                # Get text feedback
                text_feedback = (
                    criterion["text_feedback"].strip()
                    if criterion["text_feedback"]
                    else ""
                )

                # Skip sanitization for empty feedback
                if not text_feedback:
                    logger.info("Empty text feedback found - skipping sanitization")
                    sanitized_criterion = criterion.copy()
                    sanitized_criterion["text_feedback"] = ""  # Keep as empty
                    sanitized_criteria.append(sanitized_criterion)
                    continue

                # Apply sanitization checks
                sanitization_result = await sanitize_miner_feedback(
                    text_feedback, question_prompt
                )
                if sanitization_result.is_safe:
                    # Keep original text feedback if valid
                    sanitized_criterion = criterion.copy()
                    sanitized_criterion["text_feedback"] = (
                        sanitization_result.sanitized_feedback
                    )
                else:
                    logger.warning(
                        f"Sanitization failed for validator task id: {task_result.task_id} with text feedback: {text_feedback}"
                    )
                    # Replace with "invalid" if not valid
                    sanitized_criterion = criterion.copy()
                    sanitized_criterion["text_feedback"] = sanitization_result.reason

                sanitized_criteria.append(sanitized_criterion)

            # Update result item with sanitized criteria
            result_item.criteria = sanitized_criteria
            sanitized_result_data.append(result_item)

        # Update task result with sanitized result data
        sanitized_task_result.result_data = sanitized_result_data
        sanitized_results.append(sanitized_task_result)

    return sanitized_results


async def dummy_sanitize_text_feedback(text: str) -> bool:
    return True


if __name__ == "__main__":

    async def run_tests():
        pass

    asyncio.run(run_tests())
