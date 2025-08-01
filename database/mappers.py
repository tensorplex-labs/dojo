import json

from database.prisma import Json
from database.prisma.enums import CriteriaTypeEnum, TaskTypeEnum
from database.prisma.models import Completion, MinerResponse, ValidatorTask
from database.prisma.types import (
    CompletionCreateInput,
    CriterionCreateWithoutRelationsInput,
    GroundTruthCreateWithoutRelationsInput,
    MinerResponseCreateInput,
    ValidatorTaskCreateInput,
)
from dojo import get_commit_hash, get_latest_git_tag
from dojo.protocol import (
    CompletionResponse,
    CriteriaType,
    Score,
    ScoreCriteria,
    SyntheticTaskSynapse,
    TextCriteria,
    TextFeedbackScore,
)
from dojo.utils import datetime_to_iso8601_str, iso8601_str_to_datetime

from .types import Metadata


# ---------------------------------------------------------------------------- #
#                 MAP PROTOCOL OBJECTS TO DATABASE MODEL INPUTS                #
# ---------------------------------------------------------------------------- #
def map_task_synapse_object_to_validator_task(
    synapse: SyntheticTaskSynapse,
    ground_truth: dict[str, int] | None = None,
    qa_metadata: dict | None = None,
) -> ValidatorTaskCreateInput:
    """Maps a SyntheticTaskSynapse to ValidatorTask database model input.

    Args:
        synapse (SyntheticTaskSynapse): The task synapse object to map
        qa_metadata (dict | None): metadata from synthetic-API QA generation.
    Returns:
        ValidatorTaskCreateInput: The database model input
    """
    # Map ground truths if present
    ground_truths = (
        [
            GroundTruthCreateWithoutRelationsInput(
                obfuscated_model_id=model_id,
                real_model_id=model_id,
                rank_id=rank_id,
                ground_truth_score=float(rank_id),  # TODO: Add normalised gt score
            )
            for model_id, rank_id in ground_truth.items()
        ]
        if ground_truth
        else []
    )
    augment_type = qa_metadata["augment_type"] if qa_metadata else ""
    metadata = Metadata(
        git_tag=get_latest_git_tag() or "",
        commit_hash=get_commit_hash(),
        augment_type=augment_type,
    )

    return ValidatorTaskCreateInput(
        id=synapse.task_id,
        previous_task_id=synapse.previous_task_id,
        prompt=synapse.prompt,
        task_type=TaskTypeEnum(synapse.task_type),
        expire_at=iso8601_str_to_datetime(synapse.expire_at),
        is_processed=False,
        miner_responses={"create": []},
        ground_truth={"create": ground_truths},
        metadata=Json(json.dumps(metadata.model_dump())),
    )


def map_task_synapse_object_to_completions(
    synapse: SyntheticTaskSynapse, validator_task_id: str
) -> list[CompletionCreateInput]:
    """Maps completion responses to database model inputs"""

    if not synapse.completion_responses:
        raise ValueError("Completion responses are required")

    # Map completions and their associated criteria
    completions: list[CompletionCreateInput] = []
    for resp in synapse.completion_responses:
        completion = CompletionCreateInput(
            completion_id=resp.completion_id,
            validator_task_id=synapse.task_id,
            model=resp.model,
            completion=Json(json.dumps(resp.completion, default=vars)),
        )

        # Add criteria for each completion if they exist
        if hasattr(resp, "criteria_types") and resp.criteria_types:
            criteria = [
                CriterionCreateWithoutRelationsInput(
                    criteria_type=_map_criteria_type_to_enum(criterion),
                    config=Json(json.dumps(_get_criteria_config(criterion))),
                )
                for criterion in resp.criteria_types
            ]
            completion["criterion"] = {"create": criteria}

        completions.append(completion)

    return completions


def _map_criteria_type_to_enum(criteria: CriteriaType) -> CriteriaTypeEnum:
    """Helper function to map CriteriaType to CriteriaTypeEnum."""
    if isinstance(criteria, ScoreCriteria):
        return CriteriaTypeEnum.SCORE
    elif isinstance(criteria, TextCriteria):
        return CriteriaTypeEnum.TEXT


def _get_criteria_config(criteria: CriteriaType) -> dict:
    """Helper function to extract configuration from criteria."""
    config = {}

    if isinstance(criteria, ScoreCriteria):
        config["min"] = criteria.min
        config["max"] = criteria.max
    elif isinstance(criteria, TextCriteria):
        config["query"] = criteria.query

    return config


def map_task_synapse_object_to_miner_response(
    synapse: SyntheticTaskSynapse,
    validator_task_id: str,
) -> MinerResponseCreateInput:
    """Maps a SyntheticTaskSynapse to MinerResponse database model input.

    Args:
        synapse (SyntheticTaskSynapse): The task synapse object to map
        validator_task_id (str): The ID of the parent validator task

    Returns:
        MinerResponseCreateInput: The database model input
    """
    if not synapse.miner_hotkey or not synapse.miner_coldkey:
        raise ValueError("Miner hotkey and coldkey are required")

    return MinerResponseCreateInput(
        validator_task_id=validator_task_id,
        hotkey=synapse.miner_hotkey,
        coldkey=synapse.miner_coldkey,
        task_result=Json(json.dumps([])),
    )


