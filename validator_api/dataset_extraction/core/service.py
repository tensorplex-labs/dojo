from datetime import datetime, timezone
from typing import List

from fastapi import UploadFile

from dojo.logging import logger

from .types import DatasetExtractionResponse, DatasetUploadResult


class DatasetExtractionService:
    @staticmethod
    def validate_file_size(file: UploadFile, max_size_mb: int) -> bool:
        try:
            file_size = len(file.file.read())
            file.file.seek(0)  # Reset file pointer
            return file_size <= max_size_mb * 1024 * 1024
        except Exception as e:
            logger.error(f"Error validating file size: {str(e)}")
            return False

    @staticmethod
    def create_upload_result(
        success: bool, message: str, filenames: List[str], total_size: int
    ) -> DatasetUploadResult:
        return DatasetUploadResult(
            success=success,
            message=message,
            timestamp=datetime.now(timezone.utc),
            filenames=filenames,
            total_size=total_size,
        )

    @staticmethod
    def validate_extractor_credentials(
        hotkey: str, signature: str, message: str
    ) -> bool:
        if not signature.startswith("0x"):
            logger.error("Invalid signature format")
            return False
        return True

    @staticmethod
    def create_extraction_response(
        message: str,
        total_records: int,
        saved_records: int,
        warnings: List[str],
    ) -> DatasetExtractionResponse:
        return DatasetExtractionResponse(
            success=True,
            message=message,
            timestamp=datetime.now(timezone.utc),
            total_records=total_records,
            saved_records=saved_records,
            warnings=warnings,
        )
