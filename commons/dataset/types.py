from typing import List

from pydantic import BaseModel

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
