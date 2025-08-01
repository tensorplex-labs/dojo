"""Score Feedback component of the Human Feedback Loop."""

import traceback
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from kami import AxonInfo
from loguru import logger

from database.orm import ORM
from database.prisma.enums import HFLStatusEnum, TaskTypeEnum
from database.prisma.models import HFLState, ValidatorTask
from database.prisma.types import HFLStateUpdateInput, ValidatorTaskUpdateInput
from dojo.api.synthetic_api import SyntheticAPI
from dojo.objects import ObjectManager
from dojo.protocol import ScoreFeedbackEvent, SyntheticTaskSynapse, TextFeedbackEvent
from dojo.utils import datetime_as_utc, iso8601_str_to_datetime, set_expire_time

from .hfl_helpers import HFLManager
from .utils import create_initial_miner_scores, map_human_feedback_to_task_synapse

if TYPE_CHECKING:
    from neurons.validator import Validator


async def create_score_feedback_task(
    validator: "Validator",
    tf_task: ValidatorTask,
    hfl_state: HFLState,
) -> ValidatorTask | None:
    """
    Create a score feedback task based on text feedback improvements.

    Args:
        validator: Validator instance for sending requests
        tf_task_id: Text feedback task ID
        hfl_state: Current HFL state

    Returns:
        Created validator task or None if creation fails
    """
    try:
        if not hfl_state.current_synthetic_req_id:
            logger.error(f"No synthetic request ID for HFL state {hfl_state.id}")
            return None

        if not tf_task.completions:
            logger.error(f"No completions found for TF task {tf_task.id}")
            return None

        # Get improved task from synthetic API (raw response)
        success, improved_task_data = await SyntheticAPI.get_improved_task(
            hfl_state.current_synthetic_req_id
        )

        if not success:
            await handle_synthetic_generation_failure(
                tf_task_id=tf_task.id,
                hfl_state=hfl_state,
                synthetic_req_id=hfl_state.current_synthetic_req_id,
            )
            return None

        if not improved_task_data:
            logger.warning(
                f"No improved task data available yet for {hfl_state.current_synthetic_req_id}. "
                f"Will try again in next cycle."
            )
            return None

        # Map the raw response to a SyntheticTaskSynapse
        task_synapse = map_human_feedback_to_task_synapse(
            improved_task_data,
            original_model_name=tf_task.completions[0].model,
            original_completion_id=tf_task.completions[0].completion_id,
        )

        if not task_synapse or not task_synapse.completion_responses:
            logger.error(
                "Failed to map improved task data to SyntheticTaskSynapse or no completion responses"
            )
            return None

        # Send to miners as CODE_GENERATION
        task_synapse.task_type = TaskTypeEnum.CODE_GENERATION

        obfuscated_model_to_model, completion_responses = (
            validator.obfuscate_model_names(task_synapse.completion_responses)
        )

        task_synapse.completion_responses = completion_responses

        # Get active miners for SF task
        active_miners = await validator.get_active_miner_uids()
        if len(active_miners) <= 0:
            logger.error(f"No active miners found for SF task for {tf_task.id}")
            return None

        # Send to miners
        miner_responses: list[SyntheticTaskSynapse] = await send_hfl_request(
            synapse=task_synapse,
            task_type=TaskTypeEnum.SCORE_FEEDBACK,
            axons=validator._retrieve_axons(active_miners),
        )
        logger.info(
            f"Received {len(miner_responses) if miner_responses else 0} miner responses from: {[resp.miner_hotkey for resp in (miner_responses or [])]}"
        )

        if not miner_responses:
            logger.error(f"Failed to send improved task to miners for {tf_task.id}")
            return None

        # deobfuscate model names
        task_synapse.completion_responses = validator.deobfuscate_model_names(
            task_synapse.completion_responses or [],
            obfuscated_model_to_model,
        )

        # Insert SCORE_FEEDBACK task type to database
        task_synapse.task_type = TaskTypeEnum.SCORE_FEEDBACK

        # Save SF task and update HFL state
        validator_task, updated_hfl_state = await ORM.save_sf_task(
            validator_task=task_synapse,
            miner_responses=miner_responses,
            hfl_state=hfl_state,
            previous_task_id=tf_task.id,
            human_feedback_response=improved_task_data,
        )

        if not validator_task:
            logger.error(f"Failed to save SF task for {tf_task.id}")
            return None

        logger.info(f"Created SF task {validator_task.id} for {tf_task.id}")
        return validator_task

    except Exception as e:
        logger.error(f"Error creating SF task: {e}")
        logger.debug(f"Traceback: {traceback.format_exc()}")
        return None


