from datetime import datetime, timezone
from typing import List

from pydantic import BaseModel, ConfigDict, Field, model_validator
from strenum import StrEnum

from commons.utils import get_epoch_time, get_new_uuid


class SanitizedResultEnum(StrEnum):
    INVALID = "invalid"
    VALID = "valid"


class TaskTypeEnum(StrEnum):
    TEXT_TO_THREE_D = "TEXT_TO_THREE_D"
    TEXT_TO_IMAGE = "TEXT_TO_IMAGE"
    CODE_GENERATION = "CODE_GENERATION"
    TEXT_FEEDBACK = "TEXT_FEEDBACK"
    SCORE_FEEDBACK = "SCORE_FEEDBACK"


class CriteriaTypeEnum(StrEnum):
    SCORE = "score"
    TEXT = "text"


class Scores(BaseModel):
    raw_score: float | None = Field(description="Raw score of the miner", default=None)
    rank_id: int | None = Field(description="Rank of the miner", default=None)
    normalised_score: float | None = Field(
        description="Normalised score of the miner", default=None
    )
    ground_truth_score: float | None = Field(
        description="Ground truth score of the miner", default=None
    )
    cosine_similarity_score: float | None = Field(
        description="Cosine similarity score of the miner", default=None
    )
    normalised_cosine_similarity_score: float | None = Field(
        description="Normalised cosine similarity score of the miner", default=None
    )
    cubic_reward_score: float | None = Field(
        description="Cubic reward score of the miner", default=None
    )
    icc_score: float | None = Field(description="ICC score of the miner", default=None)


class TextFeedbackScore(BaseModel):
    tf_score: float | None = Field(description="Score of the completion", default=None)
    text_feedback: str | None = Field(
        description="Text feedback of the completion", default=None
    )


class ScoreCriteria(BaseModel):
    model_config = ConfigDict(frozen=False)

    type: str = Field(default=CriteriaTypeEnum.SCORE.value, frozen=True)
    min: float = Field(description="Minimum score for the task", frozen=True)
    max: float = Field(description="Maximum score for the task", frozen=True)
    scores: Scores | None = Field(description="Scores of the completion", default=None)


class TextCriteria(BaseModel):
    type: str = Field(default=CriteriaTypeEnum.TEXT.value, frozen=True)
    query: str = Field(description="Query for the task", frozen=True)
    text_feedback: str = Field(description="Text feedback for the task", frozen=True)
    score: TextFeedbackScore | None = Field(
        description="Text feedback score for the task", default=None
    )


CriteriaType = ScoreCriteria | TextCriteria


class CodeFileObject(BaseModel):
    filename: str = Field(description="Name of the file")
    content: str = Field(description="Content of the file which can be code or json")


class CodeAnswer(BaseModel):
    files: List[CodeFileObject] = Field(description="List of FileObjects")


class CompletionResponse(BaseModel):
    model: str = Field(description="Model that generated the completion")
    completion: CodeAnswer | None = Field(description="Completion from the model")
    completion_id: str = Field(description="Unique identifier for the completion")
    # TODO: Check if rank_id is needed
    rank_id: int | None = Field(
        description="Rank of the completion", examples=[1, 2, 3, 4], default=None
    )
    score: float | None = Field(description="Score of the completion", default=None)
    criteria_types: List[CriteriaType] = Field(
        description="Types of criteria for the task", default_factory=list
    )


class SyntheticQA(BaseModel):
    prompt: str
    responses: List[CompletionResponse]
    ground_truth: dict[str, int] = Field(
        description="Mapping of unique identifiers to their ground truth values",
        default_factory=dict,
    )
    metadata: dict = Field(description="Metadata of the task", default_factory=dict)

    @model_validator(mode="after")
    def verify_completion_ids(self):
        completion_ids = {resp.completion_id for resp in self.responses}
        ground_truth_keys = set(self.ground_truth.keys())

        if not completion_ids.issubset(ground_truth_keys):
            missing_ids = completion_ids - ground_truth_keys
            raise ValueError(
                f"The following completion_ids are missing from ground_truth: {missing_ids}"
            )

        if not ground_truth_keys.issubset(completion_ids):
            extra_keys = ground_truth_keys - completion_ids
            raise ValueError(
                f"The following keys in ground_truth do not correspond to any completion_id: {extra_keys}"
            )

        return self


