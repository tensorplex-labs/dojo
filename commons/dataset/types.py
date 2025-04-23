from typing import List

from pydantic import BaseModel, Field

from dojo.protocol import CodeAnswer


class HumanFeedbackTask(BaseModel):
    miner_hotkey: str
    miner_response_id: str
    feedback: str
    generated_code: CodeAnswer


class HumanFeedbackResponse(BaseModel):
    base_prompt: str
    base_code: str
    human_feedback_tasks: List[HumanFeedbackTask]


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
    base_code: str | dict = Field(
        description="Original completion that was selected for feedback (can be string or JSON object)"
    )
    miner_feedbacks: List[MinerFeedback] = Field(
        description="List of human feedback completions from miners"
    )
