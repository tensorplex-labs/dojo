import json
from datetime import datetime, timezone

import bittensor as bt
from loguru import logger

from commons.exceptions import (
    InvalidCompletion,
    InvalidMinerResponse,
    InvalidValidatorRequest,
)
from commons.utils import (
    datetime_as_utc,
    datetime_to_iso8601_str,
    iso8601_str_to_datetime,
)
from database.prisma import Json
from database.prisma.enums import CriteriaTypeEnum
from database.prisma.models import (
    Criteria_Type_Model,
    Feedback_Request_Model,
)
from database.prisma.types import (
    Completion_Response_ModelCreateInput,
    CompletionCreateInput,
    Criteria_Type_ModelCreateInput,
    Criteria_Type_ModelCreateWithoutRelationsInput,
    CriterionCreateInput,
    Feedback_Request_ModelCreateInput,
    GroundTruthCreateInput,
    MinerResponseCreateInput,
    ValidatorTaskCreateInput,
)
from dojo.protocol import (
    CompletionResponse,
    CriteriaType,
    FeedbackRequest,
    MultiScoreCriteria,
    MultiSelectCriteria,
    RankingCriteria,
    ScoreCriteria,
    TaskSynapseObject,
)


# ---------------------------------------------------------------------------- #
#                 MAP PROTOCOL OBJECTS TO DATABASE MODEL INPUTS                #
# ---------------------------------------------------------------------------- #
def map_task_synapse_object_to_validator_task(
    synapse: TaskSynapseObject,
) -> ValidatorTaskCreateInput:
    """Maps a TaskSynapseObject to ValidatorTask database model input.

    Args:
        synapse (TaskSynapseObject): The task synapse object to map

    Returns:
        ValidatorTaskCreateInput: The database model input
    """
    # Map completions and their associated criteria
    completions = []
    for resp in synapse.completion_responses:
        completion = CompletionCreateInput(
            validator_task_id=synapse.task_id,
            model=resp.model,
            completion=Json(json.dumps(resp.completion, default=vars)),
        )

        # Add criteria for each completion if they exist
        if hasattr(resp, "criteria_types") and resp.criteria_types:
            criteria = [
                CriterionCreateInput(
                    criteria_type=_map_criteria_type_to_enum(criterion),
                    config=Json(json.dumps(_get_criteria_config(criterion))),
                )
                for criterion in resp.criteria_types
            ]
            completion.criterion = {"create": criteria}

        completions.append(completion)

    # Map ground truths if present
    ground_truths = (
        [
            GroundTruthCreateInput(
                validator_task_id=synapse.task_id,
                obfuscated_model_id=model_id,
                real_model_id=model_id,
                rank_id=rank_id,
                # ground_truth_score=float(rank_id), # TODO: Add normalised gt score
            )
            for model_id, rank_id in synapse.ground_truth.items()
        ]
        if synapse.ground_truth
        else []
    )

    return ValidatorTaskCreateInput(
        id=synapse.task_id,
        previous_task_id=synapse.previous_task_id,
        prompt=synapse.prompt,
        task_type=synapse.task_type,
        expire_at=synapse.expire_at,
        is_processed=False,
        completions={"create": completions},
        ground_truth={"create": ground_truths},
    )


def _map_criteria_type_to_enum(criteria: CriteriaType) -> CriteriaTypeEnum:
    """Helper function to map CriteriaType to CriteriaTypeEnum."""
    if isinstance(criteria, ScoreCriteria):
        return CriteriaTypeEnum.SCORE
    elif isinstance(criteria, MultiSelectCriteria):
        return CriteriaTypeEnum.MULTI_SELECT
    else:
        raise ValueError(f"Unknown criteria type: {type(criteria)}")


def _get_criteria_config(criteria: CriteriaType) -> dict:
    """Helper function to extract configuration from criteria."""
    config = {}

    if isinstance(criteria, ScoreCriteria):
        config["min"] = criteria.min
        config["max"] = criteria.max
    elif isinstance(criteria, MultiSelectCriteria):
        config["options"] = criteria.options

    return config


