import asyncio
import json
import math
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator, List

from bittensor.utils.btlogging import logging as logger

from commons.dataset.types import HumanFeedbackResponse
from commons.exceptions import (
    ExpiredFromMoreThanExpireTo,
    InvalidMinerResponse,
    NoNewExpiredTasksYet,
    NoProcessedTasksYet,
)
from commons.hfl_heplers import HFLManager
from commons.utils import datetime_as_utc
from database.client import prisma, transaction
from database.mappers import (
    map_miner_response_to_task_synapse_object,
    map_task_synapse_object_to_completions,
    map_task_synapse_object_to_miner_response,
    map_task_synapse_object_to_validator_task,
    map_validator_task_to_task_synapse_object,
)
from database.prisma import Json
from database.prisma.enums import HFLStatusEnum, TaskTypeEnum
from database.prisma.errors import PrismaError
from database.prisma.models import GroundTruth, HFLState, ValidatorTask
from database.prisma.types import (
    CriterionWhereInput,
    FindManyMinerResponseArgsFromValidatorTask,
    HFLCompletionRelationCreateWithoutRelationsInput,
    HFLStateUpdateInput,
    MinerResponseCreateWithoutRelationsInput,
    MinerResponseInclude,
    MinerScoreCreateInput,
    MinerScoreUpdateInput,
    ValidatorTaskInclude,
    ValidatorTaskUpdateInput,
    ValidatorTaskWhereInput,
)
from dojo import TASK_DEADLINE
from dojo.protocol import (
    DendriteQueryResponse,
    HFLEvent,
    ScoreFeedbackEvent,
    Scores,
    TaskResult,
    TaskSynapseObject,
)


