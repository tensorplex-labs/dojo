import asyncio
import json
import random
import traceback
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

import aiohttp
from bittensor.core.chain_data.axon_info import AxonInfo
from bittensor.utils.btlogging import logging as logger
from tenacity import RetryError

import dojo
from commons.dataset.synthetic import SyntheticAPI
from commons.exceptions import NoNewExpiredTasksYet
from commons.hfl_heplers import HFLManager
from commons.orm import ORM
from commons.utils import datetime_as_utc, get_new_uuid, set_expire_time
from database.mappers import map_validator_task_to_task_synapse_object
from database.prisma import Json
from database.prisma.enums import HFLStatusEnum, TaskTypeEnum
from database.prisma.models import HFLState, MinerResponse, MinerScore, ValidatorTask
from database.prisma.types import MinerScoreWhereInput, ValidatorTaskInclude
from dojo.protocol import (
    CriteriaType,
    DendriteQueryResponse,
    MinerFeedback,
    ScoreCriteria,
    ScoreFeedbackEvent,
    SyntheticQA,
    TaskResult,
    TaskSynapseObject,
    TextCriteria,
    TextFeedbackEvent,
    TextFeedbackRequest,
)
from neurons.validator import Validator


class FeedbackLoop:
    async def start_feedback_loop(self, validator: Validator):
        """Continuously processes new feedback loop iterations."""
        while True:
            try:
                await asyncio.sleep(dojo.VALIDATOR_UPDATE_SCORE)
                await self._start_feedback_loop(validator)
            except Exception as e:
                logger.error(f"Error in start_feedback_loop: {e}")
                await asyncio.sleep(dojo.VALIDATOR_UPDATE_SCORE)

    async def _start_feedback_loop(self, validator: Validator):
        """
        Core implementation of the feedback loop logic.
        Selects a validator task, creates a text criteria task, and sends it to miners.
        """

        active_miners = await self._get_active_miners_for_hfl(
            validator=validator,
            subset_size=7,
        )
        if not active_miners:
            logger.warning(
                f"No active miners found for {TaskTypeEnum.TEXT_FEEDBACK} task... skipping"
            )
            return

        result = await self.select_validator_task()
        if result:
            selected_task, selected_completion = result
            text_criteria_task = await self.generate_text_criteria_task(
                selected_task, selected_completion
            )
            if not text_criteria_task:
                logger.error(
                    f"Failed to generate text criteria task for task {selected_task.task_id}"
                )
                return

            miner_responses = await self.send_hfl_request(
                validator=validator,
                synapse=text_criteria_task,
                task_type=TaskTypeEnum.TEXT_FEEDBACK,
                axons=[
                    validator.metagraph.axons[axon_uid] for axon_uid in active_miners
                ],
            )

            if not miner_responses:
                logger.error(
                    f"Failed to send HFL request for task {text_criteria_task.task_id}"
                )
                return

            validator_task, hfl_state = await ORM.save_tf_task(
                validator_task=text_criteria_task,
                miner_responses=miner_responses,
                previous_task_id=selected_task.task_id,
                original_task_id=selected_task.task_id,
                selected_completion_id=selected_completion,
            )

            if not validator_task:
                logger.error(
                    f"Failed to save text criteria task for task {text_criteria_task.task_id}"
                )
                return

            logger.info(
                f"Started HFL with state ID: {hfl_state.id}, original task: {selected_task.task_id}, TF task: {validator_task.id}"
            )

    async def select_validator_task(self) -> Tuple[TaskSynapseObject, str] | None:
        """
        Selects a validator task from the latest expired tasks within a specific time window.
        Time window:
          - expire_from: current time minus 2 hours
          - expire_to: current time minus 1 hour
        Reason for using this time window:We want to select a task that has expired and been scored
        The task is only selected if there exists at least one completion where >50% and <90%
        of the miners scored it the highest.

        Returns:
            Tuple[TaskSynapseObject, str] | None: A tuple of (validator task, completion_id) if criteria are met;
        """
        expire_from = datetime_as_utc(datetime.now(timezone.utc)) - timedelta(hours=48)
        # TODO: Change back to 1 hour
        expire_to = datetime_as_utc(datetime.now(timezone.utc))

        eligible_tasks = []
        try:
            async for tasks_batch, _ in ORM.get_expired_tasks(
                batch_size=10,
                expire_from=expire_from,
                expire_to=expire_to,
                is_processed=True,
                has_previous_task=False,
                task_type=TaskTypeEnum.CODE_GENERATION,
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
    ) -> Tuple[TaskSynapseObject, str] | None:
        """
        Evaluates a single task based on its miner scores from the MinerScore table.
        For each completion in the task, computes what percentage of miners scored it
        highest based on raw_score. If any completion has >50% and <90% of miners
        scoring it the highest, then the task qualifies.

        Args:
            dendrite_response (DendriteQueryResponse): Contains the validator task and related miner responses.

        Returns:
            Optional[Tuple[TaskSynapseObject, str]]: Tuple of (validator task, completion_id) if criteria are met;
            otherwise None.
        """
        validator_task: TaskSynapseObject = dendrite_response.validator_task

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
            # Get all miner scores for this validator task
            miner_scores = await MinerScore.prisma().find_many(
                where=MinerScoreWhereInput(
                    {
                        "miner_response_relation": {
                            "is": {"validator_task_id": validator_task.task_id}
                        }
                    }
                ),
                include={
                    "criterion_relation": {"include": {"completion_relation": True}},
                    "miner_response_relation": True,
                },
            )

            if not miner_scores:
                logger.debug(f"No miner scores found for task {validator_task.task_id}")
                return None

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

                completion_id = (
                    score.criterion_relation.completion_relation.completion_id
                )
                miner_response_id = score.miner_response_id

                # Store score for this completion
                if completion_id not in completion_scores:
                    completion_scores[completion_id] = []
                completion_scores[completion_id].append(
                    (miner_response_id, miner_raw_score)
                )

            logger.info(f"Completion scores: {completion_scores}")
            # Find highest scored completion for each miner
            for completion_id, scores in completion_scores.items():
                for miner_response_id, score in scores:
                    current_best = miner_best_completions.get(miner_response_id)
                    if (
                        current_best is None
                        or score > completion_scores[current_best][0][1]
                    ):
                        miner_best_completions[miner_response_id] = completion_id

            total_miners = len(set(miner_best_completions.keys()))
            if total_miners == 0:
                return None

            logger.info(f"Miner best completions: {miner_best_completions}")
            # Count how many miners scored each completion as best
            completion_counts = {}
            for best_completion in miner_best_completions.values():
                completion_counts[best_completion] = (
                    completion_counts.get(best_completion, 0) + 1
                )

            # Check percentages for each completion

            for completion_id, count in completion_counts.items():
                percentage = (count / total_miners) * 100
                # TODO: Change back to < 90
                if 50 < percentage < 101:
                    logger.info(
                        f"Found eligible completion {completion_id} with {percentage:.1f}% "
                        f"of miners ({count}/{total_miners}) scoring it highest"
                    )
                    return validator_task, completion_id

            return None

        except Exception as e:
            logger.error(f"Error evaluating task {validator_task.task_id}: {e}")
            return None

    async def generate_text_criteria_task(
        self, validator_task: TaskSynapseObject, completion_id: str
    ) -> TaskSynapseObject | None:
        """
        Generates a text criteria task based on a selected validator task and completion.
        This task will be used to evaluate the quality of miners' scoring.

        Args:
            validator_task (TaskSynapseObject): The original validator task
            completion_id (str): ID of the selected completion to be evaluated

        Returns:
            TaskSynapseObject | None: A new task for text-based evaluation, or None if generation fails
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
                expire_at=set_expire_time(
                    int(dojo.TASK_DEADLINE / 2)
                ),  # Half the deadline for TF
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

    async def update_tf_task_results(self, validator: Validator):
        """
        Continuously monitors and processes TEXT_FEEDBACK tasks.
        """
        while True:
            try:
                await asyncio.sleep(dojo.VALIDATOR_UPDATE_SCORE)
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
                await asyncio.sleep(dojo.VALIDATOR_UPDATE_SCORE)

    async def _update_tf_task_results(
        self, validator: Validator
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
            expire_from = datetime_as_utc(datetime.now(timezone.utc)) - timedelta(
                hours=2
            )
            expire_to = datetime_as_utc(datetime.now(timezone.utc))

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
                    ) = await self._fetch_miner_feedback_for_task(validator, task)

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
                    MAX_RETRY_ATTEMPTS = 5

                    if response_count >= 3:
                        # Process task with sufficient responses
                        logger.info(
                            f"Task {task.id} has {response_count} valid responses, processing"
                        )
                        sufficient_response_task_ids.append(task.id)

                        # Create a list of tuples (feedback, response) to keep them paired
                        feedback_response_pairs = list(
                            zip(miner_feedbacks, valid_responses)
                        )

                        # Select 3 random responses
                        selected_pairs = random.sample(
                            feedback_response_pairs, min(3, response_count)
                        )

                        # Unzip the pairs when needed
                        selected_feedbacks, selected_responses = (
                            zip(*selected_pairs) if selected_pairs else ([], [])
                        )

                        # Send to synthetic API
                        await self._send_text_feedback_to_synthetic_api(
                            validator_task_id=task.id,
                            hfl_state=task.HFLState,
                            miner_feedback=selected_feedbacks,
                        )

                        # Store selected responses
                        selected_responses_by_task[task.id] = selected_responses

                    elif retry_count < MAX_RETRY_ATTEMPTS:
                        # Handle task with insufficient responses needing retry

                        task_synapse = await self._get_task_synapse_for_retry(task.id)
                        if not task_synapse:
                            logger.warning(f"Task {task.id} not found, skipping")
                            continue

                        active_miners = await self._get_active_miners_for_hfl(
                            validator, 7
                        )

                        if not active_miners:
                            logger.warning(
                                f"No active miners found for {TaskTypeEnum.TEXT_FEEDBACK} task... skipping"
                            )
                            continue

                        # filter hotkey that have already been give feedback
                        axons = [
                            validator.metagraph.axons[uid]
                            for uid in active_miners
                            if validator.metagraph.axons[uid].hotkey
                            not in hotkeys_with_feedback
                        ]

                        miner_responses = await self.send_hfl_request(
                            validator=validator,
                            synapse=task_synapse,
                            task_type=TaskTypeEnum.TEXT_FEEDBACK,
                            axons=axons,
                        )
                        if not miner_responses:
                            logger.warning(
                                f"No miner responses found for task {task.id}"
                            )
                            continue

                        count, updated_hfl_state = await ORM.save_tf_retry_responses(
                            validator_task_id=task.id,
                            hfl_state=task.HFLState,
                            miner_responses=miner_responses,
                        )

                        logger.info(
                            f"Saved {count} miner responses for task {task.id}, retry count: {updated_hfl_state.tf_retry_count}"
                        )

                    else:
                        # Handle task with insufficient responses at max retries
                        logger.warning(
                            f"Task {task.id} failed to get enough responses after {MAX_RETRY_ATTEMPTS} attempts. "
                            f"Using available {response_count} responses."
                        )

                        if response_count > 0:
                            # Use all available responses (up to 3)
                            available_feedbacks = miner_feedbacks[
                                : min(3, response_count)
                            ]
                            available_responses = valid_responses[
                                : min(3, response_count)
                            ]

                            # Process with available responses
                            await self._send_text_feedback_to_synthetic_api(
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

    async def _fetch_miner_feedback_for_task(
        self, validator: Validator, task: ValidatorTask
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
        miner_feedbacks: list[MinerFeedback] = []
        valid_responses: list[MinerResponse] = []
        responses_needing_fetch: list[MinerResponse] = []

        # Identify valid miner responses
        valid_miner_responses = [
            resp
            for resp in task.miner_responses or []
            if resp.hotkey and resp.dojo_task_id
        ]

        if not valid_miner_responses:
            logger.warning(f"No valid miner responses found for task {task.id}")
            return [], []

        # Process all responses in a single pass
        for resp in valid_miner_responses:
            # Extract feedback text directly from the task_result
            feedback_text = self._extract_text_feedback_from_results(resp.task_result)
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
                responses_needing_fetch.append(resp)

        if not responses_needing_fetch:
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

        # Process results and update the database
        for i, result in enumerate(task_results_list):
            if isinstance(result, BaseException):
                logger.warning(
                    f"Error fetching results for miner {responses_needing_fetch[i].hotkey}: {result}"
                )
                continue

            if not result:  # Empty or None result
                continue

            miner_response = responses_needing_fetch[i]

            # Update the database with fresh results
            success = await ORM.update_miner_task_results(
                miner_hotkey=miner_response.hotkey,
                dojo_task_id=miner_response.dojo_task_id,
                task_results=result,
            )

            if success:
                # Extract text feedback
                feedback_text = self._extract_text_feedback_from_results(result)
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

    def _extract_text_feedback_from_results(
        self, task_results: list[TaskResult] | Json
    ) -> str:
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
                        if criterion.get("type") == "text"
                        and "text_feedback" in criterion
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
                    if not isinstance(result_data, dict) or not result_data.get(
                        "criteria"
                    ):
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

    async def _get_task_synapse_for_retry(
        self, task_id: str
    ) -> TaskSynapseObject | None:
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
            task_synapse = map_validator_task_to_task_synapse_object(task)
            task_synapse.expire_at = set_expire_time(int(dojo.TASK_DEADLINE / 2))
            if task_synapse.completion_responses:
                for completion in task_synapse.completion_responses:
                    if (
                        not completion.criteria_types
                        or len(completion.criteria_types) == 0
                    ):
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

    async def _send_text_feedback_to_synthetic_api(
        self,
        validator_task_id: str,
        hfl_state: HFLState,
        miner_feedback: list[MinerFeedback],
    ) -> str | None:
        """
        Process text feedback and send to the Synthetic API for improvement.

        Args:
            validator_task_id: ID of the current validator task
            original_task_id: ID of the original task
            miner_feedback: List of miner feedback to send

        Returns:
            Synthetic request ID if successful, None otherwise
        """
        try:
            if not miner_feedback:
                logger.warning(
                    f"No miner feedback provided for task {validator_task_id}"
                )
                return None

            # Get original task
            original_task = await ORM.get_validator_task_by_id(
                hfl_state.original_task_id
            )

            if not original_task or not original_task.completions:
                logger.warning(
                    f"Could not find original task or completions for {hfl_state.original_task_id}"
                )
                return None

            # Get the completion from the original task
            base_completion = original_task.completions[0].completion

            # Create the TextFeedbackRequest object
            text_feedback_request = TextFeedbackRequest(
                validator_task_id=validator_task_id,
                base_prompt=original_task.prompt,
                base_completion=base_completion,
                miner_feedbacks=miner_feedback,
            )

            # Send to synthetic API
            logger.info(
                f"Sending {len(miner_feedback)} feedback responses to synthetic API"
            )
            syn_req_id = await SyntheticAPI.send_text_feedback(text_feedback_request)

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
                    timestamp=datetime_as_utc(datetime.now(timezone.utc)),
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

    async def create_sf_tasks(self, validator: Validator):
        """
        Poll for completed text feedback tasks and process synthetic improvements.
        Runs continuously with SF_TASK_CREATION_INTERVAL delay between iterations.

        Flow:
        1. Query TF_COMPLETED states in batches
        2. For each batch:
            - Check synthetic task status
            - If ready, create improved task and send to miners
            - Update state to SF_PENDING
        """
        while True:
            try:
                # Get tasks with TF_COMPLETED status in batches
                async for tf_tasks_batch, _ in ORM.get_TF_tasks_by_hfl_status(
                    status=HFLStatusEnum.TF_COMPLETED,
                    batch_size=10,
                ):
                    if not tf_tasks_batch:
                        await asyncio.sleep(dojo.SF_TASK_CREATION_INTERVAL)
                        continue

                    for tf_task in tf_tasks_batch:
                        try:
                            if (
                                not tf_task.HFLState
                                or not tf_task.HFLState.current_synthetic_req_id
                            ):
                                logger.debug(
                                    f"No HFLState or current_synthetic_req_id for task-id: {tf_task.id}"
                                )
                                continue

                            # Check if synthetic task is ready
                            improved_task = (
                                await self._generate_improved_synthetic_request(
                                    tf_task.HFLState.current_synthetic_req_id
                                )
                            )
                            if not improved_task:
                                logger.debug(
                                    f"No improved task found for {tf_task.HFLState.current_synthetic_req_id} yet"
                                )
                                continue

                            # Create new task for miners
                            new_task = TaskSynapseObject(
                                task_id=get_new_uuid(),
                                prompt=improved_task.prompt,
                                task_type=TaskTypeEnum.SCORE_FEEDBACK,
                                expire_at=set_expire_time(dojo.TASK_DEADLINE),
                                completion_responses=improved_task.completion_responses,
                            )

                            # Send to miners and get responses
                            sf_task = await validator.send_request(
                                synapse=new_task,
                                synthetic_task=True,
                                prev_task_id=tf_task.id,
                            )

                            if not sf_task:
                                logger.error(
                                    f"Failed to send improved task to miners for {tf_task.id}"
                                )
                                continue

                            # Update HFL state
                            event = ScoreFeedbackEvent(
                                type=HFLStatusEnum.SF_PENDING,
                                task_id=tf_task.id,
                                syn_req_id=tf_task.HFLState.current_synthetic_req_id,
                                iteration=tf_task.HFLState.current_iteration,
                                timestamp=datetime_as_utc(datetime.now(timezone.utc)),
                            )

                            await HFLManager.update_state(
                                tf_task.HFLState.id,
                                {
                                    "status": HFLStatusEnum.SF_PENDING,
                                    "current_task_id": sf_task.id,
                                    "current_synthetic_req_id": None,  # Clear synthetic req ID
                                },
                                event,
                            )

                        except Exception as e:
                            # Log error but continue processing other tasks
                            logger.error(
                                f"Error processing task {tf_task.id}: {str(e)}"
                            )
                            continue

                    await asyncio.sleep(dojo.SF_TASK_CREATION_INTERVAL)

            except Exception as e:
                logger.error(f"Error in synthetic polling loop: {str(e)}")
                await asyncio.sleep(dojo.SF_TASK_CREATION_INTERVAL)

    async def _generate_improved_synthetic_request(
        self, syn_req_id: str
    ) -> TaskSynapseObject | None:
        """Generate an improved synthetic request"""
        try:
            SF_task: SyntheticQA | None = await SyntheticAPI.get_improved_SF(syn_req_id)

            if not SF_task:
                logger.error(f"No improved task found for {syn_req_id}")
                return None

            # Create criteria for each completion response
            criteria: List[CriteriaType] = [
                ScoreCriteria(
                    min=1.0,
                    max=100.0,
                )
            ]

            # Set criteria for each completion response
            for response in SF_task.responses:
                response.criteria_types = criteria

            synapse = TaskSynapseObject(
                task_id=get_new_uuid(),
                prompt=SF_task.prompt,
                task_type=TaskTypeEnum.CODE_GENERATION,
                expire_at=set_expire_time(dojo.TASK_DEADLINE),
                completion_responses=SF_task.responses,
            )

            return synapse

        except (RetryError, ValueError, aiohttp.ClientError) as e:
            logger.error(f"Error getting improved task for {syn_req_id}: {e}")
            return None

        except Exception as e:
            logger.error(f"Unexpected error during synthetic data generation: {e}")
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return None

    async def update_sf_task_results(self, validator: Validator):
        """
        Update the results of Score Feedback (SF) tasks.

        Flow:
        1. Query SF_PENDING tasks that have expired within a time window
        2. For each task:
            - Get all miner responses
            - Query each miner for task results using their dojo_task_id
            - Update task results in database
            - Update HFL state to SF_COMPLETED
        """
        while True:
            try:
                # Get tasks that expired in the last 2 hours
                expire_from = datetime_as_utc(datetime.now(timezone.utc)) - timedelta(
                    hours=2
                )
                expire_to = datetime_as_utc(datetime.now(timezone.utc))

                logger.debug(
                    f"Processing SF tasks with expire_from: {expire_from} and expire_to: {expire_to}"
                )

                # Get SF_PENDING tasks in batches
                async for sf_tasks_batch, _ in ORM.get_SF_tasks_by_hfl_status(
                    status=HFLStatusEnum.SF_PENDING,
                    expire_from=expire_from,
                    expire_to=expire_to,
                    batch_size=10,
                ):
                    if not sf_tasks_batch:
                        await asyncio.sleep(dojo.SF_TASK_CREATION_INTERVAL)
                        continue

                    for sf_task in sf_tasks_batch:
                        try:
                            if not sf_task.miner_responses:
                                logger.debug(
                                    f"No miner responses for task {sf_task.id}"
                                )
                                continue

                            if not sf_task.HFLState or not sf_task.HFLState.id:
                                logger.debug(
                                    f"No HFLState or HFLState.id for task {sf_task.id}"
                                )
                                continue

                            # Update task results for each miner response
                            for miner_response in sf_task.miner_responses:
                                if (
                                    not miner_response.hotkey
                                    or not miner_response.dojo_task_id
                                ):
                                    logger.debug(
                                        "Missing hotkey or dojo_task_id for miner response"
                                    )
                                    continue

                                # Get task results from miner
                                task_results = (
                                    await validator._get_task_results_from_miner(
                                        miner_hotkey=miner_response.hotkey,
                                        dojo_task_id=miner_response.dojo_task_id,
                                    )
                                )

                                if not task_results:
                                    logger.debug(
                                        f"No task results from miner {miner_response.hotkey}"
                                    )
                                    continue

                                # Update task results in database
                                success = await ORM.update_miner_task_results(
                                    miner_hotkey=miner_response.hotkey,
                                    dojo_task_id=miner_response.dojo_task_id,
                                    task_results=task_results,
                                )

                                if not success:
                                    logger.warning(
                                        f"Failed to update task_result for miner {miner_response.hotkey}"
                                    )

                            # Update HFL state to SF_COMPLETED
                            event = ScoreFeedbackEvent(
                                type=HFLStatusEnum.SF_COMPLETED,
                                task_id=sf_task.id,
                                iteration=sf_task.HFLState.current_iteration,
                                timestamp=datetime_as_utc(datetime.now(timezone.utc)),
                            )

                            await HFLManager.update_state(
                                sf_task.HFLState.id,
                                {
                                    "status": HFLStatusEnum.SF_COMPLETED,
                                },
                                event,
                            )

                            logger.success(
                                f"Successfully processed SF task {sf_task.id}"
                            )

                        except Exception as e:
                            logger.error(
                                f"Error processing SF task {sf_task.id}: {str(e)}"
                            )
                            continue

                # Add delay between batches
                await asyncio.sleep(dojo.SF_TASK_CREATION_INTERVAL)

            except Exception as e:
                logger.error(f"Error in SF task processing loop: {str(e)}")
                await asyncio.sleep(dojo.SF_TASK_CREATION_INTERVAL)

    async def send_hfl_request(
        self,
        validator: Validator,
        synapse: TaskSynapseObject,
        task_type: TaskTypeEnum,
        axons: list[AxonInfo],
    ) -> list[TaskSynapseObject] | None:
        """Send Human Feedback Loop requests to miners without using validator's send_request.

        Args:
            validator: The validator instance (used for dendrite and metagraph)
            synapse: Task synapse object with request details
            task_type: Type of HFL task ("TF" for text feedback, "SF" for score feedback)
            previous_task_id: Optional ID of previous task in the feedback loop
            subset_size: Number of miners to target

        Returns:
            Created validator task or None
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
            shuffled=True,  # Only parameter that's actually part of the method
        )

        # Process responses (HFL-specific processing)
        valid_miner_responses: list[TaskSynapseObject] = []
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
                        response.miner_coldkey = validator.metagraph.coldkeys[
                            hotkey_index
                        ]
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

        # if task_type == TaskTypeEnum.TEXT_FEEDBACK:
        #     if not selected_completion_id:
        #         logger.error(
        #             "Selected completion ID is required for TEXT_FEEDBACK tasks... skipping"
        #         )
        #         return None

        #     validator_task, hfl_state = await ORM.save_tf_task(
        #         validator_task=synapse,
        #         miner_responses=valid_responses,
        #         previous_task_id=previous_task_id,
        #         original_task_id=original_task_id,
        #         selected_completion_id=selected_completion_id,
        #     )
        # else:
        #     # For SF tasks, we need to get the HFL state by the previous task id
        #     hfl_state = await HFLManager.get_state_by_previous_task_id(previous_task_id)
        #     if not hfl_state:
        #         logger.error(f"No HFL state found for {previous_task_id}")
        #         return None

        #     validator_task, hfl_state = await ORM.save_sf_task(
        #         validator_task=synapse,
        #         miner_responses=valid_responses,
        #         hfl_state_id=hfl_state.id,
        #         previous_task_id=previous_task_id,
        #     )

        # if validator_task:
        #     logger.success(f"Successfully saved {task_type} task: {synapse.task_id}")
        # else:
        #     logger.error(f"Failed to save {task_type} task: {synapse.task_id}")

        return valid_miner_responses

    @staticmethod
    async def _get_active_miners_for_hfl(
        validator: Validator,
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

        Raises:
            ValueError: If not enough active miners are available
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
        selected_miners = random.sample(active_miners, subset_size)

        logger.info(
            f"Selected {len(selected_miners)} miners for HFL task from {len(active_miners)} active miners"
        )
        return selected_miners
