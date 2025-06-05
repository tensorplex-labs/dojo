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


class HumanFeedbackResponse(BaseModel):
    base_prompt: str
    base_code: CodeAnswer
    human_feedback_tasks: List[HumanFeedbackTask]

    @model_validator(mode="after")
    def verify_code_objects(self):
        # Verify base_code is a CodeAnswer instance
        if not isinstance(self.base_code, CodeAnswer):
            raise ValueError(
                f"base_code must be a CodeAnswer or MultimedeaAnswer instance, got {type(self.base_code)}"
            )

        # Verify all generated_code fields are CodeAnswer instances
        for idx, task in enumerate(self.human_feedback_tasks):
            if not isinstance(task.generated_code, CodeAnswer):
                raise ValueError(
                    f"generated_code in task {idx} must be a CodeAnswer or MultimediaAnswer instance, "
                    f"got {type(task.generated_code)}"
                )

        return self


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
