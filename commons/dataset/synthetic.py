import json
import os
import traceback

import aiohttp
from loguru import logger
from tenacity import (
    AsyncRetrying,
    RetryError,
    stop_after_attempt,
    wait_exponential,
)

from commons.api_settings import RedisSettings
from commons.cache import RedisCache
from commons.dataset.types import HumanFeedbackResponse, TextFeedbackRequest
from commons.dataset.utils import map_human_feedback_response, map_synthetic_response
from commons.exceptions import (
    FatalSyntheticGenerationError,
    FeedbackImprovementError,
    SyntheticGenerationError,
)
from dojo.protocol import SyntheticQA
from dojo.utils import retry_log
from dojo.utils.config import source_dotenv

SYNTHETIC_API_BASE_URL = os.getenv("SYNTHETIC_API_URL")
source_dotenv()
redis_config = RedisSettings()


class SyntheticAPI:
    _session: aiohttp.ClientSession | None = None
    _cache: RedisCache | None = None

    @classmethod
    async def init_session(cls):
        if cls._session is None:
            cls._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=120)
            )
        if cls._cache is None:
            cls._cache = RedisCache(redis_config, is_ssl=False)
            await cls._cache.connect()

    @classmethod
    async def close_session(cls):
        if cls._session is not None:
            await cls._session.close()
            cls._session = None

        if cls._cache is not None:
            await cls._cache.close()
        logger.debug("Ensured SyntheticAPI session is closed.")

    @classmethod
    async def send_text_feedback(
        cls, text_feedback_data: TextFeedbackRequest
    ) -> str | None:
        """
        Send text feedback data to the synthetic API for improvement.

        Args:
            text_feedback_data (TextFeedbackRequest): Contains prompt, base_completion, and miner_feedbacks
                with feedback responses from miners

        Returns:
            str: A synthetic request ID for tracking the improvement request

        Raises:
            SyntheticGenerationError: If the API request fails or returns an error
            ValueError: If the response format is invalid
        """
        await cls.init_session()
        if cls._session is None:
            raise FatalSyntheticGenerationError("Failed to initialize session")

        path = f"{SYNTHETIC_API_BASE_URL}/api/human-feedback"
        request_data = text_feedback_data.model_dump(mode="json")

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(6),
                wait=wait_exponential(multiplier=1, max=30),
                before_sleep=retry_log,
            ):
                with attempt:
                    async with cls._session.post(path, json=request_data) as response:
                        response.raise_for_status()
                        response_json = await response.json()

                        if not response_json.get("success", True):
                            error_msg = response_json.get(
                                "error", "No error details provided"
                            )
                            logger.error(f"API returned error: {error_msg}")
                            raise SyntheticGenerationError(error_msg)

                        if "human_feedback_id" not in response_json:
                            logger.error("Response missing human_feedback_id field")
                            raise ValueError("Missing human_feedback_id field")

                        logger.info(
                            f"Successfully created human feedback request with ID: {response_json['human_feedback_id']}"
                        )
                        return response_json["human_feedback_id"]

        except RetryError as e:
            logger.error(f"Failed after all retry attempts: {str(e)}")
            raise FatalSyntheticGenerationError(
                f"Failed after all retry attempts: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Error sending human feedback request: {str(e)}")
            raise

    @classmethod
    async def get_qa(cls) -> SyntheticQA | None:
        await cls.init_session()
        if cls._session is None:
            raise FatalSyntheticGenerationError("Failed to initialize session")

        path = f"{SYNTHETIC_API_BASE_URL}/api/synthetic-gen"
        logger.debug(f"Generating synthetic QA from {path}.")

        MAX_RETRIES = 6

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(MAX_RETRIES),
                wait=wait_exponential(multiplier=1, max=30),
                before_sleep=retry_log,
            ):
                with attempt:
                    async with cls._session.get(path) as response:
                        response.raise_for_status()
                        response_json = await response.json()
                        if response_json["success"] is False:
                            raise SyntheticGenerationError(
                                message=response_json.get(
                                    "error", "No error details provided"
                                ),
                            )
                        if "body" not in response_json:
                            raise SyntheticGenerationError(
                                "Invalid response from the server. "
                                "No body found in the response."
                            )

                        synthetic_qa = map_synthetic_response(response_json["body"])
                        logger.success("Synthetic QA generated and parsed successfully")
                        return synthetic_qa
        except RetryError:
            logger.error(
                f"Failed to generate synthetic QA after {MAX_RETRIES} retries."
            )
            traceback.print_exc()
            raise FatalSyntheticGenerationError(
                "QA generation failed after all retry attempts"
            )

        except Exception:
            raise

    @classmethod
    async def get_improved_task(
        cls, hf_id: str
    ) -> tuple[bool, HumanFeedbackResponse | None]:
        """
        Retrieve human feedback data from Redis and map to HumanFeedbackResponse.

        Args:
            hf_id (str): The human feedback request ID to query

        Returns:
            tuple[bool, HumanFeedbackResponse | None]: A tuple containing:
                - success: True if request was acknowledged, False if API explicitly failed
                - The human feedback response if available, None if not ready yet

        Raises:
            Various exceptions for network, validation, or internal errors
        """
        await cls.init_session()
        if cls._cache is None:
            raise FeedbackImprovementError("Redis cache not initialized")

        # The key format is "synthetic:hf:{hf_id}"
        key = f"synthetic:hf:{hf_id}"

        # Get the data from Redis
        data = await cls._cache.get(key)

        # No data yet - task is still being processed
        if not data:
            logger.info(f"Task improvement not found in Redis: {hf_id}")
            return True, None  # Success=True but data=None means "still processing"

        # Decode and parse the JSON data
        raw_response = json.loads(data.decode("utf-8"))

        # Check if success flag is explicitly False - API reported failure
        if raw_response.get("success") is False:
            error_message = raw_response.get("message", "Unknown error")
            logger.error(f"Error in synthetic API response: {error_message}")
            return False, None  # Explicit failure from API

        # Map and return the response if available
        response_obj = map_human_feedback_response(raw_response)
        logger.info(f"Successfully retrieved improved task for ID: {hf_id}")
        return True, response_obj  # Success with data