async def process_score_feedback_task(
    validator: "Validator",
    sf_task: ValidatorTask,
    hfl_state: HFLState,
) -> bool:
    """
    Process results from a score feedback task.

    Args:
        validator: Validator instance
        sf_task_id: Score feedback task ID
        hfl_state: Current HFL state

    Returns:
        True if processing was successful, False otherwise
    """
    try:
        if not sf_task or not sf_task.miner_responses:
            logger.error(f"No SF task or miner responses found for {sf_task.id}")
            return False

        # Process each miner response
        success_count = 0
        for miner_response in sf_task.miner_responses:
            if not miner_response.hotkey:
                logger.warning(
                    f"Skipping miner response {miner_response.id} due to missing hotkey, hotkey: {miner_response.hotkey} for sf task {sf_task.id}"
                )
                continue

            # Get task results from miner
            task_results = await validator._get_task_results_from_miner(
                miner_hotkey=miner_response.hotkey,
                validator_task_id=sf_task.id,
            )

            if not task_results:
                continue

            # Update task results in database
            success = await ORM.update_miner_task_results(
                miner_hotkey=miner_response.hotkey,
                validator_task_id=sf_task.id,
                task_results=task_results,
            )

            if not success:
                logger.warning(
                    f"Failed to store task results for miner {miner_response.hotkey}"
                )
                continue

            # Create initial miner scores with their relations
            score_update_success = await create_initial_miner_scores(
                validator_task_id=sf_task.id,
                miner_hotkey=miner_response.hotkey,
                task_results=task_results,
            )

            if score_update_success:
                success_count += 1

        if success_count == 0:
            logger.debug(f"No miner task results are updated for {sf_task.id}")
            return False

        # Update HFL state to SF_COMPLETED
        event = ScoreFeedbackEvent(
            type=HFLStatusEnum.SF_COMPLETED,
            task_id=sf_task.id,
            iteration=hfl_state.current_iteration,
            message=f"Successfully processed SF task {sf_task.id} with {success_count} results",
        )

        updated_hfl_state = await HFLManager.update_state(
            hfl_state_id=hfl_state.id,
            updates=HFLStateUpdateInput(status=HFLStatusEnum.SF_COMPLETED),
            event_data=event,
        )

        if not updated_hfl_state:
            logger.error(f"Failed to update HFL state for {sf_task.id}")
            return False

        logger.info(
            f"Successfully processed SF task {sf_task.id} with {success_count} results"
        )
        return True

    except Exception as e:
        logger.error(f"Error processing SF task {sf_task.id}: {e}")
        logger.debug(f"Traceback: {traceback.format_exc()}")
        return False


