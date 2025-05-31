import copy
import json
import traceback
from collections import defaultdict

from loguru import logger
from pydantic import ValidationError

from commons.human_feedback import HFLConstants
from commons.orm import ORM
from commons.stats import calculate_icc
from database.prisma.enums import HFLStatusEnum
from database.prisma.models import (
    HFLCompletionRelation,
    HFLState,
    MinerResponse,
    MinerScore,
    ValidatorTask,
)
from dojo.protocol import Scores

TF_WEIGHT = HFLConstants.TF_WEIGHT.value
SF_WEIGHT = HFLConstants.SF_WEIGHT.value


async def score_hfl_tasks(
    task: ValidatorTask,
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    """MAIN DRIVER FUNCTION TO SCORE HFL TASKS"""
    hotkey_to_score: dict[str, float] = {}
    hotkey_to_tf_score: dict[str, float] = {}
    hotkey_to_sf_score: dict[str, float] = {}

    try:
        if not task.miner_responses:
            logger.warning(
                f"Task with id: {task.id} has no miner responses for scoring"
            )
            return hotkey_to_score, hotkey_to_tf_score, hotkey_to_sf_score

        # Filter valid miner responses
        task.miner_responses = filter_valid_miner_responses(task.miner_responses)
        if not task.miner_responses:
            logger.warning(f"Task with id: {task.id} has no valid miner responses")
            return hotkey_to_score, hotkey_to_tf_score, hotkey_to_sf_score

        # Rest of your scoring logic
        hotkey_to_tf_score = await _calc_tf_score(task)
        if not hotkey_to_tf_score:
            logger.warning(f"Failed to calculate TF score for task {task.id}")
            return hotkey_to_score, hotkey_to_tf_score, hotkey_to_sf_score

        hotkey_to_sf_score = await _calc_sf_score(task)

        for hotkey, tf_score in hotkey_to_tf_score.items():
            hotkey_to_score[hotkey] = (
                TF_WEIGHT * tf_score + SF_WEIGHT * hotkey_to_sf_score.get(hotkey, 0.0)
            )

        return hotkey_to_score, hotkey_to_tf_score, hotkey_to_sf_score
    except Exception as e:
        logger.error(f"Error in score_hfl_tasks for task {task.id}: {e}")
        logger.error(f"Error traceback: {traceback.format_exc()}")
        return hotkey_to_score, hotkey_to_tf_score, hotkey_to_sf_score


@staticmethod
async def _calc_sf_score(task: ValidatorTask) -> dict[str, float]:
    """Calculate SF Score, which is used when we don't have ground truth for the score feedback task.
    Args:
        task (ValidatorTask): Task to score

    Returns:
        dict[str, float]: Mapping of hotkey to score
    """
    # ensure completion ordering
    task = ensure_miner_response_order(task)
    # NOTE: you cannot use Scoring.calculate_score because SF Task doesn't have ground truth
    # NOTE: this will allow for sybil attacks tho but just getting it out first

    # for each miner's response, calculate the ICC(2,1) with the average score
    hotkey_to_raw_scores: dict[str, list[float]] = {}
    for miner_response in task.miner_responses or []:
        if miner_response.hotkey not in hotkey_to_raw_scores:
            hotkey_to_raw_scores[miner_response.hotkey] = []

        # TODO: refactor to an ORM utils maybe
        miner_raw_scores: list[float] = []
        for score in miner_response.scores or []:
            scores = Scores.model_validate_json(score.scores)
            if scores.raw_score:
                miner_raw_scores.append(scores.raw_score)

        hotkey_to_raw_scores[miner_response.hotkey] = miner_raw_scores

    if len(hotkey_to_raw_scores) < 2:
        logger.warning(
            f"Not enough raw scores to calculate ICC for task {task.id}, returning empty dict"
        )
        return {}

    hotkey_to_icc = calculate_icc(hotkey_to_scores=hotkey_to_raw_scores)
    return hotkey_to_icc


def _validate_task(task: ValidatorTask, hfl_state: HFLState) -> None:
    """Validate a task for HFL Scoring.

    Args:
        task (ValidatorTask): task
        hfl_state (HFLState): hfl_state

    Returns:
        None:
    """
    if hfl_state.status != HFLStatusEnum.SF_COMPLETED:
        raise Exception("HFL State not ready for scoring")
    if not task.completions:
        raise Exception("Task completions not found")

    sf_task_id = task.id
    tf_task_id = task.previous_task_id
    if not tf_task_id:
        raise ValueError(
            f"Previous task id should be filled for SF_TASK, task id: {sf_task_id}"
        )


@staticmethod
async def _calc_tf_score(sf_task: ValidatorTask) -> dict[str, float]:
    """Calculate TF_TASK score based on how much each miner's feedback improved the completion.

    Args:
        sf_task (ValidatorTask): SF task with completions to evaluate

    Returns:
        dict[str, float]: Mapping of miner hotkeys to their TF scores
    """
    sf_task_id = sf_task.id
    try:
        # Get and validate HFL state
        hfl_state = await ORM.get_hfl_state_by_current_task_id(sf_task_id)
        if not hfl_state:
            logger.error(f"No HFL state found for SF task {sf_task_id}")
            return {}

        _validate_task(sf_task, hfl_state)
    except Exception as e:
        logger.error(f"Error validating task: {e}")
        return {}

    # Calculate score changes for each completion
    sf_cid_to_scores_delta = await _calc_score_deltas(sf_task)
    logger.info(f"sf cid to scores delta: {sf_cid_to_scores_delta}")

    # Get direct mapping from SF completions to the single miner response that created it
    sf_cid_to_miner_response = await _get_sf_completion_to_miner_response(sf_task)

    hotkey_to_tf_score: dict[str, float] = defaultdict(float)

    # Process each completion in the SF task
    for completion in sf_task.completions or []:
        completion_id = completion.completion_id

        # Get the specific miner response that led to this completion
        miner_response = sf_cid_to_miner_response.get(completion_id)
        if not miner_response:
            logger.debug(
                f"No miner response found for SF completion {completion_id}, this might be original response"
            )
            continue

        # Get score delta for this completion
        score_delta = sf_cid_to_scores_delta.get(completion_id, 0)

        # Award score to the specific miner who contributed to this completion
        hotkey = miner_response.hotkey
        hotkey_to_tf_score[hotkey] += score_delta
        logger.info(
            f"Miner {hotkey} feedback led to completion {completion_id} with score delta: {score_delta}"
        )

    return dict(hotkey_to_tf_score)


async def _calc_score_deltas(sf_task: ValidatorTask) -> dict[str, float]:
    """Calculate the change in scores between an SF_TASK and its parent TF_TASK.
    Or an SF_TASK and its original task.

    ┌─────────────┐       ┌──────┐       ┌──────┐      ┌──────┐     ┌──────┐
    │             │       │      │       │      │      │      │     │      │
    │Original Task│──────▶│ TF_1 │──────▶│ SF_1 │─────▶│ TF_2 │────▶│ SF_2 │
    │             │       │      │       │      │      │      │     │      │
    └─────────────┘       └──────┘       └──────┘      └──────┘     └──────┘
    """
    # Get previous task (original or parent SF)
    previous_task = await ORM.get_original_or_parent_sf_task(sf_task.id)
    if not previous_task:
        logger.error(f"Previous task not found for SF task {sf_task.id}")
        return {}

    if not previous_task.miner_responses:
        logger.error(f"Previous task {previous_task.id} has no miner responses")
        return {}

    previous_task.miner_responses = filter_valid_miner_responses(
        previous_task.miner_responses, require_scores=True, require_task_result=True
    )

    # Calculate average scores for each completion in the previous task
    prev_completion_scores = await _calc_avg_score_by_completion_id(previous_task)
    logger.info(
        f"prev completion scores for task: {previous_task.id} {prev_completion_scores}"
    )

    # Calculate average scores for each completion in the current SF task
    sf_completion_scores = await _calc_avg_score_by_completion_id(sf_task)
    logger.info(f"sf completion scores for task: {sf_task.id} {sf_completion_scores}")

    # Get HFL state to get the selected completion ID
    hfl_state = await ORM.get_hfl_state_by_current_task_id(sf_task.id)
    if not hfl_state or not hfl_state.selected_completion_id:
        logger.error(f"No selected completion ID in HFL state for task {sf_task.id}")
        return {}

    # Find the previous score based on the selected completion ID
    selected_completion_id = hfl_state.selected_completion_id
    prev_score = 0

    # Find the completion in the previous task that matches the selected ID
    for comp in previous_task.completions or []:
        if comp.completion_id == selected_completion_id:
            prev_score = prev_completion_scores.get(comp.completion_id, 0)
            logger.info(
                f"Found selected completion {selected_completion_id} with score {prev_score}"
            )
            break

    if prev_score == 0:
        logger.warning(
            f"Could not find score for selected completion {selected_completion_id}"
        )

    # Calculate deltas for each SF completion
    sf_cid_to_scores_delta = {}
    for sf_completion in sf_task.completions or []:
        sf_cid = sf_completion.completion_id

        # Skip if we don't have a score for this completion
        if sf_cid not in sf_completion_scores:
            logger.warning(f"No score found for SF completion {sf_cid}")
            continue

        # Get the SF completion's score
        sf_score = sf_completion_scores[sf_cid]

        # Calculate delta against the previous score
        delta = sf_score - prev_score
        sf_cid_to_scores_delta[sf_cid] = delta

        logger.info(
            f"Completion {sf_cid} score: {sf_score}, previous: {prev_score}, delta: {delta}"
        )

    return sf_cid_to_scores_delta


async def _get_sf_completion_to_miner_response(
    sf_task: ValidatorTask,
) -> dict[str, MinerResponse]:
    """Get mapping from SF completions to the single miner response that influenced each.

    Args:
        sf_task: SF task with completions

    Returns:
        Dictionary mapping SF completion IDs to their corresponding miner response
    """
    sf_completion_ids = [comp.completion_id for comp in sf_task.completions or []]
    if not sf_completion_ids:
        return {}

    # Find all relationships for these SF completions
    relations = await HFLCompletionRelation.prisma().find_many(
        where={"sf_completion_id": {"in": sf_completion_ids}}
    )

    # Get all miner response IDs
    miner_response_ids = [relation.miner_response_id for relation in relations]

    # Fetch all miner responses in a single query
    miner_responses = (
        await MinerResponse.prisma().find_many(where={"id": {"in": miner_response_ids}})
        if miner_response_ids
        else []
    )

    # Create a mapping from miner response ID to miner response object
    id_to_miner_response = {mr.id: mr for mr in miner_responses}

    # Create a direct one-to-one mapping
    result = {}
    for relation in relations:
        if miner_response := id_to_miner_response.get(relation.miner_response_id):
            result[relation.sf_completion_id] = miner_response

    return result


def ensure_miner_response_order(validator_task: ValidatorTask) -> ValidatorTask:
    """Ensure the ordering of the scores in miner's responses match those in validator's completions.

    This is super important to do right before any scoring functions.

    Args:
        validator_task (ValidatorTask): validator_task

    Returns:
        ValidatorTask: A copy of the original validator task with the miner
            responses' completions having the same order as the validator's
            completions.
    """
    if not validator_task.miner_responses:
        raise ValueError("Task must have miner responses for scoring")

    completion_order: dict[str, int] = {
        comp.id: idx for idx, comp in enumerate(validator_task.completions or [])
    }

    task_copy: ValidatorTask = copy.deepcopy(validator_task)

    # For each miner response, sort completions in-place based on validator_task.completions order
    for miner_response in task_copy.miner_responses or []:
        if not miner_response.scores:
            logger.debug(
                f"Miner response with hotkey: {miner_response.hotkey} has no scores"
            )
            continue

        # Sort miner scores based on order from validator's completions
        def get_order(score: MinerScore) -> int:
            if not score.criterion_relation:
                raise ValueError(
                    f"Miner score {score.id} has no criterion relation, you must fetch criterion relation"
                )

            completion_id: str = score.criterion_relation.completion_id
            if completion_id not in completion_order:
                raise ValueError(
                    f"Completion ID {completion_id} not found in task completions"
                )
            return completion_order[completion_id]

        miner_response.scores.sort(key=get_order)
    return task_copy


async def _calc_avg_score_by_completion_id(task: ValidatorTask) -> dict[str, float]:
    if not task.completions:
        raise ValueError(f"Task with id: {task.id} must have completions for scoring")
    if not task.miner_responses:
        raise ValueError(
            f"Task with id: {task.id} must have miner responses for scoring"
        )

    task = ensure_miner_response_order(task)

    # calculate the average score per completion
    # Create a dictionary to store the sum of scores and the count of scores for each completion
    stats_by_completion_id: dict[str, dict[str, float]] = {}

    cid_to_completion_id: dict[str, str] = {
        comp.id: comp.completion_id for comp in task.completions or []
    }

    for miner_response in task.miner_responses or []:
        if not miner_response.scores:
            logger.error(f"Miner response {miner_response.id} has no scores")
            continue
        try:
            for score in miner_response.scores or []:
                if not score.criterion_relation:
                    logger.error(f"Score {score.id} has no criterion relation")
                    continue

                # NOTE: cid is PK of completion, not completion_id
                cid = score.criterion_relation.completion_id
                completion_id = cid_to_completion_id[cid]
                scores = Scores.model_validate_json(score.scores)
                if completion_id not in stats_by_completion_id:
                    stats_by_completion_id[completion_id] = {"sum": 0, "count": 0}

                if not scores.raw_score:
                    logger.warning(
                        f"No raw score found miner response id: {miner_response.id} and score id: {score.id}"
                    )
                    continue

                stats_by_completion_id[completion_id]["sum"] += scores.raw_score
                stats_by_completion_id[completion_id]["count"] += 1

        except ValidationError as e:
            logger.warning(
                f"Score data validation failed for miner {miner_response.hotkey}: {e}"
            )
            continue
        except Exception as e:
            logger.error(f"Error calculating average score: {e}")
            continue

    # Calculate the average score for each completion
    cid_to_avg_score: dict[str, float] = {}
    for completion_id, scores in stats_by_completion_id.items():
        average_score = scores["sum"] / scores["count"]
        cid_to_avg_score[completion_id] = average_score
        logger.info(f"Completion {completion_id}: Average score = {average_score}")

    return cid_to_avg_score


def filter_valid_miner_responses(
    miner_responses: list[MinerResponse],
    require_scores: bool = True,
    require_task_result: bool = False,
) -> list[MinerResponse]:
    """
    Filter a list of miner responses to include only valid ones.

    Args:
        miner_responses: List of miner responses to filter
        require_scores: Whether to require scores to be present
        require_task_result: Whether to require task_result to be present
        logger: Optional logger to record filtering decisions

    Returns:
        List of valid miner responses
    """
    if not miner_responses:
        return []

    valid_responses = []

    for response in miner_responses:
        # Skip responses without hotkey
        if not response.hotkey or not response.dojo_task_id:
            continue

        # Check if scores are required and present
        if require_scores and not response.scores:
            logger.debug(
                f"Skipping miner response with hotkey: {response.hotkey} and id: {response.id}: missing scores"
            )
            continue

        # Check if task_result is required and present
        if require_task_result:
            task_result = response.task_result
            # Handle string representation of JSON
            if isinstance(task_result, str):
                try:
                    parsed_result = json.loads(task_result)
                    if not parsed_result:  # Empty dict after parsing
                        logger.debug(
                            f"Skipping miner response with hotkey: {response.hotkey} and id: {response.id}: empty task_result after parsing"
                        )
                        continue
                except json.JSONDecodeError:
                    # If it's not valid JSON but require_task_result is True, skip it
                    logger.debug(
                        f"Skipping miner response with hotkey: {response.hotkey} and id: {response.id}: invalid JSON in task_result"
                    )
                    continue
            # Handle native Python types
            elif not task_result:
                logger.debug(
                    f"Skipping miner response with hotkey: {response.hotkey} and id: {response.id}: missing task_result"
                )
                continue

        # If we get here, the response is valid
        valid_responses.append(response)

    return valid_responses
