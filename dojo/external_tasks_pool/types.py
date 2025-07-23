from pydantic import BaseModel
from typing import List, Optional, Union, Dict


class ThreeDDuelInfo(BaseModel):
    preview: str
    score: int
    source: str
    rank_before: float
    rank_after: float
    explanation: str


class ThreeDTaskMetadata(BaseModel):
    prompt: str
    left: ThreeDDuelInfo
    right: ThreeDDuelInfo


class Task(BaseModel):
    created_at: str
    updated_at: str
    id: str
    scored_status: bool
    task_metadata: ThreeDTaskMetadata
    task_type: str
