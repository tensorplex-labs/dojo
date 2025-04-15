import time
import traceback

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from dojo.logging import logger
from validator_api.analytics.core.service import AnalyticsService
from validator_api.analytics.core.types import AnalyticsPayload
from validator_api.analytics.external.storage import AnalyticsStorage
from validator_api.shared.auth import ValidatorAuth

analytics_router = APIRouter()


@analytics_router.post("/api/v1/validator/analytics/tasks")
async def create_analytics_data(
    request: Request,
    data: AnalyticsPayload,
    hotkey: str = Depends(ValidatorAuth.validate_validator),
):
    start_time = time.time()
    try:
        logger.info(f"Received analytics request from hotkey {hotkey}")

        # Initialize storage
        storage = AnalyticsStorage(
            redis_cache=request.app.state.redis, aws_config=request.app.state.api_config
        )

        # Validate analytics data
        if not AnalyticsService.validate_analytics_data(data):
            logger.error(f"Invalid analytics data from hotkey {hotkey}")
            raise HTTPException(status_code=400, detail="Invalid analytics data")

        # Process and upload data
        new_tasks = []
        newly_cached_tasks = []
        try:
            # Cache new tasks
            for task in data.tasks:
                if not await storage.is_task_cached(task.validator_task_id):
                    new_tasks.append(task)
                    await storage.cache_task_id(task.validator_task_id)
                    newly_cached_tasks.append(task.validator_task_id)

            if not new_tasks:
                logger.info("No processed tasks to upload. Skipping analytics upload.")
                end_time = time.time()
                execution_time = end_time - start_time
                logger.debug(f"Request completed in {execution_time:.4f} seconds")
                result = AnalyticsService.create_success_response(
                    message="No processed tasks to upload. Skipping analytics upload.",
                    task_count=0,
                )
                return JSONResponse(
                    content=result.model_dump(mode="json"), status_code=200
                )

            # Upload to S3
            upload_success = await storage.upload_to_s3(
                AnalyticsPayload(tasks=new_tasks), hotkey
            )

            if not upload_success:
                logger.error(f"Failed to upload analytics data for hotkey {hotkey}")
                # Clean up cached tasks on failure
                for task_id in newly_cached_tasks:
                    await storage.remove_cached_task(task_id)
                raise HTTPException(
                    status_code=500, detail="Failed to upload analytics data"
                )

            logger.info(
                f"Successfully processed {len(new_tasks)} analytics tasks for hotkey {hotkey}"
            )
            end_time = time.time()
            execution_time = end_time - start_time
            logger.debug(f"Request completed in {execution_time:.4f} seconds")
            result = AnalyticsService.create_success_response(
                message=f"Successfully processed {len(new_tasks)} analytics tasks",
                task_count=len(new_tasks),
            )
            return JSONResponse(content=result.model_dump(mode="json"), status_code=200)

        except Exception:
            # Clean up newly cached tasks on any error
            for task_id in newly_cached_tasks:
                await storage.remove_cached_task(task_id)
            raise

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        logger.error(traceback.format_exc())

        # Handle both HTTPException and general exceptions
        error_message = str(e.detail) if isinstance(e, HTTPException) else str(e)
        status_code = e.status_code if isinstance(e, HTTPException) else 400

        result = AnalyticsService.create_error_response(
            message="Failed to process request",
            error=error_message,
            error_details={
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": traceback.format_exc(),
            },
        )
        return JSONResponse(
            content=result.model_dump(mode="json"), status_code=status_code
        )
