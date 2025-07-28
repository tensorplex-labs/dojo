from pydantic import BaseModel
from typing import Dict


class ThreeDDuelInfo(BaseModel):
    preview: str
    score: int
    source: str
    rank_before: float
    rank_after: float


class ThreeDTaskMetadata(BaseModel):
    prompt: str
    left: ThreeDDuelInfo
    right: ThreeDDuelInfo
    explanation: str
    ground_truth: Dict[str, int]


class Task(BaseModel):
    created_at: str
    updated_at: str
    id: str
    scored_status: bool
    task_metadata: ThreeDTaskMetadata
    task_type: str
    sent_status: bool = False  # Default to False if not provided
