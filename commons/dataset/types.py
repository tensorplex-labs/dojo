from typing import List

from pydantic import BaseModel, Field, model_validator

from commons.utils import get_new_uuid
from dojo.protocol import CodeAnswer


class HumanFeedbackTask(BaseModel):
    miner_hotkey: str
    miner_response_id: str
    feedback: str
    model: str
    completion_id: str = Field(
        description="ID of the completion", default_factory=get_new_uuid
    )
    generated_code: CodeAnswer

    @model_validator(mode="before")
    @classmethod
    def add_completion_id(cls, data):
        if isinstance(data, dict):
            # Add completion_id if not present (API doesn't send this)
            if "completion_id" not in data:
                data["completion_id"] = get_new_uuid()
        return data


class HumanFeedbackResponse(BaseModel):
    base_prompt: str
    base_code: CodeAnswer
    human_feedback_tasks: List[HumanFeedbackTask]

    @model_validator(mode="before")
    @classmethod
    def transform_from_api(cls, data):
        if isinstance(data, dict):
            # Remove API-only fields
            data.pop("hf_id", None)
            data.pop("success", None)

            # Convert JSON string to CodeAnswer
        if "base_code" in data:
            data["base_code"] = CodeAnswer.model_validate_json(data["base_code"])

        return data


class MinerFeedback(BaseModel):
    """
    Represents a single text feedback response from a miner.
    """

    hotkey: str = Field(description="Hotkey of the miner providing the feedback")
    miner_response_id: str = Field(
        description="ID of the miner response in the database"
    )
    feedback: str = Field(description="Feedback provided by the miner")


class TextFeedbackRequest(BaseModel):
    """
    Represents a request to the synthetic API with text feedback data.
    Used to generate improved responses based on human feedback.
    """

    base_prompt: str = Field(description="Original prompt that was given to the LLM")
    base_code: CodeAnswer = Field(description="Completion from the model")
    miner_feedbacks: List[MinerFeedback] = Field(
        description="List of human feedback completions from miners"
    )
