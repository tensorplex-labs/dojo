"""Score Feedback component of the Human Feedback Loop."""

import traceback
from datetime import datetime, timezone

from bittensor.core.chain_data.axon_info import AxonInfo
from bittensor.utils.btlogging import logging as logger

from commons.dataset.synthetic import SyntheticAPI
from commons.dataset.types import HumanFeedbackResponse
from commons.hfl_heplers import HFLManager
from commons.human_feedback.utils import (
    create_initial_miner_scores,
    map_human_feedback_to_task_synapse,
)
from commons.orm import ORM
from commons.utils import datetime_as_utc
from database.prisma.enums import HFLStatusEnum, TaskTypeEnum
from database.prisma.models import HFLState, ValidatorTask
from database.prisma.types import HFLStateUpdateInput
from dojo.protocol import ScoreFeedbackEvent, TaskSynapseObject
from neurons.validator import Validator


async def get_improved_task_from_synthetic_api(
    syn_req_id: str,
) -> HumanFeedbackResponse | None:
    """
    Get improved task from synthetic API based on request ID as a HumanFeedbackResponse.

    Args:
        syn_req_id: Synthetic API request ID

    Returns:
        HumanFeedbackResponse object or None if not found/error
    """
    response = await SyntheticAPI.get_improved_task_raw(syn_req_id)
    logger.info(f"Response: {response}")
    return response


async def create_score_feedback_task(
    validator: Validator,
    tf_task_id: str,
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

        # Get improved task from synthetic API (raw response)
        improved_task_data = await get_improved_task_from_synthetic_api(
            hfl_state.current_synthetic_req_id
        )

        if not improved_task_data:
            logger.info(
                f"No improved task data available yet for {hfl_state.current_synthetic_req_id}. "
                f"Will try again in next cycle."
            )
            return None

        # Map the raw response to a TaskSynapseObject
        task_synapse = map_human_feedback_to_task_synapse(improved_task_data)

        if not task_synapse or not task_synapse.completion_responses:
            logger.error(
                "Failed to map improved task data to TaskSynapseObject or no completion responses"
            )
            return None

        obfuscated_model_to_model, completion_responses = (
            validator.obfuscate_model_names(task_synapse.completion_responses)
        )

        task_synapse.completion_responses = completion_responses

        # Get active miners for SF task
        active_miners = await get_active_miners_for_hfl(validator)
        if not active_miners:
            logger.error(f"No active miners found for SF task for {tf_task_id}")
            return None

        axons = [validator.metagraph.axons[miner_uid] for miner_uid in active_miners]

        # Send to miners
        miner_responses = await send_hfl_request(
            validator=validator,
            synapse=task_synapse,
            task_type=TaskTypeEnum.SCORE_FEEDBACK,
            axons=axons,
        )

        if not miner_responses:
            logger.error(f"Failed to send improved task to miners for {tf_task_id}")
            return None

        # deobfuscate model names
        for response in miner_responses:
            if response.completion_responses:
                for completion in response.completion_responses:
                    completion.model = obfuscated_model_to_model.get(
                        completion.model, completion.model
                    )

        # Save SF task and update HFL state
        validator_task, updated_hfl_state = await ORM.save_sf_task(
            validator_task=task_synapse,
            miner_responses=miner_responses,
            hfl_state=hfl_state,
            previous_task_id=tf_task_id,
            human_feedback_response=improved_task_data,
        )

        if not validator_task:
            logger.error(f"Failed to save SF task for {tf_task_id}")
            return None

        logger.info(f"Created SF task {validator_task.id} for {tf_task_id}")
        return validator_task

    except Exception as e:
        logger.error(f"Error creating SF task: {e}")
        logger.debug(f"Traceback: {traceback.format_exc()}")
        return None


async def process_score_feedback_task(
    validator: Validator,
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
            if not miner_response.hotkey or not miner_response.dojo_task_id:
                continue

            # Get task results from miner
            task_results = await validator._get_task_results_from_miner(
                miner_hotkey=miner_response.hotkey,
                dojo_task_id=miner_response.dojo_task_id,
            )

            if not task_results:
                continue

            # Update task results in database
            success = await ORM.update_miner_task_results(
                miner_hotkey=miner_response.hotkey,
                dojo_task_id=miner_response.dojo_task_id,
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

        # Update HFL state to SF_COMPLETED
        event = ScoreFeedbackEvent(
            type=HFLStatusEnum.SF_COMPLETED,
            task_id=sf_task.id,
            iteration=hfl_state.current_iteration,
            timestamp=datetime_as_utc(datetime.now(timezone.utc)),
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


async def get_active_miners_for_hfl(
    validator,
    subset_size: int | None = None,
    min_miners: int = 3,
) -> list[int] | None:
    """
    Get a subset of active miners suitable for HFL tasks.

    Args:
        validator: The Validator instance containing miner information
        subset_size: The desired number of miners to return
        min_miners: Minimum number of miners required (raises error if not met)

    Returns:
        List of UID integers for selected miners
    """
    # Get the current active miner UIDs from the validator
    async with validator._uids_alock:
        active_miners = sorted(list(validator._active_miner_uids))

    if not active_miners:
        logger.warning(
            f"No active miners available for HFL tasks: {validator._active_miner_uids}"
        )
        return None

    # Make sure we have enough miners
    if len(active_miners) < min_miners:
        logger.warning(
            f"Not enough active miners for HFL tasks. Need at least {min_miners}, "
            f"but only found {len(active_miners)}"
        )
        return None

    if not subset_size:
        logger.info(
            f"No subset size provided, returning all {len(active_miners)} active miners"
        )
        return active_miners

    # Safeguard against subset size being greater than the number of active miners
    subset_size = min(subset_size, len(active_miners))

    # Randomly select the requested number of miners
    import random

    selected_miners = random.sample(active_miners, subset_size)

    logger.info(
        f"Selected {len(selected_miners)} miners for HFL task from {len(active_miners)} active miners"
    )
    return selected_miners


async def send_hfl_request(
    validator: Validator,
    synapse: TaskSynapseObject,
    task_type: TaskTypeEnum,
    axons: list[AxonInfo],
) -> list[TaskSynapseObject] | None:
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
        return None

    logger.info(
        f"Sending {task_type} request to miners: {[axon.hotkey for axon in axons]}"
    )

    # Send request to miners
    miner_responses = await validator._send_requests_to_miners(
        validator.dendrite,
        axons,
        synapse,
        shuffled=True,
    )

    # Process responses
    valid_miner_responses = []
    for response in miner_responses:
        try:
            if not response.dojo_task_id:
                continue

            # Add minimal required identification for HFL
            response.miner_hotkey = response.axon.hotkey if response.axon else None

            # Get coldkey
            if response.axon and response.axon.hotkey:
                try:
                    hotkey_index = validator.metagraph.hotkeys.index(
                        response.axon.hotkey
                    )
                    response.miner_coldkey = validator.metagraph.coldkeys[hotkey_index]
                except (ValueError, IndexError):
                    response.miner_coldkey = None
            else:
                response.miner_coldkey = None

            valid_miner_responses.append(response)
        except Exception as e:
            logger.error(f"Error processing HFL response: {e}")
            continue

    if not valid_miner_responses:
        logger.info(f"No valid responses received for {task_type} task... skipping")
        return None

    return valid_miner_responses
