"""Text Feedback component of the Human Feedback Loop."""

import asyncio
import traceback
from typing import List

from bittensor.utils.btlogging import logging as logger

import dojo
from commons.dataset.synthetic import SyntheticAPI
from commons.dataset.types import MinerFeedback, TextFeedbackRequest
from commons.hfl_heplers import HFLManager
from commons.human_feedback.utils import (
    create_initial_miner_scores,
    extract_text_feedback_from_results,
)
from commons.orm import ORM
from commons.utils import get_new_uuid, set_expire_time
from database.prisma.enums import HFLStatusEnum, TaskTypeEnum
from database.prisma.models import HFLState, MinerResponse, ValidatorTask
from database.prisma.types import ValidatorTaskInclude
from dojo.protocol import (
    CriteriaType,
    TaskSynapseObject,
    TextCriteria,
    TextFeedbackEvent,
)
from neurons.validator import Validator


async def create_text_feedback_task(
    validator_task: TaskSynapseObject, completion_id: str
) -> TaskSynapseObject | None:
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

        prompt = f"""Please analyze this output and suggest specific improvements:
        Prompt: {validator_task.prompt}
        """
        # Create a new task with the same prompt but different criteria type
        new_tf_task = TaskSynapseObject(
            task_id=get_new_uuid(),
            previous_task_id=validator_task.task_id,
            prompt=prompt,
            task_type=TaskTypeEnum.TEXT_FEEDBACK,
            expire_at=set_expire_time(int(dojo.HFL_TASK_DEADLINE)),
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
    validator: Validator, task: ValidatorTask
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
    valid_miner_responses = [
        resp for resp in task.miner_responses or [] if resp.hotkey and resp.dojo_task_id
    ]

    if not valid_miner_responses:
        logger.warning(f"No valid miner responses found for task {task.id}")
        return [], []

    # Filter out miner responses that have already been given feedback
    for resp in valid_miner_responses:
        # Extract feedback text directly from the task_result
        feedback_text = extract_text_feedback_from_results(resp.task_result)
        if feedback_text and feedback_text != "":
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
                miner_hotkey=resp.hotkey,
                dojo_task_id=resp.dojo_task_id,
            )
        )
        for resp in responses_needing_fetch
    ]

    # Execute all fetch tasks concurrently
    task_results_list = await asyncio.gather(*fetch_tasks, return_exceptions=True)

    # A list of miner responses that have been updated with the new results
    for i, result in enumerate(task_results_list):
        if isinstance(result, BaseException):
            logger.warning(
                f"Error fetching results for miner {responses_needing_fetch[i].hotkey}: {result}"
            )
            continue

        if not result:  # Empty or None result
            continue

        miner_response = responses_needing_fetch[i]

        logger.info(f"result from miners........ {result}")
        # Update the database with fresh results
        success = await ORM.update_miner_task_results(
            miner_hotkey=miner_response.hotkey,
            dojo_task_id=miner_response.dojo_task_id,
            task_results=result,
        )

        if not success:
            logger.error(
                f"Error updating miner task results for miner {miner_response.hotkey}"
            )
            continue

        logger.info(f"Task results for miner {miner_response.hotkey}: {result}")
        # Create initial miner scores with their relations
        success = await create_initial_miner_scores(
            validator_task_id=task.id,
            miner_hotkey=miner_response.hotkey,
            task_results=result,
        )

        if not success:
            logger.error(
                f"Error creating initial miner scores for miner {miner_response.hotkey}"
            )

        # Extract text feedback
        feedback_text = extract_text_feedback_from_results(result)
        if feedback_text:
            miner_feedbacks.append(
                MinerFeedback(
                    hotkey=miner_response.hotkey,
                    miner_response_id=miner_response.id,
                    feedback=feedback_text,
                )
            )
            valid_responses.append(miner_response)

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


async def get_task_synapse_for_retry(task_id: str) -> TaskSynapseObject | None:
    """
    Retrieve and convert a validator task to a TaskSynapseObject for retry purposes.

    Args:
        task_id: The task ID to retrieve

    Returns:
        TaskSynapseObject ready for retry or None if conversion fails
    """
    try:
        # Fetch the task from the database
        task = await ORM.get_validator_task_by_id(task_id)

        if not task:
            logger.warning(f"Task with ID {task_id} not found")
            return None

        # Convert to TaskSynapseObject using the existing mapper function
        from database.mappers import map_validator_task_to_task_synapse_object

        task_synapse = map_validator_task_to_task_synapse_object(task)
        task_synapse.expire_at = set_expire_time(int(dojo.HFL_TASK_DEADLINE))
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
