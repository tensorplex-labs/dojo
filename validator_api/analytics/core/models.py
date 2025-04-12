from datetime import datetime
from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict


class AnalyticsData(BaseModel):
    validator_task_id: str
    validator_hotkey: str
    prompt: str
    completions: List[Dict[str, Any]]
    ground_truths: List[Dict[str, Any]]
    miner_responses: List[Dict[str, Any]]
    scored_hotkeys: List[str]
    absent_hotkeys: List[str]
    created_at: str
    updated_at: str
    metadata: Dict[str, Any] | None = None


class AnalyticsPayload(BaseModel):
    tasks: List[AnalyticsData]


class ErrorDetails(BaseModel):
    error_type: str
    error_message: str
    traceback: str


class AnalyticsSuccessResponse(BaseModel):
    model_config = ConfigDict(json_encoders={datetime: lambda dt: dt.isoformat()})
    success: bool = True
    message: str
    timestamp: datetime
    task_count: int


class AnalyticsErrorResponse(BaseModel):
    model_config = ConfigDict(json_encoders={datetime: lambda dt: dt.isoformat()})
    success: bool = False
    message: str
    timestamp: datetime
    error: str
    details: ErrorDetails