# ---------------------------------------------------------------------------- #
#               MAPPING DATABASE OBJECTS TO OUR PROTOCOL OBJECTS               #
# ---------------------------------------------------------------------------- #
def map_validator_task_to_task_synapse_object(
    model: ValidatorTask,
) -> SyntheticTaskSynapse:
    """Maps a ValidatorTask database model to SyntheticTaskSynapse.

    Args:
        model (ValidatorTask): The database model to map

    Returns:
        SyntheticTaskSynapse: The protocol object
    """
    # Map completion responses
    completion_responses = []
    for completion in model.completions or []:
        # Map criteria types for each completion
        criteria_types = []
        for criterion in completion.criterion or []:
            config = json.loads(criterion.config)
            if criterion.criteria_type == CriteriaTypeEnum.SCORE:
                criteria_types.append(
                    ScoreCriteria(
                        min=config.get("min", 0.0),
                        max=config.get("max", 0.0),
                    )
                )

        completion_responses.append(
            CompletionResponse(
                model=completion.model,
                completion=json.loads(completion.completion),
                completion_id=completion.completion_id,
                criteria_types=criteria_types,
            )
        )

    # Map ground truth if present
    ground_truth = {}
    if model.ground_truth:
        for gt in model.ground_truth:
            ground_truth[gt.obfuscated_model_id] = gt.rank_id

    # # Map miner info if present
    # miner_hotkey = None
    # miner_coldkey = None
    # dojo_task_id = None
    # if model.miner_responses and len(model.miner_responses) > 0:
    #     miner = model.miner_responses[0]  # Take first miner response
    #     miner_hotkey = miner.hotkey
    #     miner_coldkey = miner.coldkey
    #     dojo_task_id = miner.dojo_task_id

    return SyntheticTaskSynapse(
        task_id=model.id,
        previous_task_id=model.previous_task_id,
        prompt=model.prompt,
        task_type=model.task_type,
        expire_at=datetime_to_iso8601_str(model.expire_at),
        completion_responses=completion_responses,
        ground_truth=ground_truth,
        miner_hotkey=None,
        miner_coldkey=None,
    )


def map_miner_response_to_task_synapse_object(
    miner_response: MinerResponse,
    validator_task: ValidatorTask,
) -> SyntheticTaskSynapse:
    """Maps a MinerResponse database model to SyntheticTaskSynapse.

    Args:
        miner_response (MinerResponse): The miner response database model to map
        validator_task (ValidatorTask): The validator task containing completions and criteria

    Returns:
        SyntheticTaskSynapse: The protocol object
    """
    completion_responses = []
    for completion in validator_task.completions or []:
        # Map criteria types for each completion
        criteria_types = []
        score = None

        for criterion in completion.criterion or []:
            config = json.loads(criterion.config)
            # Find the corresponding score for this criterion from miner_response
            for miner_score in criterion.scores or []:
                if miner_score.miner_response_id == miner_response.id:
                    score_data = json.loads(miner_score.scores)
                    score = score_data.get("raw_score")
                    break

            if criterion.criteria_type == CriteriaTypeEnum.SCORE:
                criteria_types.append(
                    ScoreCriteria(
                        min=config.get("min", 0.0),
                        max=config.get("max", 0.0),
                    )
                )

        completion_responses.append(
            CompletionResponse(
                model=completion.model,
                completion=json.loads(completion.completion),
                completion_id=completion.completion_id,
                criteria_types=criteria_types,
                score=score,
            )
        )

    return SyntheticTaskSynapse(
        task_id=miner_response.validator_task_id,
        previous_task_id=validator_task.previous_task_id,
        prompt=validator_task.prompt,
        task_type=validator_task.task_type,
        expire_at=datetime_to_iso8601_str(validator_task.expire_at),
        completion_responses=completion_responses,
        ground_truth=None,
        miner_hotkey=miner_response.hotkey,
        miner_coldkey=miner_response.coldkey,
    )


def map_miner_response_to_completion_responses(
    miner_response: MinerResponse, completions: list[Completion]
) -> list[CompletionResponse]:
    """
    Convert a miner response and task completions to CompletionResponse objects.

    Args:
        miner_response: The miner response database model
        task_completions: The completions from the validator task

    Returns:
        List of CompletionResponse objects
    """
    completion_responses = []

    for completion in completions:
        # Map criteria types for each completion
        criteria_types = []
        for criterion in completion.criterion or []:
            config = json.loads(criterion.config)

            # Find the corresponding score for this criterion from miner_response
            miner_score = None
            for score in criterion.scores or []:
                if score.miner_response_id == miner_response.id:
                    miner_score = score
                    break

            # Create appropriate criteria type based on the database enum
            if criterion.criteria_type == CriteriaTypeEnum.SCORE:
                score_data = {}
                if miner_score:
                    score_data = (
                        json.loads(miner_score.scores)
                        if isinstance(miner_score.scores, str)
                        else miner_score.scores
                    )

                criteria_types.append(
                    ScoreCriteria(
                        min=config.get("min", 0.0),
                        max=config.get("max", 10.0),
                        scores=Score.model_validate(score_data) if score_data else None,
                    )
                )
            elif criterion.criteria_type == CriteriaTypeEnum.TEXT:
                # Extract text feedback and score from task result if available
                tf_score = None
                if miner_score:
                    tf_score = TextFeedbackScore.model_validate(
                        json.loads(miner_score.scores)
                    )
                criteria_types.append(
                    # NOTE: For simplicity, let's just return score for now
                    TextCriteria(
                        query="",
                        text_feedback="",
                        scores=tf_score,
                    )
                )

        # Create completion response with user-specific data where available
        completion_data = json.loads(completion.completion)
        completion_response = CompletionResponse(
            model=completion.model,
            completion=completion_data,
            completion_id=completion.completion_id,
            criteria_types=criteria_types,
        )

        completion_responses.append(completion_response)

    return completion_responses
