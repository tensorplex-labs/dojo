import time
import traceback

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from dojo.logging import logging as logger
from validator_api.shared.auth import ValidatorAuth
from validator_api.validator_logging.core.service import LoggingService
from validator_api.validator_logging.core.types import LogBatch
from validator_api.validator_logging.external.storage import LogStorage

logging_router = APIRouter(tags=["logging"])


@logging_router.post("/api/v1/validator/logging")
async def send_logs_to_loki(
    request: Request,
    log_batch: LogBatch,
    hotkey: str = Depends(ValidatorAuth.validate_validator),
):
    start_time = time.time()
    try:
        logger.info(f"Received logging request from hotkey {hotkey}")

        # Initialize storage
        storage = LogStorage(config=request.app.state.api_config)

        # Validate log entries
        if not LoggingService.validate_log_entries(log_batch.logs):
            logger.error(f"Invalid log data from hotkey {hotkey}")
            raise HTTPException(status_code=400, detail="Invalid log data")

        # Send logs to Loki
        success = await storage.send_to_loki(log_batch.logs, hotkey)

        if success:
            logger.debug(
                f"Successfully sent {len(log_batch.logs)} logs to Loki from validator {hotkey}"
            )
            end_time = time.time()
            execution_time = end_time - start_time
            logger.debug(f"Request completed in {execution_time:.4f} seconds")

            result = LoggingService.create_success_response(
                message=f"Sent {len(log_batch.logs)} logs to Loki",
                validator=hotkey,
                log_count=len(log_batch.logs),
            )
            return JSONResponse(content=result.model_dump(), status_code=200)
        else:
            logger.error(f"Failed to send logs to Loki for validator {hotkey}")
            raise HTTPException(status_code=500, detail="Failed to send logs to Loki")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        logger.error(traceback.format_exc())

        # Handle general exceptions
        error_message = str(e)

        result = LoggingService.create_error_response(
            message="Failed to process request",
            validator=log_batch.hotkey,
            error=error_message,
            error_details={
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": traceback.format_exc(),
            },
        )
        return JSONResponse(content=result.model_dump(), status_code=400)