async def send_hfl_request(
    synapse: SyntheticTaskSynapse,
    task_type: TaskTypeEnum,
    axons: list[AxonInfo],
) -> list[SyntheticTaskSynapse]:
    """
    Send Human Feedback Loop requests to miners.

    Args:
        validator: The validator instance (used for dendrite and metagraph)
        synapse: Task synapse object with request details
        task_type: Type of HFL task
        axons: List of axons to send requests to

    Returns:
        List of valid miner responses or None
    """
    if not synapse.completion_responses:
        logger.error(f"No completion responses for synapse: {synapse}")
        return []

    if not axons:
        logger.warning(f"No axons for {task_type} task: {synapse.task_id}")
        return []

    logger.info(
        f"Sending {task_type} request to miners: {[axon.hotkey for axon in axons]}"
    )

    # Send request to miners
    _validator = await ObjectManager.get_validator()
    miner_responses = await _validator.send_synthetic_task(synapse=synapse, axons=axons)

    # Process responses
    valid_miner_responses: list[SyntheticTaskSynapse] = []
    for response, axon in zip(miner_responses, axons):
        if not response.body.ack:
            continue
        task = response.body
        task.miner_hotkey = axon.hotkey
        task.miner_coldkey = axon.coldkey
        valid_miner_responses.append(task)

    if not valid_miner_responses:
        logger.info(f"No valid responses received for {task_type} task... skipping")
        return []

    return valid_miner_responses


async def handle_synthetic_generation_failure(
    tf_task_id: str, hfl_state: HFLState, synthetic_req_id: str
) -> None:
    """
    Handle synthetic generation failure by updating HFL state and task expiration.

    Args:
        tf_task_id: ID of the text feedback task
        hfl_state: Current HFL state
        synthetic_req_id: Synthetic request ID that failed
    """
    try:
        logger.debug(f"Handling synthetic generation failure for task {tf_task_id}")
        # Get current retry count
        current_retry_count = hfl_state.syn_retry_count or 0
        MAX_RETRY_ATTEMPTS = 5

        # Prepare event data
        event_timestamp = datetime_as_utc(datetime.now(timezone.utc))

        if current_retry_count >= MAX_RETRY_ATTEMPTS:
            # If we've exceeded max retries, mark as failed
            event_data = TextFeedbackEvent(
                type=HFLStatusEnum.TF_FAILED,
                task_id=tf_task_id,
                iteration=hfl_state.current_iteration,
                timestamp=event_timestamp,
                syn_req_id=synthetic_req_id,
            )

            await ORM.update_hfl_state_and_task(
                hfl_state_id=hfl_state.id,
                validator_task_id=tf_task_id,
                state_updates=HFLStateUpdateInput(
                    status=HFLStatusEnum.TF_FAILED,
                    syn_retry_count=current_retry_count + 1,
                ),
                task_updates={},  # No task updates needed for failed state
                event_data=event_data,
            )

            logger.error(
                f"Task {tf_task_id} failed after {MAX_RETRY_ATTEMPTS} synthetic generation attempts"
            )
        else:
            # Otherwise, increment retry count and move back to TF_PENDING
            event_data = TextFeedbackEvent(
                type=HFLStatusEnum.TF_PENDING,
                task_id=tf_task_id,
                iteration=hfl_state.current_iteration,
                timestamp=event_timestamp,
                syn_req_id=synthetic_req_id,
            )

            # Calculate new expiration time
            new_expire_time = set_expire_time(900)

            await ORM.update_hfl_state_and_task(
                hfl_state_id=hfl_state.id,
                validator_task_id=tf_task_id,
                state_updates=HFLStateUpdateInput(
                    status=HFLStatusEnum.TF_PENDING,
                    syn_retry_count=current_retry_count + 1,
                    current_synthetic_req_id=None,
                ),
                task_updates=ValidatorTaskUpdateInput(
                    expire_at=iso8601_str_to_datetime(new_expire_time),
                    is_processed=False,  # Make sure the task gets picked up again
                ),
                event_data=event_data,
            )

            logger.info(
                f"Moved task {tf_task_id} back to TF_PENDING for retry (attempt {current_retry_count + 1}/{MAX_RETRY_ATTEMPTS})"
            )
    except Exception as e:
        logger.error(
            f"Failed to handle synthetic generation failure for task {tf_task_id}: {e}"
        )
        logger.debug(f"Traceback: {traceback.format_exc()}")

    logger.error(
        f"Failed to get improved task for synthetic request ID: {synthetic_req_id}"
    )
