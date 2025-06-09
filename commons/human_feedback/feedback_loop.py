"""Main Human Feedback Loop coordinator module."""

import asyncio
import random
import traceback
from typing import TYPE_CHECKING, Dict, List, Tuple

from loguru import logger

from commons.dataset.types import MinerFeedback
from commons.exceptions import NoNewExpiredTasksYet
from commons.hfl_helpers import HFLManager
from commons.orm import ORM
from database.prisma import Json
from database.prisma.enums import HFLStatusEnum, TaskTypeEnum
from database.prisma.models import MinerResponse
from database.prisma.types import HFLStateUpdateInput, ValidatorTaskInclude
from dojo.protocol import DendriteQueryResponse, SyntheticTaskSynapse

from .score_feedback import (
    create_score_feedback_task,
    process_score_feedback_task,
    send_hfl_request,
)
from .text_feedback import (
    create_text_feedback_task,
    fetch_miner_feedback_for_task,
    get_task_synapse_for_retry,
    send_text_feedback_to_synthetic_api,
)
from .types import HFLConstants, HFLInterval
from .utils import evaluate_miner_consensus, get_time_window_for_tasks

if TYPE_CHECKING:
    from neurons.validator import Validator


class FeedbackLoop:
    """
    Human Feedback Loop (HFL) coordinator class that manages the process of:
    1. Selecting completed tasks for feedback
    2. Getting text feedback from miners on responses
    3. Using feedback to generate improved versions via synthetic API
    4. Having miners score the improved versions
    5. Tracking metrics on the process
    """

    async def start_feedback_loop(self, validator: "Validator"):
        """Continuously processes new feedback loop iterations."""
        while True:
            try:
                await asyncio.sleep(HFLInterval.TF_CREATE_INTERVAL)
                logger.info("Starting feedback loop")
                await self._start_feedback_loop(validator)
                logger.info("Feedback loop completed")
            except Exception as e:
                logger.error(f"Error in start_feedback_loop: {e}")
                logger.debug(f"Traceback: {traceback.format_exc()}")
                await asyncio.sleep(HFLInterval.TF_CREATE_INTERVAL)

    async def _start_feedback_loop(self, validator: "Validator"):
        """
        Core implementation of the feedback loop logic.
        Selects a validator task, creates a text criteria task, and sends it to miners.
        """
        active_miner_uids = await validator.get_active_miner_uids(
            subset_size=HFLConstants.TARGET_NUM_MINERS.value
        )
        if len(active_miner_uids) <= HFLConstants.TARGET_NUM_MINERS.value:
            logger.warning(
                f"Not enough active miners found for {TaskTypeEnum.TEXT_FEEDBACK} task... skipping"
            )
            return

        result = await self.select_validator_task()
        if result:
            selected_task, selected_completion_id = result
            text_criteria_task = await create_text_feedback_task(
                selected_task, selected_completion_id
            )
            if not text_criteria_task:
                logger.error(
                    f"Failed to generate text criteria task for task {selected_task.task_id}"
                )
                return

            obfuscated_model_to_model, selected_task.completion_responses = (
                validator.obfuscate_model_names(
                    selected_task.completion_responses or []
                )
            )

            miner_responses = await send_hfl_request(
                synapse=text_criteria_task,
                task_type=TaskTypeEnum.TEXT_FEEDBACK,
                axons=validator._retrieve_axons(active_miner_uids),
            )

            if not miner_responses:
                logger.error(
                    f"Failed to send HFL request for task {text_criteria_task.task_id}"
                )
                return

            # deobfuscate model names
            text_criteria_task.completion_responses = validator.deobfuscate_model_names(
                text_criteria_task.completion_responses or [],
                obfuscated_model_to_model,
            )

            validator_task, hfl_state = await ORM.save_tf_task(
                validator_task=text_criteria_task,
                miner_responses=miner_responses,
                previous_task_id=selected_task.task_id,
                selected_completion_id=selected_completion_id,
            )

            if not validator_task:
                logger.error(
                    f"Failed to save text criteria task for task {text_criteria_task.task_id}"
                )
                return

            logger.info(
                f"Started HFL with state ID: {hfl_state.id}, original task: {selected_task.task_id}, TF task: {validator_task.id}"
            )

    async def select_validator_task(self) -> Tuple[SyntheticTaskSynapse, str] | None:
        """
        Selects a validator task from the latest expired tasks within a specific time window.
        Time window:
          - expire_from: current time minus 2 hours
          - expire_to: current time minus 1 hour
        Reason for using this time window:We want to select a task that has expired and been scored
        The task is only selected if there exists at least one completion where >50% and <90%
        of the miners scored it the highest.

        Returns:
            Tuple[SyntheticTaskSynapse, str] | None: A tuple of (validator task, completion_id) if criteria are met;
        """
        expire_from, expire_to = get_time_window_for_tasks(
            hours_ago_start=1, hours_ago_end=0
        )

        eligible_tasks = []
        try:
            async for tasks_batch, _ in ORM.get_expired_tasks(
                batch_size=10,
                expire_from=expire_from,
                expire_to=expire_to,
                is_processed=True,
                has_previous_task=False,
                has_next_task=False,
                task_types=[TaskTypeEnum.CODE_GENERATION],
            ):
                for dendrite_response in tasks_batch:
                    eligible_task = await self._evaluate_task(dendrite_response)
                    if eligible_task:
                        eligible_tasks.append(eligible_task)
        except NoNewExpiredTasksYet as e:
            logger.info(f"No expired CODE_GENERATION tasks found for processing: {e}")
            return None
        except Exception as e:
            logger.error(f"Error retrieving expired tasks: {e}")
            return None

        if not eligible_tasks:
            logger.info("No tasks meeting criteria found.")
            return None

        selected_task, selected_completion = random.choice(eligible_tasks)
        logger.info(
            f"Selected validator task with ID: {selected_task.task_id} and completion ID: {selected_completion}"
        )
        return selected_task, selected_completion

    async def _evaluate_task(
        self, dendrite_response: DendriteQueryResponse
    ) -> Tuple[SyntheticTaskSynapse, str] | None:
        """
        Evaluates a single task based on its miner scores from the MinerScore table.
        For each completion in the task, computes what percentage of miners scored it
        highest based on raw_score. If any completion has >50% and <90% of miners
        scoring it the highest, then the task qualifies.

        Args:
            dendrite_response (DendriteQueryResponse): Contains the validator task and related miner responses.

        Returns:
            Optional[Tuple[SyntheticTaskSynapse, str]]: Tuple of (validator task, completion_id) if criteria are met;
            otherwise None.
        """
        validator_task: SyntheticTaskSynapse = dendrite_response.validator_task

        if not validator_task.task_id:
            logger.debug("Task ID is missing")
            return None

        try:
            hfl_state = await HFLManager.get_state_by_original_task_id(
                validator_task.task_id
            )
            if hfl_state:
                logger.debug(
                    f"HFL state found for task {validator_task.task_id}, means we already processed this task, skipping"
                )
                return None

            # TODO: turn back to 90 on mainnet
            _, eligible_completion, _ = await evaluate_miner_consensus(
                task_id=validator_task.task_id,
                min_threshold=HFLConstants.MIN_THRESHOLD.value,
                max_threshold=HFLConstants.MAX_THRESHOLD.value,
            )

            if eligible_completion:
                return validator_task, eligible_completion

            return None

        except Exception as e:
            logger.error(f"Error evaluating task {validator_task.task_id}: {e}")
            return None

    async def update_tf_task_results(self, validator: "Validator"):
        """
        Continuously monitors and processes TEXT_FEEDBACK tasks.
        """
        while True:
            try:
                await asyncio.sleep(HFLInterval.TF_UPDATE_INTERVAL)
                selected_responses_by_task = await self._update_tf_task_results(
                    validator
                )
                for task_id, responses in selected_responses_by_task.items():
                    miner_info = [
                        (r.hotkey, r.id)
                        for r in responses
                        if hasattr(r, "hotkey") and hasattr(r, "id")
                    ]
                    logger.info(f"Task {task_id}: Selected miners {miner_info}")
            except Exception as e:
                logger.error(f"Error in update_text_feedback_results: {e}")
                logger.debug(f"Traceback: {traceback.format_exc()}")
                await asyncio.sleep(HFLInterval.TF_UPDATE_INTERVAL)

    async def _update_tf_task_results(
        self, validator: "Validator"
    ) -> Dict[str, List[MinerResponse]]:
        """
        Optimized implementation for processing TEXT_FEEDBACK tasks that efficiently
        fetches miner responses and processes them for HFL workflow.

        Args:
            validator: The Validator instance for network access

        Returns:
            Dictionary mapping task IDs to selected miner responses
        """
        if not validator._active_miner_uids:
            logger.warning(
                f"No active miners found for {TaskTypeEnum.TEXT_FEEDBACK} task... skipping"
            )
            return {}

        # Dictionary to store selected responses by task ID
        selected_responses_by_task = {}

        try:
            logger.info("Updating text feedback task results...")

            # Set time window for expired tasks
            expire_from, expire_to = get_time_window_for_tasks(
                hours_ago_start=2, hours_ago_end=0, buffer_minutes=10
            )

            # Process TF_PENDING tasks in batches
            async for tf_tasks_batch, _ in ORM.get_tasks_by_hfl_status(
                status=HFLStatusEnum.TF_PENDING,
                task_type=TaskTypeEnum.TEXT_FEEDBACK,
                expire_from=expire_from,
                expire_to=expire_to,
                batch_size=10,
                include_options=ValidatorTaskInclude(
                    {"HFLState": True, "miner_responses": True}
                ),
            ):
                if not tf_tasks_batch:
                    continue

                sufficient_response_task_ids: list[str] = []

                # Process each task in the batch
                for task in tf_tasks_batch:
                    hotkeys_with_feedback: list[str] = []

                    # Fetch and process miner feedback
                    (
                        miner_feedbacks,
                        valid_responses,
                    ) = await fetch_miner_feedback_for_task(validator, task)

                    hotkeys_with_feedback.extend(
                        [miner_feedback.hotkey for miner_feedback in miner_feedbacks]
                    )

                    # Check if we have sufficient responses
                    response_count = len(miner_feedbacks)

                    # Verify HFL state exists
                    if not task.HFLState:
                        logger.error(
                            f"No HFLState found for task {task.id} which should not happen"
                        )
                        continue

                    # Get retry count from HFL state
                    retry_count = task.HFLState.tf_retry_count or 0

                    # NOTE: Process task with sufficient responses
                    if response_count >= HFLConstants.TF_MIN_RESPONSES.value:
                        logger.info(
                            f"Task {task.id} has {response_count} valid responses, processing"
                        )
                        sufficient_response_task_ids.append(task.id)

                        # Create a list of tuples (feedback, response) to keep them paired
                        feedback_response_pairs: list[
                            tuple[MinerFeedback, MinerResponse]
                        ] = list(zip(miner_feedbacks, valid_responses))

                        # Select 3 random responses
                        selected_pairs: list[tuple[MinerFeedback, MinerResponse]] = (
                            random.sample(
                                feedback_response_pairs, min(3, response_count)
                            )
                        )

                        # Unzip the pairs when needed
                        selected_feedbacks, selected_responses = (
                            zip(*selected_pairs) if selected_pairs else ([], [])
                        )

                        # Send to synthetic API
                        await send_text_feedback_to_synthetic_api(
                            validator_task_id=task.id,
                            hfl_state=task.HFLState,
                            miner_feedback=selected_feedbacks,
                        )

                        # Store selected responses
                        selected_responses_by_task[task.id] = selected_responses

                    # NOTE: Process task with insufficient responses needing retry
                    elif (
                        response_count < HFLConstants.TF_MIN_RESPONSES.value
                        and retry_count < HFLConstants.TF_MAX_RETRY.value
                    ):
                        task_synapse = await get_task_synapse_for_retry(task.id)

                        if not task_synapse:
                            logger.warning(f"Task {task.id} not found, skipping")
                            continue

                        if not task_synapse.completion_responses:
                            logger.warning(
                                f"Task {task.id} has no completion responses, skipping"
                            )
                            continue

                        obfuscated_model_to_model, task_synapse.completion_responses = (
                            validator.obfuscate_model_names(
                                task_synapse.completion_responses
                            )
                        )

                        active_miner_uids = await validator.get_active_miner_uids()
                        axons = validator._retrieve_axons(active_miner_uids)
                        # filter hotkey that have already been give feedback
                        axons = [
                            axon
                            for axon in axons
                            if axon.hotkey not in hotkeys_with_feedback
                        ]
                        if len(axons) < HFLConstants.MIN_NUM_MINERS.value:
                            continue

                        miner_responses = await send_hfl_request(
                            synapse=task_synapse,
                            task_type=TaskTypeEnum.TEXT_FEEDBACK,
                            axons=axons,
                        )
                        if not miner_responses:
                            logger.warning(
                                f"No miner responses found for task {task.id}"
                            )
                            continue

                        # deobfuscate model names
                        for response in miner_responses:
                            if response.completion_responses:
                                for completion in response.completion_responses:
                                    completion.model = obfuscated_model_to_model.get(
                                        completion.model, completion.model
                                    )

                        count, updated_hfl_state = await ORM.save_tf_retry_responses(
                            validator_task_id=task.id,
                            hfl_state=task.HFLState,
                            miner_responses=miner_responses,
                        )

                        logger.info(
                            f"Saved {count} miner responses for task {task.id}, retry count: {updated_hfl_state.tf_retry_count}"
                        )

                    # NOTE: We still have insufficient responses < 3 but we have reached max retries
                    elif (
                        response_count < HFLConstants.TF_MIN_RESPONSES.value
                        and retry_count >= HFLConstants.TF_MAX_RETRY.value
                    ):
                        # Handle task with insufficient responses at max retries
                        logger.warning(
                            f"Task {task.id} failed to get enough responses after {HFLConstants.TF_MAX_RETRY.value} attempts. "
                            f"Using available {response_count} responses."
                        )
                        # Cover edge case where we have no responses after max retries
                        if response_count == 0:
                            logger.warning(
                                f"Task {task.id} has no responses after {HFLConstants.TF_MAX_RETRY.value} attempts, ending HFL"
                            )
                            await HFLManager.update_state(
                                hfl_state_id=task.HFLState.id,
                                updates=HFLStateUpdateInput(
                                    status=HFLStatusEnum.TF_FAILED
                                ),
                            )
                            await ORM.mark_validator_task_as_processed([task.id])

                            continue

                        else:
                            # Use all available responses (up to 3)
                            available_feedbacks = miner_feedbacks[
                                : min(3, response_count)
                            ]
                            available_responses = valid_responses[
                                : min(3, response_count)
                            ]

                            # Process with available responses
                            await send_text_feedback_to_synthetic_api(
                                validator_task_id=task.id,
                                hfl_state=task.HFLState,
                                miner_feedback=available_feedbacks,
                            )

                            # Mark as processed and store responses
                            sufficient_response_task_ids.append(task.id)
                            selected_responses_by_task[task.id] = available_responses

                # Mark tasks with sufficient responses as processed
                if sufficient_response_task_ids:
                    await ORM.mark_validator_task_as_processed(
                        sufficient_response_task_ids
                    )

            return selected_responses_by_task

        except Exception as e:
            logger.error(f"Error during text feedback task monitoring: {str(e)}")
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return {}

    async def create_sf_tasks(self, validator: "Validator"):
        """Continuously poll for completed text feedback tasks and process synthetic improvements."""
        while True:
            try:
                await asyncio.sleep(HFLInterval.SF_CREATE_INTERVAL)
                await self._create_sf_tasks(validator)
            except Exception as e:
                logger.error(f"Error in create_sf_tasks: {str(e)}")
                logger.debug(f"Traceback: {traceback.format_exc()}")
                await asyncio.sleep(HFLInterval.SF_CREATE_INTERVAL)

    async def _create_sf_tasks(self, validator: "Validator"):
        """
        Poll for completed text feedback tasks and process synthetic improvements.
        Runs continuously with HFL_SF_CREATE_INTERVAL delay between iterations.

        Flow:
        1. Query TF_COMPLETED states in batches
        2. For each batch:
            - Check synthetic task status
            - If ready, create improved task and send to miners
            - Update state to SF_PENDING
        """
        try:
            if not validator._active_miner_uids:
                logger.warning(
                    f"No active miners found for {TaskTypeEnum.SCORE_FEEDBACK} task... skipping"
                )
                return

            # Get tasks with TF_COMPLETED status in batches
            async for tf_tasks_batch, _ in ORM.get_TF_tasks_by_hfl_status(
                status=HFLStatusEnum.TF_COMPLETED,
                batch_size=10,
            ):
                if not tf_tasks_batch:
                    continue

                for tf_task in tf_tasks_batch:
                    if (
                        not tf_task.HFLState
                        or not tf_task.HFLState.current_synthetic_req_id
                    ):
                        logger.debug(
                            f"No HFLState or current_synthetic_req_id for task-id: {tf_task.id}"
                        )
                        continue

                    # Create SF task for miners
                    validator_task = await create_score_feedback_task(
                        validator=validator,
                        tf_task=tf_task,
                        hfl_state=tf_task.HFLState,
                    )

                    if not validator_task:
                        logger.error(f"Failed to create SF task for {tf_task.id}")
                        continue

                    logger.info(
                        f"Created SF task with validator task: {validator_task.id} for {tf_task.id}"
                    )

        except Exception as e:
            logger.error(f"Error in creating SF tasks: {str(e)}")
            logger.debug(f"Traceback: {traceback.format_exc()}")

    async def update_sf_task_results(self, validator: "Validator"):
        """
        Update the results of Score Feedback (SF) tasks.
        """
        while True:
            try:
                await asyncio.sleep(HFLInterval.SF_UPDATE_INTERVAL)
                logger.info("Updating SF task results")
                await self._update_sf_task_results(validator)
                logger.info("Updating SF task results completed")
            except Exception as e:
                logger.error(f"Error in update_sf_task_results: {str(e)}")
                logger.debug(f"Traceback: {traceback.format_exc()}")
                await asyncio.sleep(HFLInterval.SF_UPDATE_INTERVAL)

    async def _update_sf_task_results(self, validator: "Validator"):
        """
        Update the results of Score Feedback (SF) tasks.

        Flow:
        1. Query SF_PENDING tasks that have expired within a time window
        2. For each task:
            - Get all miner responses
            - Query each miner for task results using validator task id
            - Update task results in database
            - Update HFL state to SF_COMPLETED
        """
        try:
            # Get tasks that expired in the last 2 hours
            expire_from, expire_to = get_time_window_for_tasks(
                hours_ago_start=2, hours_ago_end=0
            )

            logger.debug(
                f"Processing SF tasks with expire_from: {expire_from} and expire_to: {expire_to}"
            )

            # Get SF_PENDING tasks in batches
            async for sf_tasks_batch, _ in ORM.get_tasks_by_hfl_status(
                status=HFLStatusEnum.SF_PENDING,
                task_type=TaskTypeEnum.SCORE_FEEDBACK,
                expire_from=expire_from,
                expire_to=expire_to,
                batch_size=10,
                include_options=ValidatorTaskInclude(
                    {
                        "HFLState": True,
                        "miner_responses": {
                            "where": {"task_result": {"equals": Json("[]")}}
                        },
                    }
                ),
            ):
                if not sf_tasks_batch:
                    continue

                for sf_task in sf_tasks_batch:
                    if not sf_task.HFLState:
                        logger.debug(
                            f"No HFLState for task {sf_task.id} which should not happen"
                        )
                        continue

                    # Process the SF task
                    success = await process_score_feedback_task(
                        validator=validator,
                        sf_task=sf_task,
                        hfl_state=sf_task.HFLState,
                    )

                    if success:
                        logger.success(f"Successfully processed SF task {sf_task.id}")
                    else:
                        logger.error(f"Failed to process SF task {sf_task.id}")

        except Exception as e:
            logger.error(f"Error in SF task processing loop: {str(e)}")
            logger.debug(f"Traceback: {traceback.format_exc()}")

    async def create_next_tf_tasks(self, validator: "Validator"):
        """Continuously poll for HFL states that should continue to the next iteration."""
        while True:
            try:
                await asyncio.sleep(HFLInterval.NEXT_TF_INTERVAL)
                logger.info("Creating next TF tasks")
                await self._create_next_tf_tasks(validator)
                logger.info("Next TF tasks creation completed")
            except Exception as e:
                logger.error(f"Error in create_next_tf_tasks: {str(e)}")
                logger.debug(f"Traceback: {traceback.format_exc()}")
                await asyncio.sleep(HFLInterval.NEXT_TF_INTERVAL)

    async def _create_next_tf_tasks(self, validator: "Validator"):
        """
        Poll for tasks with HFL states in TF_SCHEDULED status and create the next text feedback task.

        Flow:
        1. Query tasks with TF_SCHEDULED HFL states
        2. For each task:
            - Map the SF task to a SyntheticTaskSynapse
            - Create the next TF task based on the best completion
            - Update HFL state to TF_PENDING
        """
        try:
            if not validator._active_miner_uids:
                logger.warning(
                    f"No active miners found for {TaskTypeEnum.TEXT_FEEDBACK} task... skipping"
                )
                return

            # Get tasks with TF_SCHEDULED status in batches
            async for scheduled_tasks_batch, _ in ORM.get_tasks_by_hfl_status(
                status=HFLStatusEnum.TF_SCHEDULED,
                task_type=TaskTypeEnum.SCORE_FEEDBACK,
                batch_size=10,
                include_options=ValidatorTaskInclude(
                    {"HFLState": True, "completions": True}
                ),
            ):
                if not scheduled_tasks_batch:
                    continue

                for sf_task in scheduled_tasks_batch:
                    if not sf_task.HFLState:
                        logger.error(f"No HFL state found for task {sf_task.id}")
                        continue

                    hfl_state = sf_task.HFLState

                    # Find the best completion from the SF task using evaluate_miner_consensus
                    completion_percentages, _, _ = await evaluate_miner_consensus(
                        task_id=sf_task.id,
                    )

                    if not completion_percentages:
                        logger.error(
                            f"No completion percentages found for SF task {sf_task.id}"
                        )
                        continue

                    # Get the completion with the highest consensus
                    best_completion_id = (
                        max(completion_percentages.items(), key=lambda x: x[1])[0]
                        if completion_percentages
                        else None
                    )

                    if not best_completion_id:
                        logger.error(
                            f"No best completion found for SF task {sf_task.id}"
                        )
                        continue

                    # Directly map the sf_task to a SyntheticTaskSynapse
                    from database.mappers import (
                        map_validator_task_to_task_synapse_object,
                    )

                    improved_task = map_validator_task_to_task_synapse_object(sf_task)
                    if not improved_task:
                        logger.error(
                            f"Failed to map task {sf_task.id} to SyntheticTaskSynapse"
                        )
                        continue

                    # Create a text feedback task for the best completion
                    text_criteria_task = await create_text_feedback_task(
                        improved_task, best_completion_id
                    )

                    if not text_criteria_task:
                        logger.error(
                            f"Failed to generate text criteria task for task {improved_task.task_id}"
                        )
                        continue

                    # Get active miners for the new TF task
                    active_miners = await validator.get_active_miner_uids(
                        subset_size=HFLConstants.TARGET_NUM_MINERS.value
                    )
                    if len(active_miners) <= HFLConstants.TARGET_NUM_MINERS.value:
                        logger.warning(
                            f"Not enough active miners found for {TaskTypeEnum.TEXT_FEEDBACK} task... skipping"
                        )
                        continue

                    # Send the task to miners
                    miner_responses = await send_hfl_request(
                        synapse=text_criteria_task,
                        task_type=TaskTypeEnum.TEXT_FEEDBACK,
                        axons=validator._retrieve_axons(active_miners),
                    )

                    if not miner_responses:
                        logger.error(
                            f"Failed to send HFL request for task {text_criteria_task.task_id}"
                        )
                        continue

                    # Save the new TF task and update the HFL state
                    validator_task, updated_hfl_state = await ORM.save_tf_task(
                        validator_task=text_criteria_task,
                        miner_responses=miner_responses,
                        previous_task_id=sf_task.id,
                        selected_completion_id=best_completion_id,
                        is_next_task=True,
                    )

                    if not validator_task:
                        logger.error(
                            f"Failed to save text criteria task for task {text_criteria_task.task_id}"
                        )
                        continue

                    logger.info(
                        f"Created next TF task {validator_task.id} for iteration {updated_hfl_state.current_iteration} "
                        f"of HFL process {hfl_state.id}"
                    )

        except Exception as e:
            logger.error(f"Error creating next TF tasks: {str(e)}")
            logger.debug(f"Traceback: {traceback.format_exc()}")