class ORM:
    # TODO: refactor this function
    @staticmethod
    async def get_expired_tasks(
        batch_size: int = 10,
        expire_from: datetime | None = None,
        expire_to: datetime | None = None,
        filter_empty_result: bool = False,
        is_processed: bool = False,
        has_previous_task: bool = False,
        task_types: List[TaskTypeEnum] = [TaskTypeEnum.CODE_GENERATION],
    ) -> AsyncGenerator[tuple[List[DendriteQueryResponse], bool], None]:
        """Returns batches of expired ValidatorTask records and a boolean indicating if there are more batches.

        Args:
            batch_size (int, optional): Number of tasks to return in a batch. Defaults to 10.
            expire_from: (datetime | None) If provided, only tasks with expire_at after expire_from will be returned.
            expire_to: (datetime | None) If provided, only tasks with expire_at before expire_to will be returned.
            You must determine the `expire_at` cutoff yourself, otherwise it defaults to current time UTC.
            filter_empty_results: If True, only include miner_responses with empty task_result
            is_processed: (bool, optional): If True, only processed tasks will be returned. Defaults to False.
            has_previous_task: (bool, optional): Checks if task has a previous task. Defaults to False.

        Raises:
            ExpiredFromMoreThanExpireTo: If expire_from is greater than expire_to
            NoNewExpiredTasksYet: If no expired tasks are found for processing.

        Yields:
            tuple[List[DendriteQueryResponse], bool]: Each yield returns:
            - List of DendriteQueryResponse records with their related completions, miner_responses, and GroundTruth
            - Boolean indicating if there are more batches to process
        """

        # Create miner_responses include query
        miner_responses_include: FindManyMinerResponseArgsFromValidatorTask = {
            "include": {"scores": True}
        }

        if filter_empty_result:
            miner_responses_include["where"] = {"task_result": {"equals": Json("{}")}}

        include_query = ValidatorTaskInclude(
            {
                "completions": {
                    "include": {"criterion": {"include": {"scores": True}}}
                },
                "miner_responses": miner_responses_include,
                "ground_truth": True,
            }
        )

        # Set default expiry timeframe of 6 hours before the latest expired tasks
        if not expire_from:
            expire_from = (
                datetime_as_utc(datetime.now(timezone.utc))
                - timedelta(seconds=TASK_DEADLINE)
                - timedelta(hours=6)
            )
        if not expire_to:
            expire_to = datetime_as_utc(datetime.now(timezone.utc)) - timedelta(
                seconds=TASK_DEADLINE
            )

        # Check that expire_from is lesser than expire_to
        if expire_from > expire_to:
            raise ExpiredFromMoreThanExpireTo(
                "expire_from should be less than expire_to."
            )

        vali_where_query_dict = {
            "expire_at": {
                "gt": expire_from,
                "lt": expire_to,
            },
            "is_processed": is_processed,
        }

        if has_previous_task:
            vali_where_query_dict["previous_task_id"] = {"not": None}

        if task_types:
            vali_where_query_dict["task_type"] = {"in": task_types}

        vali_where_query = ValidatorTaskWhereInput(**vali_where_query_dict)

        # Get total count and first batch of validator tasks in parallel
        task_count, first_batch = await asyncio.gather(
            ValidatorTask.prisma().count(where=vali_where_query),
            ValidatorTask.prisma().find_many(
                include=include_query,
                where=vali_where_query,
                order={"created_at": "desc"},
                take=batch_size,
            ),
        )
        if first_batch and first_batch[0] and first_batch[0].miner_responses:
            logger.debug(
                f"First batch: {[miner_response.task_result for miner_response in first_batch[0].miner_responses]}"
            )
        if is_processed:
            logger.debug(f"Count of processed validator tasks: {task_count}")
        else:
            logger.debug(f"Count of unprocessed validator tasks: {task_count}")

        if not task_count:
            raise NoNewExpiredTasksYet(
                f"No expired validator tasks found for processing, please wait for tasks to pass the task deadline of {TASK_DEADLINE} seconds."
            )
        first_batch_responses = [
            DendriteQueryResponse(
                validator_task=map_validator_task_to_task_synapse_object(task),
                miner_responses=(
                    [
                        map_miner_response_to_task_synapse_object(miner_response, task)
                        for miner_response in task.miner_responses
                    ]
                    if task.miner_responses
                    else []
                ),
            )
            for task in first_batch
        ]
        yield first_batch_responses, task_count > batch_size

        # Process remaining batches
        for skip in range(batch_size, task_count, batch_size):
            validator_tasks = await ValidatorTask.prisma().find_many(
                include=include_query,
                where=vali_where_query,
                order={"created_at": "desc"},
                skip=skip,
                take=batch_size,
            )
            batch_responses = [
                DendriteQueryResponse(
                    validator_task=map_validator_task_to_task_synapse_object(task),
                    miner_responses=(
                        [
                            map_miner_response_to_task_synapse_object(
                                miner_response, task
                            )
                            for miner_response in task.miner_responses
                        ]
                        if task.miner_responses
                        else []
                    ),
                )
                for task in validator_tasks
            ]
            has_more = (skip + batch_size) < task_count
            yield batch_responses, has_more

    @staticmethod
    async def get_real_model_ids(validator_task_id: str) -> dict[str, str]:
        """Fetches a mapping of obfuscated model IDs to real model IDs for a given request ID.

        Args:
            validator_task_id: The ID of the validator task

        Returns:
            A dictionary mapping obfuscated_model_id to real_model_id

        Raises:
            PrismaError: If database query fails
        """
        try:
            ground_truths = await GroundTruth.prisma().find_many(
                where={"validator_task_id": validator_task_id}
            )
            return {gt.obfuscated_model_id: gt.real_model_id for gt in ground_truths}
        except PrismaError as e:
            logger.error(
                f"Database error fetching model IDs for task {validator_task_id}: {e}"
            )
            raise

    @staticmethod
    async def mark_validator_task_as_processed(
        validator_task_ids: list[str],
    ) -> int | None:
        """Mark records associated with validator's tasks as processed.

        Args:
            validator_task_ids (list[str]): List of validator task ids.
        """
        if not validator_task_ids:
            logger.error("No validator task ids provided to mark as processed")
            return

        try:
            async with transaction() as tx:
                num_updated = await tx.validatortask.update_many(
                    data={"is_processed": True},
                    where={"id": {"in": validator_task_ids}},
                )
                if num_updated:
                    logger.success(
                        f"Marked {num_updated} records as processed from {len(validator_task_ids)} task IDs"
                    )
                else:
                    logger.warning("No records were updated")

                return num_updated
        except PrismaError as exc:
            logger.error(f"Prisma error occurred: {exc}")
        except Exception as exc:
            logger.error(f"Unexpected error occurred: {exc}")

    @staticmethod
    async def get_num_processed_tasks() -> int:
        return await ValidatorTask.prisma().count(where={"is_processed": True})

    @staticmethod
    async def update_miner_task_results(
        miner_hotkey: str,
        dojo_task_id: str,
        task_results: List[TaskResult],
        max_retries: int = 3,
    ) -> bool:
        """Updates the task_result field of a MinerResponse with the provided task results.

        Args:
            miner_hotkey (str): The hotkey of the miner
            dojo_task_id (str): The Dojo task ID
            task_results (List[TaskResult]): List of task results to store
            max_retries (int, optional): Maximum number of retry attempts. Defaults to 3.

        Returns:
            bool: True if update was successful, False otherwise
        """
        try:
            for attempt in range(max_retries):
                try:
                    # Convert task_results to JSON-compatible format
                    task_results_json = Json(
                        [result.model_dump() for result in task_results]
                    )

                    # Update the miner response
                    updated = await prisma.minerresponse.update_many(
                        where={
                            "hotkey": miner_hotkey,
                            "dojo_task_id": dojo_task_id,
                        },
                        data={
                            "task_result": task_results_json,
                            "updated_at": datetime.now(timezone.utc),
                        },
                    )

                    if updated:
                        logger.success(
                            f"Updated task results for miner {miner_hotkey}, dojo_task_id {dojo_task_id}"
                        )
                        return True
                    else:
                        if attempt == max_retries - 1:
                            logger.error(
                                f"Failed to update task results after {max_retries} attempts"
                            )
                        else:
                            logger.warning(
                                f"Retrying update, attempt {attempt + 2}/{max_retries}"
                            )
                            await asyncio.sleep(2**attempt)

                except Exception as e:
                    if attempt == max_retries - 1:
                        logger.error(f"Error updating task results: {e}")
                    else:
                        logger.warning(
                            f"Error during attempt {attempt + 1}, retrying: {e}"
                        )
                        await asyncio.sleep(2**attempt)

            return False

        except Exception as e:
            logger.error(f"Unexpected error updating task results: {e}")
            return False

    # TODO: How to store miner scores
    @staticmethod
    async def update_miner_raw_scores(
        miner_responses: List[TaskSynapseObject],
        batch_size: int = 10,
        max_retries: int = 20,
    ) -> tuple[bool, list[int]]:
        """Update the miner's provided raw scores for a list of miner responses.
        NOTE: this is to be used when the task is first saved to validator's database.

        Args:
            miner_responses: List of TaskSynapseObject containing miner responses
            batch_size: Number of responses to process in each batch
            max_retries: Maximum number of retry attempts for failed batches

        Returns:
            Tuple containing:
            - Boolean indicating if all updates were successful
            - List of indices for any failed batches
        """
        if not len(miner_responses):
            logger.warning(
                "Attempting to update miner responses: nothing to update, skipping."
            )
            return True, []

        # Returns ceiling of the division to get number of batches to process
        num_batches = math.ceil(len(miner_responses) / batch_size)
        failed_batch_indices = []

        for batch_id in range(num_batches):
            start_idx = batch_id * batch_size
            end_idx = min((batch_id + 1) * batch_size, len(miner_responses))
            batch_responses = miner_responses[start_idx:end_idx]

            for attempt in range(max_retries):
                try:
                    async with prisma.tx(timeout=timedelta(seconds=30)) as tx:
                        for miner_response in batch_responses:
                            if not miner_response.miner_hotkey:
                                raise InvalidMinerResponse(
                                    f"Miner response {miner_response} must have a hotkey"
                                )

                            # Find the miner response record
                            db_miner_response = await tx.minerresponse.find_first(
                                where={
                                    "hotkey": miner_response.miner_hotkey,
                                    "dojo_task_id": miner_response.dojo_task_id or "",
                                }
                            )

                            if not db_miner_response:
                                raise ValueError(
                                    f"Miner response not found for dojo_task_id: {miner_response.dojo_task_id}, "
                                    f"hotkey: {miner_response.miner_hotkey}"
                                )

                            if not miner_response.completion_responses:
                                continue

                            # Create score records for each completion response
                            for completion in miner_response.completion_responses:
                                # Find or create the criterion record
                                criterion = await tx.criterion.find_first(
                                    where=CriterionWhereInput(
                                        {
                                            "completion_relation": {
                                                "is": {
                                                    "completion_id": completion.completion_id,
                                                    "validator_task_id": miner_response.task_id,
                                                }
                                            }
                                        }
                                    )
                                )

                                if not criterion:
                                    continue

                                # Create scores object
                                scores = Scores(
                                    raw_score=completion.score,
                                    rank_id=completion.rank_id,
                                    # Initialize other scores as None - they'll be computed later
                                    normalised_score=None,
                                    ground_truth_score=None,
                                    cosine_similarity_score=None,
                                    normalised_cosine_similarity_score=None,
                                    cubic_reward_score=None,
                                )

                                await tx.minerscore.upsert(
                                    where={
                                        "criterion_id_miner_response_id": {
                                            "criterion_id": criterion.id,
                                            "miner_response_id": db_miner_response.id,
                                        }
                                    },
                                    data={
                                        "create": MinerScoreCreateInput(
                                            criterion_id=criterion.id,
                                            miner_response_id=db_miner_response.id,
                                            scores=Json(
                                                json.dumps(scores.model_dump())
                                            ),
                                        ),
                                        "update": MinerScoreUpdateInput(
                                            scores=Json(json.dumps(scores.model_dump()))
                                        ),
                                    },
                                )

                    logger.debug(
                        f"Updating completion responses: updated batch {batch_id + 1}/{num_batches}"
                    )
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        logger.error(
                            f"Failed to update batch {batch_id + 1}/{num_batches} after {max_retries} attempts: {e}"
                        )
                        failed_batch_indices.extend(range(start_idx, end_idx))
                    else:
                        logger.warning(
                            f"Retrying batch {batch_id + 1}/{num_batches}, attempt {attempt + 2}/{max_retries}"
                        )
                        await asyncio.sleep(2**attempt)

                await asyncio.sleep(0.1)

        if not failed_batch_indices:
            logger.success(
                f"Successfully updated all {num_batches} batches for {len(miner_responses)} responses"
            )
            return True, []

        return False, failed_batch_indices

    @staticmethod
    async def save_task(
        validator_task: TaskSynapseObject,
        miner_responses: List[TaskSynapseObject],
        ground_truth: dict[str, int],
    ) -> ValidatorTask | None:
        """Saves a task, which consists of both the validator's request and the miners' responses.

        Args:
            validator_task (ValidatorTask): The task created by the validator.
            miner_responses (List[MinerResponse]): The responses made by the miners.
            ground_truth (dict[str, int]): Mapping of completion_id to rank_id for ground truth.

        Returns:
            ValidatorTask | None: The created validator task, or None if failed.
        """
        try:
            async with prisma.tx(timeout=timedelta(seconds=30)) as tx:
                logger.trace("Starting transaction for saving task.")

                # Map validator task using mapper function
                validator_task_data = map_task_synapse_object_to_validator_task(
                    validator_task
                )
                if not validator_task_data:
                    logger.error("Failed to map validator task")
                    return None

                created_task = await tx.validatortask.create(data=validator_task_data)

                # Create completions separately, ValidatorTaskCreateInput does not support CompletionCreateInput
                completions = map_task_synapse_object_to_completions(
                    validator_task, created_task.id
                )

                for completion in completions:
                    await tx.completion.create(data=completion)

                # Pre-process all valid miner responses
                valid_miner_data = []
                for miner_response in miner_responses:
                    try:
                        miner_data = map_task_synapse_object_to_miner_response(
                            miner_response,
                            created_task.id,
                        )
                        valid_miner_data.append(miner_data)
                    except InvalidMinerResponse as e:
                        miner_hotkey = miner_response.miner_hotkey
                        logger.debug(
                            f"Miner response from hotkey: {miner_hotkey} is invalid: {e}"
                        )

                if valid_miner_data:
                    # Bulk create all miner responses
                    await tx.minerresponse.create_many(
                        data=[
                            MinerResponseCreateWithoutRelationsInput(**miner_data)
                            for miner_data in valid_miner_data
                        ]
                    )

                return created_task

        except Exception as e:
            logger.error(f"Failed to save task: {e}")
            return None

    @staticmethod
    async def update_miner_scores(
        task_id: str,
        miner_responses: List[TaskSynapseObject],
        batch_size: int = 10,
        max_retries: int = 3,
    ) -> tuple[bool, list[str]]:
        """Update scores for miners in the MinerScore table.

        Args:
            task_id: The validator task ID
            miner_responses: List of miner responses to update
            batch_size: Number of scores to process in each batch
            max_retries: Maximum number of retry attempts for failed updates

        Returns:
            Tuple containing:
            - Boolean indicating if all updates were successful
            - List of hotkeys that failed to update
        """
        failed_hotkeys = []

        try:
            # Get all miner responses for this task
            db_miner_responses = await prisma.minerresponse.find_many(
                where={
                    "validator_task_id": task_id,
                    "hotkey": {
                        "in": [
                            mr.miner_hotkey for mr in miner_responses if mr.miner_hotkey
                        ]
                    },
                },
                include=MinerResponseInclude(
                    {
                        "scores": {
                            "include": {
                                "criterion_relation": {
                                    "include": {"completion_relation": True}
                                }
                            }
                        }
                    }
                ),
            )

            # Process in batches
            for i in range(0, len(db_miner_responses), batch_size):
                batch = db_miner_responses[i : i + batch_size]

                for attempt in range(max_retries):
                    try:
                        async with prisma.tx() as tx:
                            for db_miner_response in batch:
                                # Find matching miner response from input
                                miner_response = next(
                                    (
                                        mr
                                        for mr in miner_responses
                                        if mr.miner_hotkey == db_miner_response.hotkey
                                    ),
                                    None,
                                )
                                if (
                                    not miner_response
                                    or not miner_response.completion_responses
                                ):
                                    continue

                                # Update each MinerScore record for this miner response
                                for score_record in db_miner_response.scores or []:
                                    completion_id = (
                                        score_record.criterion_relation.completion_relation.completion_id
                                        if score_record.criterion_relation
                                        and score_record.criterion_relation.completion_relation
                                        else None
                                    )

                                    matching_completion = next(
                                        (
                                            cr
                                            for cr in miner_response.completion_responses
                                            if cr.completion_id == completion_id
                                        ),
                                        None,
                                    )

                                    if (
                                        not matching_completion
                                        or not matching_completion.criteria_types
                                    ):
                                        continue

                                    # Find matching criteria type
                                    matching_criteria = next(
                                        (
                                            ct
                                            for ct in matching_completion.criteria_types
                                            if hasattr(ct, "scores") and ct.scores
                                        ),
                                        None,
                                    )

                                    if not matching_criteria:
                                        continue

                                    if matching_criteria and matching_criteria.scores:
                                        # Merge existing scores with new scores
                                        existing_scores = json.loads(
                                            score_record.scores
                                        )
                                        new_scores = (
                                            matching_criteria.scores.model_dump()
                                        )
                                        updated_scores = {
                                            k: (
                                                new_scores.get(k)
                                                if new_scores.get(k) is not None
                                                else v
                                            )
                                            for k, v in existing_scores.items()
                                        }
                                        await tx.minerscore.update(
                                            where={
                                                "criterion_id_miner_response_id": {
                                                    "criterion_id": score_record.criterion_id,
                                                    "miner_response_id": db_miner_response.id,
                                                }
                                            },
                                            data={
                                                "scores": Json(
                                                    json.dumps(updated_scores)
                                                )
                                            },
                                        )
                        break

                    except Exception as e:
                        if attempt == max_retries - 1:
                            logger.error(
                                f"Failed to update scores for batch after {max_retries} attempts: {e}"
                            )
                            failed_hotkeys.extend([m.hotkey for m in batch])
                        else:
                            await asyncio.sleep(2**attempt)

            return (
                len(failed_hotkeys) == 0,
                failed_hotkeys,
            )

        except Exception as e:
            logger.error(f"Error updating miner scores: {e}")
            return False, [mr.miner_hotkey for mr in miner_responses if mr.miner_hotkey]

    @staticmethod
    async def get_processed_tasks(
        batch_size: int = 10,
        expire_from: datetime | None = None,
        expire_to: datetime | None = None,
    ) -> AsyncGenerator[tuple[List[ValidatorTask], bool], None]:
        """
        Returns batches of processed ValidatorTask records and a boolean indicating if there are more batches.
        Used to collect analytics data.

        Args:
            batch_size (int, optional): Number of tasks to return in a batch. Defaults to 10.
            expire_from: (datetime | None) If provided, only tasks with expire_at after expire_from will be returned.
            expire_to: (datetime | None) If provided, only tasks with expire_at before expire_to will be returned.
            You must determine the `expire_at` cutoff yourself, otherwise it defaults to current time UTC.

        Raises:
            ExpiredFromMoreThanExpireTo: If expire_from is greater than expire_to
            NoProcessedTasksYet: If no processed tasks are found for uploading.

        Yields:
            tuple[validator_task, bool]: Each yield returns:
            - List of ValidatorTask records with their related completions, miner_responses, and GroundTruth
            - Boolean indicating if there are more batches to process

        @to-do: write unit test for this function.
        """
        # find all validator requests first
        include_query = ValidatorTaskInclude(
            {
                "completions": {"include": {"criterion": True}},
                "miner_responses": {"include": {"scores": True}},
                "ground_truth": True,
            }
        )

        # Set default expiry timeframe of 6 hours before the latest expired tasks
        if not expire_from:
            expire_from = (
                datetime_as_utc(datetime.now(timezone.utc))
                - timedelta(seconds=TASK_DEADLINE)
                - timedelta(hours=6)
            )
        if not expire_to:
            expire_to = datetime_as_utc(datetime.now(timezone.utc)) - timedelta(
                seconds=TASK_DEADLINE
            )

        # Check that expire_from is lesser than expire_to
        if expire_from > expire_to:
            raise ExpiredFromMoreThanExpireTo(
                "expire_from should be less than expire_to."
            )

        vali_where_query_processed = ValidatorTaskWhereInput(
            {
                # only check for expire at since miner may lie
                "expire_at": {
                    "gt": expire_from,
                    "lt": expire_to,
                },
                "is_processed": True,
            }
        )

        # Get total count and first batch of validator tasks in parallel
        task_count_processed, first_batch = await asyncio.gather(
            ValidatorTask.prisma().count(where=vali_where_query_processed),
            ValidatorTask.prisma().find_many(
                include=include_query,
                where=vali_where_query_processed,
                order={"created_at": "desc"},
                take=batch_size,
            ),
        )

        logger.debug(f"Count of processed validator tasks: {task_count_processed}")

        if not task_count_processed:
            raise NoProcessedTasksYet(
                "No processed tasks found for uploading, wait for next scoring execution."
            )

        yield first_batch, task_count_processed > batch_size

        # Process remaining batches
        for skip in range(batch_size, task_count_processed, batch_size):
            validator_tasks = await ValidatorTask.prisma().find_many(
                include=include_query,
                where=vali_where_query_processed,
                order={"created_at": "desc"},
                skip=skip,
                take=batch_size,
            )
            has_more = (skip + batch_size) < task_count_processed
            yield validator_tasks, has_more

    @staticmethod
    async def get_TF_tasks_by_hfl_status(
        status: HFLStatusEnum,
        expire_from: datetime | None = None,
        expire_to: datetime | None = None,
        batch_size: int = 10,
    ) -> AsyncGenerator[tuple[list[ValidatorTask], bool], None]:
        """Get validator tasks by HFL status in batches.

        Args:
            status: HFL status to filter by
            batch_size: Number of tasks to return in each batch

        Yields:
            tuple[list[ValidatorTask], bool]: Each yield returns:
            - List of validator tasks with the specified HFL status
            - Boolean indicating if there are more batches to process
        """
        try:
            where_query = ValidatorTaskWhereInput(
                task_type=TaskTypeEnum.TEXT_FEEDBACK,
                HFLState={
                    "is": {
                        "status": status,
                    }
                },
            )

            # Add expire time filters if provided
            if expire_from and expire_to:
                where_query["expire_at"] = {
                    "gt": expire_from,
                    "lt": expire_to,
                }
            # Get total count of matching tasks
            total_tasks = await ValidatorTask.prisma().count(where=where_query)

            if total_tasks == 0:
                yield [], False
                return

            # Process in batches
            for skip in range(0, total_tasks, batch_size):
                tasks = await ValidatorTask.prisma().find_many(
                    where=where_query,
                    include={
                        "HFLState": True,
                        "miner_responses": True,
                    },
                    order={"created_at": "desc"},
                    take=batch_size,
                    skip=skip,
                )

                has_more = skip + batch_size < total_tasks
                yield tasks, has_more

        except Exception as e:
            logger.error(f"Error getting tasks by HFL status {status}: {e}")
            yield [], False

    @staticmethod
    async def get_tasks_by_hfl_status(
        status: HFLStatusEnum,
        task_type: TaskTypeEnum | None = None,
        expire_from: datetime | None = None,
        expire_to: datetime | None = None,
        batch_size: int = 10,
        include_options: ValidatorTaskInclude | None = None,
    ) -> AsyncGenerator[tuple[list[ValidatorTask], bool], None]:
        """
        Get validator tasks by HFL status, with optional task type filtering.

        Args:
            status: HFL status to filter by
            task_type: Optional task type to further filter results (TEXT_FEEDBACK, SCORE_FEEDBACK, etc.)
            expire_from: Optional datetime to filter tasks that expired after this time
            expire_to: Optional datetime to filter tasks that expired before this time
            batch_size: Number of tasks to return in each batch
            include_options: Optional dictionary of additional relations to include

        Yields:
            tuple[list[ValidatorTask], bool]: Each yield returns:
            - List of validator tasks with the specified HFL status and type
            - Boolean indicating if there are more batches to process
        """
        try:
            # Build the base query
            where_query = ValidatorTaskWhereInput(HFLState={"is": {"status": status}})

            # Add task type filter if specified
            if task_type:
                where_query["task_type"] = task_type

            # Add expire time filters if provided
            if expire_from and expire_to:
                where_query["expire_at"] = {
                    "gt": expire_from,
                    "lt": expire_to,
                }

            # Get total count of matching tasks
            total_tasks = await ValidatorTask.prisma().count(where=where_query)

            if total_tasks == 0:
                yield [], False
                return

            # Process in batches
            for skip in range(0, total_tasks, batch_size):
                tasks = await ValidatorTask.prisma().find_many(
                    where=where_query,
                    include=include_options,
                    order={"created_at": "desc"},
                    take=batch_size,
                    skip=skip,
                )

                has_more = skip + batch_size < total_tasks
                yield tasks, has_more

        except Exception as e:
            logger.error(
                f"Error getting tasks by HFL status {status} and type {task_type}: {e}"
            )
            yield [], False

    @staticmethod
    async def create_hfl_completion_relation(
        completion_id_pairs: List[tuple[str, str]],
    ) -> bool:
        """Create HFLCompletionRelation records connecting TF completions to SF completions.

        Args:
            completion_id_pairs: List of tuples with (tf_completion_id, sf_completion_id) pairs

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create a relation for each (tf_id, sf_id) pair
            async with prisma.tx() as tx:
                for tf_id, sf_id in completion_id_pairs:
                    await tx.hflcompletionrelation.create(
                        data={
                            "miner_response_id": tf_id,
                            "sf_completion_id": sf_id,
                        }
                    )

            logger.success(
                f"Created {len(completion_id_pairs)} HFLCompletionRelation records"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to create HFLCompletionRelation records: {e}")
            return False

    @staticmethod
    async def save_tf_task(
        validator_task: TaskSynapseObject,
        miner_responses: list[TaskSynapseObject],
        previous_task_id: str,
        selected_completion_id: str,
        original_task_id: str | None = None,
    ) -> tuple[ValidatorTask, HFLState]:
        """
        Save a Text Feedback task and create a new HFL state within a single transaction.

        Args:
            validator_task: The task synapse object
            miner_responses: List of miner responses
            original_task_id: ID of original task that initiated the HFL

        Returns:
            Tuple of (created task, created HFL state)
        """
        async with prisma.tx() as tx:
            hfl_state = await HFLManager.create_state(
                current_task_id=validator_task.task_id,
                previous_task_id=previous_task_id,
                original_task_id=original_task_id,
                status=HFLStatusEnum.TF_PENDING,
                selected_completion_id=selected_completion_id,
                tx=tx,
            )
            # Create the validator task with the HFL state ID
            validator_task_data = map_task_synapse_object_to_validator_task(
                validator_task
            )

            # Add the HFL state ID to the validator task data
            validator_task_data["hfl_state_id"] = hfl_state.id
            validator_task_data["previous_task_id"] = previous_task_id

            created_task = await tx.validatortask.create(data=validator_task_data)
            await tx.validatortask.update(
                where={"id": previous_task_id},
                data={"next_task": {"connect": {"id": created_task.id}}},
            )

            # Create completions separately, ValidatorTaskCreateInput does not support CompletionCreateInput
            completions = map_task_synapse_object_to_completions(
                validator_task, created_task.id
            )

            for completion in completions:
                await tx.completion.create(data=completion)

            # Pre-process all valid miner responses
            valid_miner_data = []
            for miner_response in miner_responses:
                try:
                    miner_data = map_task_synapse_object_to_miner_response(
                        miner_response,
                        created_task.id,
                    )
                    valid_miner_data.append(miner_data)
                except InvalidMinerResponse as e:
                    miner_hotkey = miner_response.miner_hotkey
                    logger.debug(
                        f"Miner response from hotkey: {miner_hotkey} is invalid: {e}"
                    )

            if valid_miner_data:
                # Bulk create all miner responses
                await tx.minerresponse.create_many(
                    data=[
                        MinerResponseCreateWithoutRelationsInput(**miner_data)
                        for miner_data in valid_miner_data
                    ]
                )
            return created_task, hfl_state

    @staticmethod
    async def save_sf_task(
        validator_task: TaskSynapseObject,
        miner_responses: list[TaskSynapseObject],
        hfl_state: HFLState,
        previous_task_id: str,
        human_feedback_response: HumanFeedbackResponse,
    ) -> tuple[ValidatorTask, HFLState]:
        """
        Save a Score Feedback task and update an existing HFL state within a single transaction.

        Args:
            validator_task: The task synapse object
            miner_responses: List of miner responses
            hfl_state_id: ID of existing HFL state to update

        Returns:
            Tuple of (created task, updated HFL state)
        """
        async with prisma.tx() as tx:
            validator_task_data = map_task_synapse_object_to_validator_task(
                validator_task
            )

            # Add the HFL state ID to the validator task data
            validator_task_data["hfl_state_id"] = hfl_state.id
            validator_task_data["previous_task_id"] = previous_task_id

            created_task = await tx.validatortask.create(data=validator_task_data)
            await tx.validatortask.update(
                where={"id": previous_task_id},
                data={"next_task": {"connect": {"id": created_task.id}}},
            )

            completions = map_task_synapse_object_to_completions(
                validator_task, created_task.id
            )

            for completion in completions:
                await tx.completion.create(data=completion)

            # Pre-process all valid miner responses
            valid_miner_data = []
            for miner_response in miner_responses:
                try:
                    miner_data = map_task_synapse_object_to_miner_response(
                        miner_response,
                        created_task.id,
                    )
                    valid_miner_data.append(miner_data)
                except InvalidMinerResponse as e:
                    miner_hotkey = miner_response.miner_hotkey
                    logger.debug(
                        f"Miner response from hotkey: {miner_hotkey} is invalid: {e}"
                    )

            if valid_miner_data:
                await tx.minerresponse.create_many(
                    data=[
                        MinerResponseCreateWithoutRelationsInput(**miner_data)
                        for miner_data in valid_miner_data
                    ]
                )

            # Update HFL state with current task id and status
            updated_hfl_state = await HFLManager.update_state(
                hfl_state_id=hfl_state.id,
                updates=HFLStateUpdateInput(
                    current_task_id=created_task.id,
                    status=HFLStatusEnum.SF_PENDING,
                ),
                event_data=ScoreFeedbackEvent(
                    type=HFLStatusEnum.SF_PENDING,
                    task_id=validator_task.task_id,
                    syn_req_id=hfl_state.current_synthetic_req_id
                    if hfl_state.current_synthetic_req_id
                    else "",
                    iteration=hfl_state.current_iteration,
                    timestamp=datetime_as_utc(datetime.now(timezone.utc)),
                ),
                tx=tx,
            )
            if not updated_hfl_state:
                raise ValueError(f"Failed to update HFL state with ID {hfl_state.id}")

            # TODO: remove this
            logger.info(
                f"completion-id {[c for comp in validator_task.completion_responses or [] for c in comp.completion_id]}"
            )
            logger.info(
                f"Creating completion relations: human_feedback_response={human_feedback_response}"
            )
            completion_relations = [
                HFLCompletionRelationCreateWithoutRelationsInput(
                    miner_response_id=feedback_task.miner_response_id,
                    sf_completion_id=feedback_task.completion_id,
                )
                for feedback_task in human_feedback_response.human_feedback_tasks
            ]

            logger.info(
                f"Creating completion relations: completion_relations={completion_relations}"
            )

            await tx.hflcompletionrelation.create_many(data=completion_relations)

            return created_task, updated_hfl_state

    @staticmethod
    async def get_validator_task_by_id(
        task_id: str, include: ValidatorTaskInclude | None = None
    ) -> ValidatorTask | None:
        """Get a task by its ID."""
        if include:
            task = await ValidatorTask.prisma().find_unique(
                where={"id": task_id},
                include=include,
            )
        else:
            task = await ValidatorTask.prisma().find_unique(
                where={"id": task_id},
                include=ValidatorTaskInclude(
                    completions={
                        "include": {"criterion": {"include": {"scores": True}}}
                    },
                    miner_responses={"include": {"scores": True}},
                ),
            )

        if not task:
            logger.error(f"Task with ID {task_id} not found")
            return None

        return task

    @staticmethod
    async def save_tf_retry_responses(
        validator_task_id: str,
        hfl_state: HFLState,
        miner_responses: list[TaskSynapseObject],
    ) -> tuple[int, HFLState]:
        """
        Save additional miner responses for an existing validator task and update
        the HFL state retry count in a single transaction.

        Args:
            validator_task_id: ID of the existing validator task
            hfl_state: HFL state to update
            miner_responses: List of additional miner responses from send_hfl_request

        Returns:
            Tuple of (number of saved responses, whether retry count was updated)
        """
        if not miner_responses:
            return 0, hfl_state

        saved_count = 0

        try:
            async with prisma.tx() as tx:
                # Process each miner response
                for response in miner_responses:
                    if (
                        not response.dojo_task_id
                        or not response.miner_hotkey
                        or not response.miner_coldkey
                    ):
                        logger.warning(
                            "Missing dojo_task_id or hotkey in miner response"
                        )
                        continue

                    try:
                        # Check if there's already a response from this miner for this validator task
                        existing_response = await tx.minerresponse.find_first(
                            where={
                                "validator_task_id": validator_task_id,
                                "hotkey": response.miner_hotkey,
                            }
                        )

                        if existing_response:
                            # Update the existing response with the new dojo_task_id
                            await tx.minerresponse.update(
                                where={"id": existing_response.id},
                                data={
                                    "dojo_task_id": response.dojo_task_id,
                                    "updated_at": datetime_as_utc(datetime.now()),
                                },
                            )
                            logger.debug(
                                f"Updated existing response for miner {response.miner_hotkey} with new dojo_task_id"
                            )
                        else:
                            # Create a new response
                            await tx.minerresponse.create(
                                data={
                                    "validator_task_id": validator_task_id,
                                    "dojo_task_id": response.dojo_task_id,
                                    "hotkey": response.miner_hotkey,
                                    "coldkey": response.miner_coldkey,
                                    "task_result": Json(json.dumps({})),
                                }
                            )
                            logger.debug(
                                f"Created new response for miner {response.miner_hotkey}"
                            )

                        saved_count += 1

                    except Exception as e:
                        logger.error(
                            f"Error saving miner response for {response.miner_hotkey}: {e}"
                        )
                        continue

                updated_hfl_state = await HFLManager.update_state(
                    hfl_state_id=hfl_state.id,
                    updates=HFLStateUpdateInput(
                        tf_retry_count=hfl_state.tf_retry_count + 1
                    ),
                )
            return saved_count, updated_hfl_state

        except Exception as e:
            logger.error(f"Transaction failed to save TF retry responses: {e}")
            return 0, hfl_state

    @staticmethod
    async def get_hfl_state_by_current_task_id(task_id: str) -> HFLState | None:
        try:
            hfl_state = await prisma.hflstate.find_first(
                where={"current_task_id": task_id}, include={"ValidatorTask": True}
            )
            return hfl_state
        except:  # noqa: E722
            logger.error(f"Failed to get HFL State with current task id: {task_id}")
        return None

    @staticmethod
    async def get_original_or_parent_sf_task(sf_task_id: str) -> ValidatorTask | None:
        """
        Get the original or parent task for scoring purposes.
        ┌─────────────┐       ┌──────┐       ┌──────┐      ┌──────┐     ┌──────┐
        │Original Task│──────▶│ TF_1 │──────▶│ SF_1 │─────▶│ TF_2 │────▶│ SF_2 │
        └─────────────┘       └──────┘       └──────┘      └──────┘     └──────┘
        For iteration 1, returns the original CODE_GENERATION task.
        For iteration > 1, returns the previous SF task by finding the task
        whose next_task_id points to the current task's previous_task_id.

        Args:
            sf_task_id: ID of the current SF task

        Returns:
            Original task or previous SF task, or None if not found
        """
        try:
            # First, get the current SF task with HFL state
            current_sf_task = await ValidatorTask.prisma().find_unique(
                where={"id": sf_task_id},
                include={
                    "HFLState": True,
                },
            )

            if not current_sf_task:
                logger.error(f"SF task {sf_task_id} not found")
                return None

            if not current_sf_task.HFLState:
                logger.error(f"SF task {sf_task_id} has no HFL state")
                return None

            # TODO: is this check necessary?
            if current_sf_task.HFLState.status != HFLStatusEnum.SF_COMPLETED:
                logger.error(
                    f"SF task {sf_task_id} is not completed yet {current_sf_task.HFLState.status}"
                )
                return None

            # Get the current iteration from HFL state
            current_iteration = current_sf_task.HFLState.current_iteration

            if current_iteration == 1:
                # For first iteration, get the original task directly from HFL state
                original_task_id = current_sf_task.HFLState.original_task_id
                original_task = await ValidatorTask.prisma().find_unique(
                    where={"id": original_task_id},
                    include={
                        "completions": True,
                        "miner_responses": {
                            "include": {
                                "scores": {"include": {"criterion_relation": True}}
                            }
                        },
                    },
                )

                logger.info(
                    f"Retrieved original task {original_task_id} for first iteration SF task {sf_task_id}"
                )
                return original_task
            else:
                # We have a TF task that is the previous task of our current SF task
                tf_task_id = current_sf_task.previous_task_id

                if not tf_task_id:
                    logger.error(f"SF task {sf_task_id} has no previous task ID")
                    return None

                # Find the task whose next_task_id points to our TF task
                # This is our previous SF task
                previous_sf_task = await ValidatorTask.prisma().find_first(
                    where={"next_task_id": tf_task_id},
                    include={
                        "completions": True,
                        "miner_responses": {
                            "include": {
                                "scores": {"include": {"criterion_relation": True}}
                            }
                        },
                    },
                )

                if previous_sf_task:
                    logger.info(
                        f"Retrieved previous SF task {previous_sf_task.id} using next_task_id relation"
                    )
                    return previous_sf_task
                else:
                    logger.error(
                        f"Could not find previous SF task for TF task {tf_task_id}"
                    )
                    return None

        except Exception as e:
            logger.error(f"Error getting original or parent SF task: {e}")
            return None

    @staticmethod
    async def get_task_by_id(task_id: str) -> ValidatorTask | None:
        """Given a current task id, fetch the previous task"""
        try:
            task = await prisma.validatortask.find_unique(where={"id": task_id})
            if task is None:
                raise
        except Exception as e:
            logger.error(f"Failed to get validator task with ID {task_id}: {e}")
        return None

    # TODO: KIV
    @staticmethod
    async def update_hfl_scores(
        sf_task_id: str,
        hotkey_to_scores: dict[str, float],
        batch_size: int = 10,
        max_retries: int = 3,
    ) -> tuple[bool, list[str]]:
        """Update HFL scores for miners in the MinerScore table.

        Args:
            sf_task_id: The validator task ID for the SF task
            hotkey_to_scores: Dictionary mapping miner hotkeys to their calculated HFL scores
            batch_size: Number of scores to process in each batch
            max_retries: Maximum number of retry attempts for failed updates

        Returns:
            Tuple containing:
            - Boolean indicating if all updates were successful
            - List of hotkeys that failed to update
        """
        failed_hotkeys = []

        try:
            # Get all miner responses for this task
            db_miner_responses = await prisma.minerresponse.find_many(
                where={
                    "validator_task_id": sf_task_id,
                    "hotkey": {"in": list(hotkey_to_scores.keys())},
                },
                include=MinerResponseInclude(
                    {
                        "scores": {
                            "include": {
                                "criterion_relation": {
                                    "include": {"completion_relation": True}
                                }
                            }
                        }
                    }
                ),
            )

            # Process miner responses in batches
            for i in range(0, len(db_miner_responses), batch_size):
                batch = db_miner_responses[i : i + batch_size]

                for attempt in range(max_retries):
                    try:
                        async with prisma.tx() as tx:
                            for db_miner_response in batch:
                                hotkey = db_miner_response.hotkey
                                if hotkey not in hotkey_to_scores:
                                    continue

                                hfl_score = hotkey_to_scores[hotkey]

                                # Update each MinerScore record for this miner response
                                for score_record in db_miner_response.scores or []:
                                    # Only update one record per miner with the HFL score
                                    # Consider using a specific criterion or just the first one
                                    if (
                                        score_record.criterion_relation
                                        and score_record.criterion_relation.completion_relation
                                    ):
                                        # Parse the existing scores
                                        existing_scores = json.loads(
                                            score_record.scores
                                        )

                                        # Add the HFL scores (tf_score field)
                                        existing_scores["tf_score"] = hfl_score

                                        await tx.minerscore.update(
                                            where={
                                                "criterion_id_miner_response_id": {
                                                    "criterion_id": score_record.criterion_id,
                                                    "miner_response_id": db_miner_response.id,
                                                }
                                            },
                                            data={
                                                "scores": Json(
                                                    json.dumps(existing_scores)
                                                )
                                            },
                                        )

                                        # Only update one score record per miner
                                        break

                        # Break out of retry loop if successful
                        break

                    except Exception as e:
                        if attempt == max_retries - 1:
                            logger.error(
                                f"Failed to update HFL scores after {max_retries} attempts: {e}"
                            )
                            failed_hotkeys.extend([mr.hotkey for mr in batch])
                        else:
                            await asyncio.sleep(2**attempt)

            return (
                len(failed_hotkeys) == 0,
                failed_hotkeys,
            )

        except Exception as e:
            logger.error(f"Error updating HFL scores: {e}")
            return False, list(hotkey_to_scores.keys())

    @staticmethod
    async def update_hfl_final_scores(
        sf_task_id: str,
        hotkey_to_sf_scores: dict[str, float],
        hotkey_to_tf_scores: dict[str, float],
        batch_size: int = 10,
        max_retries: int = 3,
    ) -> tuple[bool, list[str]]:
        """Update both SF and TF scores in the MinerScore table.

        Args:
            sf_task_id: Score Feedback task ID
            hotkey_to_sf_scores: SF scores component (ICC)
            hotkey_to_tf_scores: TF scores component (feedback improvement)
            batch_size: Batch size for processing
            max_retries: Max retry attempts

        Returns:
            Tuple containing success flag and list of failed hotkeys
        """
        try:
            # Get SF task and related data
            sf_task = await ORM.get_validator_task_by_id(sf_task_id)
            if not sf_task:
                logger.error(f"No SF task found with ID {sf_task_id}")
                return False, []

            # Find original or parent task for updating TF scores
            previous_task = await ORM.get_original_or_parent_sf_task(sf_task_id)
            if not previous_task:
                logger.error(f"Previous task not found for SF task {sf_task_id}")
                return False, []

            # Get all miner responses for SF task
            sf_miner_responses = await prisma.minerresponse.find_many(
                where={
                    "validator_task_id": sf_task_id,
                    "hotkey": {"in": list(hotkey_to_sf_scores.keys())},
                },
                include={"scores": {"include": {"criterion_relation": True}}},
            )

            # Get all miner responses for parent/original task
            parent_miner_responses = await prisma.minerresponse.find_many(
                where={
                    "validator_task_id": previous_task.id,
                    "hotkey": {"in": list(hotkey_to_tf_scores.keys())},
                },
                include={"scores": {"include": {"criterion_relation": True}}},
            )

            failed_hotkeys = []

            # Update SF scores (ICC scores in SF task)
            for i in range(0, len(sf_miner_responses), batch_size):
                batch = sf_miner_responses[i : i + batch_size]

                for attempt in range(max_retries):
                    try:
                        async with prisma.tx() as tx:
                            for miner_response in batch:
                                hotkey = miner_response.hotkey
                                if hotkey not in hotkey_to_sf_scores:
                                    continue

                                sf_score = hotkey_to_sf_scores[hotkey]

                                # Update scores for this miner in SF task (criteria with type "score")
                                for score_record in miner_response.scores or []:
                                    # We only need to find score criteria
                                    criterion = score_record.criterion_relation
                                    if (
                                        criterion
                                        and criterion.criteria_type.lower() == "score"
                                    ):
                                        # Parse existing scores
                                        scores_data = json.loads(score_record.scores)

                                        # Update with the SF component (ICC)
                                        if isinstance(scores_data, dict):
                                            # Update appropriate fields in Scores model
                                            scores_data["icc_score"] = sf_score

                                            await tx.minerscore.update(
                                                where={
                                                    "criterion_id_miner_response_id": {
                                                        "criterion_id": score_record.criterion_id,
                                                        "miner_response_id": miner_response.id,
                                                    }
                                                },
                                                data={
                                                    "scores": Json(
                                                        json.dumps(scores_data)
                                                    )
                                                },
                                            )
                                            break

                        # If we make it here, break the retry loop
                        break

                    except Exception as e:
                        if attempt == max_retries - 1:
                            logger.error(
                                f"Failed to update SF scores after {max_retries} attempts: {e}"
                            )
                            failed_hotkeys.extend([mr.hotkey for mr in batch])
                        else:
                            await asyncio.sleep(2**attempt)

            # Update TF scores (text feedback scores in parent/original task)
            for i in range(0, len(parent_miner_responses), batch_size):
                batch = parent_miner_responses[i : i + batch_size]

                for attempt in range(max_retries):
                    try:
                        async with prisma.tx() as tx:
                            for miner_response in batch:
                                hotkey = miner_response.hotkey
                                if hotkey not in hotkey_to_tf_scores:
                                    continue

                                tf_score = hotkey_to_tf_scores[hotkey]

                                # Update scores for this miner in parent/original task
                                for score_record in miner_response.scores or []:
                                    criterion = score_record.criterion_relation
                                    if criterion:
                                        # Find appropriate type for updating
                                        if criterion.criteria_type.lower() == "text":
                                            # For text feedback, use TextFeedbackScore model
                                            scores_data = json.loads(
                                                score_record.scores
                                            )

                                            if isinstance(scores_data, dict):
                                                scores_data["tf_score"] = tf_score

                                                await tx.minerscore.update(
                                                    where={
                                                        "criterion_id_miner_response_id": {
                                                            "criterion_id": score_record.criterion_id,
                                                            "miner_response_id": miner_response.id,
                                                        }
                                                    },
                                                    data={
                                                        "scores": Json(
                                                            json.dumps(scores_data)
                                                        )
                                                    },
                                                )
                                                break

                        # If we make it here, break the retry loop
                        break

                    except Exception as e:
                        if attempt == max_retries - 1:
                            logger.error(
                                f"Failed to update TF scores after {max_retries} attempts: {e}"
                            )
                            failed_hotkeys.extend([mr.hotkey for mr in batch])
                        else:
                            await asyncio.sleep(2**attempt)

            return len(failed_hotkeys) == 0, failed_hotkeys

        except Exception as e:
            logger.error(f"Error updating HFL scores: {e}")
            return False, []

    @staticmethod
    async def update_hfl_state_and_task(
        hfl_state_id: str,
        validator_task_id: str,
        state_updates: HFLStateUpdateInput,
        task_updates: ValidatorTaskUpdateInput,
        event_data: HFLEvent | None = None,
    ) -> HFLState:
        """
        Update HFL state and validator task in a single transaction.

        Args:
            hfl_state_id: ID of the HFL state to update
            validator_task_id: ID of the validator task to update
            state_updates: HFLStateUpdateInput of HFL state updates
            task_updates: ValidatorTaskUpdateInput of validator task updates
            event_data: Optional event data to append to HFL state events

        Returns:
            Updated HFL state
        """
        async with prisma.tx() as tx:
            # Update HFL state using HFLManager (which handles events and state transitions)
            updated_state = await HFLManager.update_state(
                hfl_state_id=hfl_state_id,
                updates=state_updates,
                event_data=event_data,
                tx=tx,  # Pass the transaction to ensure both updates happen atomically
            )

            # Update validator task if there are updates
            if task_updates:
                await tx.validatortask.update(
                    where={"id": validator_task_id}, data=task_updates
                )

            return updated_state


# ---------------------------------------------------------------------------- #
#                          Test custom ORM functions                           #
# ---------------------------------------------------------------------------- #


async def test_get_expired_tasks():
    """Test function for get_expired_tasks."""
    from database.client import connect_db, disconnect_db

    # Connect to database first
    await connect_db()

    try:
        orm = ORM()
        batch_size = 5
        expire_from = datetime_as_utc(datetime.now(timezone.utc)) - timedelta(days=1)
        expire_to = datetime_as_utc(datetime.now(timezone.utc))

        total_tasks = 0
        async for tasks, has_more in orm.get_expired_tasks(
            batch_size, expire_from, expire_to, is_processed=False
        ):
            total_tasks += len(tasks)
            if not has_more:
                break
        logger.info(f"Total number of unprocessed expired tasks: {total_tasks}")
    except NoNewExpiredTasksYet as e:
        print(f"No new expired tasks: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        # Always disconnect when done
        await disconnect_db()


async def test_get_real_model_ids():
    """Test function for get_real_model_ids."""
    from database.client import connect_db, disconnect_db

    # Connect to database first
    await connect_db()

    try:
        orm = ORM()
        # Use a known validator_task_id from your database
        validator_task_id = "5c91e4b4-a675-47e8-a06b-c2e66ec67239"

        model_id_mapping = await orm.get_real_model_ids(validator_task_id)
        logger.info(f"Model ID mapping: {model_id_mapping}")

        # Print the number of mappings found
        logger.info(f"Number of model ID mappings found: {len(model_id_mapping)}")

    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        # Always disconnect when done
        await disconnect_db()


async def test_mark_validator_task_as_processed():
    """Test function for mark_validator_task_as_processed."""
    from database.client import connect_db, disconnect_db

    # Connect to database first
    await connect_db()

    try:
        orm = ORM()
        # Use a list of known validator_task_ids from your database
        validator_task_ids = [
            "5c91e4b4-a675-47e8-a06b-c2e66ec67239",
        ]

        # Get initial processed state
        initial_tasks = await ValidatorTask.prisma().find_many(
            where={"id": {"in": validator_task_ids}}
        )
        logger.info(
            f"Initial processed state: {[task.is_processed for task in initial_tasks]}"
        )

        # Mark tasks as processed
        num_updated = await orm.mark_validator_task_as_processed(validator_task_ids)
        logger.info(f"Number of tasks marked as processed: {num_updated}")

        # Verify the update
        updated_tasks = await ValidatorTask.prisma().find_many(
            where={"id": {"in": validator_task_ids}}
        )
        logger.info(
            f"Updated processed state: {[task.is_processed for task in updated_tasks]}"
        )

    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        # Always disconnect when done
        await disconnect_db()


async def test_get_num_processed_tasks():
    """Test function for get_num_processed_tasks."""
    from database.client import connect_db, disconnect_db

    # Connect to database first
    await connect_db()

    try:
        orm = ORM()
        num_processed = await orm.get_num_processed_tasks()
        logger.info(f"Number of processed tasks: {num_processed}")

    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        # Always disconnect when done
        await disconnect_db()


# TODO: Update this test
# async def test_save_task():
#     """Test function for save_task."""
#     from database.client import connect_db, disconnect_db
#     from datetime import datetime, timezone
#     from dojo.protocol import TaskType, CodeAnswer, CompletionResponses, FileObject

#     # Connect to database first
#     await connect_db()

#     try:
#         orm = ORM()

#         # Create test validator task
#         test_validator_task = ValidatorTask(
#             prompt="Test prompt",
#             task_type=TaskType.CODE_GENERATION.value,
#             expire_at=datetime_as_utc(datetime.now(timezone.utc)),
#             completions=[
#                 Completion(
#                     model="model1",
#                     completion=CodeAnswer(
#                         files=[
#                             FileObject(
#                                 filename="fibonacci.py",
#                                 content="""def fibonacci(n):
#                                         if n <= 1:
#                                             return n
#                                         return fibonacci(n-1) + fibonacci(n-2)""",
#                                 language="python",
#                             )
#                         ]
#                     ),
#                     criterion=[],
#                 ),
#                 Completion(
#                     model="model2",
#                     completion=CodeAnswer(
#                         files=[
#                             FileObject(
#                                 filename="fibonacci.py",
#                                 content="""def fibonacci(n):
#                                         a, b = 0, 1
#                                         for _ in range(n):
#                                             a, b = b, a + b
#                                         return a""",
#                                 language="python",
#                             )
#                         ]
#                     ),
#                     criterion=[],
#                 ),
#             ],
#         )