def map_task_synapse_object_to_miner_response(
    synapse: TaskSynapseObject,
    validator_task_id: str,
) -> MinerResponseCreateInput:
    """Maps a TaskSynapseObject to MinerResponse database model input.

    Args:
        synapse (TaskSynapseObject): The task synapse object to map
        validator_task_id (str): The ID of the parent validator task

    Returns:
        MinerResponseCreateInput: The database model input
    """
    if not synapse.miner_hotkey or not synapse.miner_coldkey:
        raise ValueError("Miner hotkey and coldkey are required")

    if not synapse.dojo_task_id:
        raise ValueError("Dojo task ID is required")

    return MinerResponseCreateInput(
        validator_task_id=validator_task_id,
        dojo_task_id=synapse.dojo_task_id,
        hotkey=synapse.miner_hotkey,
        coldkey=synapse.miner_coldkey,
    )


def map_criteria_type_to_model(
    criteria: CriteriaType, feedback_request_id: str
) -> Criteria_Type_ModelCreateWithoutRelationsInput:
    try:
        if isinstance(criteria, RankingCriteria):
            return Criteria_Type_ModelCreateInput(
                type=CriteriaTypeEnum.RANKING_CRITERIA,
                feedback_request_id=feedback_request_id,  # this is parent_id
                # options=cast(Json, json.dumps(criteria.options)),
                options=Json(json.dumps(criteria.options)),
            )
        elif isinstance(criteria, ScoreCriteria):
            return Criteria_Type_ModelCreateInput(
                type=CriteriaTypeEnum.SCORE,
                feedback_request_id=feedback_request_id,
                min=criteria.min,
                max=criteria.max,
                options=Json(json.dumps([])),
            )
        elif isinstance(criteria, MultiSelectCriteria):
            return Criteria_Type_ModelCreateInput(
                type=CriteriaTypeEnum.MULTI_SELECT,
                feedback_request_id=feedback_request_id,
                options=Json(json.dumps(criteria.options)),
            )
        elif isinstance(criteria, MultiScoreCriteria):
            return Criteria_Type_ModelCreateInput(
                type=CriteriaTypeEnum.MULTI_SCORE,
                feedback_request_id=feedback_request_id,
                options=Json(json.dumps(criteria.options)),
                min=criteria.min,
                max=criteria.max,
            )
        else:
            raise ValueError("Unknown criteria type")
    except Exception as e:
        raise ValueError(f"Failed to map criteria type to model {e}")


def map_criteria_type_model_to_criteria_type(
    model: Criteria_Type_Model,
) -> CriteriaType:
    try:
        if model.type == CriteriaTypeEnum.RANKING_CRITERIA:
            return RankingCriteria(
                options=json.loads(model.options) if model.options else []
            )
        elif model.type == CriteriaTypeEnum.SCORE:
            return ScoreCriteria(
                min=model.min if model.min is not None else 0.0,
                max=model.max if model.max is not None else 0.0,
            )
        elif model.type == CriteriaTypeEnum.MULTI_SELECT:
            return MultiSelectCriteria(
                options=json.loads(model.options) if model.options else []
            )
        elif model.type == CriteriaTypeEnum.MULTI_SCORE:
            return MultiScoreCriteria(
                options=json.loads(model.options) if model.options else [],
                min=model.min if model.min is not None else 0.0,
                max=model.max if model.max is not None else 0.0,
            )
        else:
            raise ValueError("Unknown criteria type")
    except Exception as e:
        logger.error(f"Failed to map criteria type model to criteria type: {e}")
        raise ValueError("Failed to map criteria type model to criteria type")


def map_completion_response_to_model(
    response: CompletionResponse, feedback_request_id: str
) -> Completion_Response_ModelCreateInput:
    result = Completion_Response_ModelCreateInput(
        completion_id=response.completion_id,
        model=response.model,
        completion=Json(json.dumps(response.completion, default=vars)),
        rank_id=response.rank_id,
        score=response.score,
        feedback_request_id=feedback_request_id,
    )
    return result