class SyntheticTaskSynapse(BaseModel):
    ack: bool = Field(description="Acknowledgement of the synapse", default=False)
    epoch_timestamp: float = Field(
        default_factory=get_epoch_time,
        description="Epoch timestamp for the task",
    )
    task_id: str = Field(
        default_factory=get_new_uuid,
        description="Unique identifier for the task",
    )
    previous_task_id: str | None = Field(
        description="ID of the previous task", default=None
    )
    prompt: str = Field(
        description="Prompt or query from the user sent to the LLM",
    )
    task_type: str = Field(description="Type of task")
    expire_at: str = Field(
        description="Expired time for task which will be used by miner to create dojo task"
    )
    completion_responses: List[CompletionResponse] | None = Field(
        description="List of completions for the task",
        default=None,
    )
    ground_truth: dict[str, int] | None = Field(
        description="Mapping of unique identifiers to their ground truth values",
        default=None,
    )
    miner_hotkey: str | None = Field(
        description="Hotkey of the miner that created the task", default=None
    )
    miner_coldkey: str | None = Field(
        description="Coldkey of the miner that created the task", default=None
    )


class ScoreResultSynapse(BaseModel):
    validator_task_id: str = Field(
        description="Unique identifier for the request",
    )
    scores: Scores = Field(description="Scores object for a miner for that task id")


class Heartbeat(BaseModel):
    ack: bool = Field(description="Acknowledgement of the heartbeat", default=False)


# TODO rename this to be a Task or something
class DendriteQueryResponse(BaseModel):
    model_config = ConfigDict(frozen=False)
    validator_task: SyntheticTaskSynapse
    miner_responses: List[SyntheticTaskSynapse]


class Result(BaseModel):
    model: str = Field(description="Model that generated the result")
    criteria: list[dict] = Field(description="List of criteria with scores")


class TaskResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(description="Task ID")
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")
    status: str = Field(description="Status of the task result")
    result_data: list[Result] = Field(description="List of Result data for the task")
    task_id: str = Field(description="ID of the associated dojo task")
    worker_id: str = Field(description="ID of the worker who completed the task")


class TaskResultSynapse(BaseModel):
    validator_task_id: str = Field(
        description="The ID of the task to retrieve results for"
    )
    task_results: list[TaskResult] = Field(
        description="List of TaskResult objects", default=[]
    )


class AnalyticsData(BaseModel):
    """
    defines the structure for analytics data that will be sent by validators to the analytics endpoint.
    """

    validator_task_id: str
    task_type: str
    previous_task_id: str | None = Field(
        description="ID of the previous task", default=None
    )
    next_task_id: str | None = Field(description="ID of the next task", default=None)
    validator_hotkey: str
    prompt: str
    completions: List[dict]
    ground_truths: List[dict]
    scored_hotkeys: List[str]
    absent_hotkeys: List[str]
    miner_responses: List[dict]  # contains responses from all miners.
    created_at: str
    updated_at: str
    metadata: dict | None


class AnalyticsPayload(BaseModel):
    tasks: List[AnalyticsData]


class HFLEvent(BaseModel):
    type: str = Field(description="Type of the event")
    task_id: str = Field(description="ID of the task")
    syn_req_id: str = Field(description="ID of the synthetic request", default="")
    iteration: int = Field(description="Iteration of the event", default=0)
    message: str = Field(description="Message of the event", default="")
    timestamp: datetime = Field(
        description="Timestamp of the event",
        default_factory=lambda: datetime.now(timezone.utc),
    )


# TODO: Add more data as needed
class TextFeedbackEvent(HFLEvent):
    type: str = Field(description="Type of the event", default="TEXT_FEEDBACK")


# TODO: Add more data as needed
class ScoreFeedbackEvent(HFLEvent):
    type: str = Field(description="Type of the event", default="SCORE_FEEDBACK")