#         # Create test miner responses
#         test_miner_responses = [
#             MinerResponse(
#                 dojo_task_id="test_task_1",
#                 hotkey="test_hotkey_1",
#                 coldkey="test_coldkey_1",
#                 task_result=CompletionResponses(responses=[{"model1": 1, "model2": 2}]),
#             )
#         ]

#         # Create test ground truth
#         test_ground_truth = {"model1": 1, "model2": 2}

#         # Save the task
#         created_task = await orm.save_task(
#             test_validator_task, test_miner_responses, test_ground_truth
#         )

#         if created_task:
#             logger.success(f"Successfully created task with ID: {created_task.id}")

#             # Verify the saved data
#             saved_task = await ValidatorTask.prisma().find_unique(
#                 where={"id": created_task.id},
#                 include={
#                     "completions": True,
#                     "miner_responses": True,
#                     "GroundTruth": True,
#                 },
#             )

#             logger.info(f"Number of completions: {len(saved_task.completions)}")
#             logger.info(f"Number of miner responses: {len(saved_task.miner_responses)}")
#             logger.info(f"Number of ground truths: {len(saved_task.GroundTruth)}")
#         else:
#             logger.error("Failed to create task")

#     except Exception as e:
#         logger.error(f"An error occurred: {e}")
#     finally:
#         # Always disconnect when done
#         await disconnect_db()


if __name__ == "__main__":

    async def run_tests():
        # await test_get_expired_tasks()
        # await test_get_real_model_ids()
        # await test_mark_validator_task_as_processed()
        await test_get_num_processed_tasks()
        # await test_save_task()

    asyncio.run(run_tests())
