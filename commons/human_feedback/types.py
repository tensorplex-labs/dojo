"""Type definitions for Human Feedback Loop functionality."""

from dataclasses import dataclass, field
from typing import List

from database.prisma.enums import HFLStatusEnum
from database.prisma.models import MinerResponse


@dataclass
class FeedbackTaskResult:
    """Results of a feedback task processing operation."""

    task_id: str
    status: HFLStatusEnum
    selected_responses: List[MinerResponse] = field(default_factory=list)
    error: str | None = None


@dataclass
class HFLMetrics:
    """Metrics tracked for Human Feedback Loop performance."""

    total_tasks_processed: int = 0
    successful_improvements: int = 0
    failed_improvements: int = 0
    avg_feedback_quality: float = 0.0
    avg_response_time: float = 0.0