def map_parent_feedback_request_to_model(
    request: FeedbackRequest,
) -> Feedback_Request_ModelCreateInput:
    if not request.dendrite or not request.dendrite.hotkey:
        raise InvalidValidatorRequest("Validator Hotkey is required")

    if not request.expire_at:
        raise InvalidValidatorRequest("Expire at is required")

    expire_at = iso8601_str_to_datetime(request.expire_at)
    if expire_at < datetime.now(timezone.utc):
        raise InvalidValidatorRequest("Expire at must be in the future")

    result = Feedback_Request_ModelCreateInput(
        request_id=request.request_id,
        task_type=request.task_type,
        prompt=request.prompt,
        hotkey=request.dendrite.hotkey,
        expire_at=expire_at,
    )

    return result


def map_child_feedback_request_to_model(
    request: FeedbackRequest, parent_id: str, expire_at: datetime
) -> Feedback_Request_ModelCreateInput:
    if not request.axon or not request.axon.hotkey:
        raise InvalidMinerResponse("Miner Hotkey is required")

    if not parent_id:
        raise InvalidMinerResponse("Parent ID is required")

    if not request.dojo_task_id:
        raise InvalidMinerResponse("Dojo Task ID is required")

    result = Feedback_Request_ModelCreateInput(
        request_id=request.request_id,
        task_type=request.task_type,
        prompt=request.prompt,
        hotkey=request.axon.hotkey,
        expire_at=datetime_as_utc(expire_at),
        dojo_task_id=request.dojo_task_id,
        parent_id=parent_id,
    )

    return result


# ---------------------------------------------------------------------------- #
#               MAPPING DATABASE OBJECTS TO OUR PROTOCOL OBJECTS               #
# ---------------------------------------------------------------------------- #


def map_feedback_request_model_to_feedback_request(
    model: Feedback_Request_Model, is_miner: bool = False
) -> FeedbackRequest:
    """Smaller function to map Feedback_Request_Model to FeedbackRequest, meant to be used when reading from database.

    Args:
        model (Feedback_Request_Model): Feedback_Request_Model from database.
        is_miner (bool, optional): If we're converting for a validator request or miner response.
        Defaults to False.

    Raises:
        ValueError: If failed to map.

    Returns:
        FeedbackRequest: FeedbackRequest object.
    """

    try:
        # Map criteria types
        criteria_types = [
            map_criteria_type_model_to_criteria_type(criteria)
            for criteria in model.criteria_types or []
        ]

        # Map completion responses
        if not model.completions:
            raise InvalidCompletion("No completion responses found to map")

        completion_responses = [
            CompletionResponse(
                completion_id=completion.completion_id,
                model=completion.model,
                completion=json.loads(completion.completion),
                rank_id=completion.rank_id,
                score=completion.score,
            )
            for completion in model.completions
        ]

        ground_truth: dict[str, int] = {}

        if model.ground_truths:
            for gt in model.ground_truths:
                ground_truth[gt.obfuscated_model_id] = gt.rank_id

        if is_miner:
            # Create FeedbackRequest object
            feedback_request = FeedbackRequest(
                request_id=model.request_id,
                prompt=model.prompt,
                task_type=model.task_type,
                criteria_types=criteria_types,
                completion_responses=completion_responses,
                dojo_task_id=model.dojo_task_id,
                expire_at=datetime_to_iso8601_str(model.expire_at),
                axon=bt.TerminalInfo(hotkey=model.hotkey),
            )
        else:
            feedback_request = FeedbackRequest(
                request_id=model.request_id,
                prompt=model.prompt,
                task_type=model.task_type,
                criteria_types=criteria_types,
                completion_responses=completion_responses,
                dojo_task_id=model.dojo_task_id,
                expire_at=datetime_to_iso8601_str(model.expire_at),
                dendrite=bt.TerminalInfo(hotkey=model.hotkey),
                ground_truth=ground_truth,
            )

        return feedback_request
    except Exception as e:
        raise ValueError(
            f"Failed to map Feedback_Request_Model to FeedbackRequest: {e}"
        )
