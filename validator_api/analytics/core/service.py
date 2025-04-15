from datetime import datetime, timezone
from typing import Any, Dict

from dojo.logging import logger

from .types import (
    AnalyticsErrorResponse,
    AnalyticsPayload,
    AnalyticsSuccessResponse,
    ErrorDetails,
)


class AnalyticsService:
    @staticmethod
    def validate_analytics_data(data: AnalyticsPayload) -> bool:
        if not data.tasks:
            logger.error("No analytics data to validate")
            return False

        for task in data.tasks:
            if not task.validator_hotkey or not task.validator_task_id:
                logger.error("Invalid task data: missing required fields")
                return False

        return True

    @staticmethod
    def create_success_response(
        message: str, task_count: int
    ) -> AnalyticsSuccessResponse:
        return AnalyticsSuccessResponse(
            message=message, timestamp=datetime.now(timezone.utc), task_count=task_count
        )

    @staticmethod
    def create_error_response(
        message: str, error: str, error_details: Dict[str, Any]
    ) -> AnalyticsErrorResponse:
        return AnalyticsErrorResponse(
            message=message,
            timestamp=datetime.now(timezone.utc),
            error=error,
            details=ErrorDetails(**error_details),
        )
