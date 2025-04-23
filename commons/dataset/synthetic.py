import json
import os
import traceback

import aiohttp
from bittensor.utils.btlogging import logging as logger
from tenacity import (
    AsyncRetrying,
    RetryError,
    before_sleep_log,
    stop_after_attempt,
    wait_exponential,
)

from commons.api_settings import RedisSettings
from commons.cache import RedisCache
from commons.dataset.types import HumanFeedbackResponse, TextFeedbackRequest
from commons.exceptions import FatalSyntheticGenerationError, SyntheticGenerationError
from dojo.protocol import SyntheticQA
from dojo.utils.config import source_dotenv

SYNTHETIC_API_BASE_URL = os.getenv("SYNTHETIC_API_URL")
source_dotenv()
redis_config = RedisSettings()


def _map_synthetic_response(response: dict) -> SyntheticQA:
    # Create a new dictionary to store the mapped fields
    mapped_data = {
        "prompt": response["prompt"],
        "ground_truth": response["ground_truth"],
    }

    responses = list(
        map(
            lambda resp: {
                "model": resp["model"],
                "completion": resp["completion"],
                "completion_id": resp["cid"],
            },
            response["responses"],
        )
    )

    mapped_data["responses"] = responses

    return SyntheticQA.model_validate(mapped_data)


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
            cls._cache = RedisCache(redis_config)
            await cls._cache.connect()
            logger.info(f"Redis cache initialized successfully {cls._cache.redis_url}")

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

        logger.info(
            f"Sending human feedback request for {len(request_data['miner_feedbacks'])} miner feedbacks"
        )

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(6),
                wait=wait_exponential(multiplier=1, max=30),
                before_sleep=before_sleep_log(logger._logger, log_level=10),
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
            raise SyntheticGenerationError(f"Error: {str(e)}")

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
                before_sleep=before_sleep_log(
                    logger._logger, log_level=10, exc_info=True
                ),
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

                        synthetic_qa = _map_synthetic_response(response_json["body"])
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
    async def get_improved_task(cls, hf_id: str) -> HumanFeedbackResponse | None:
        """
        Retrieve human feedback data from Redis using the request ID.

        Args:
            hf_id (str): The human feedback request ID to query

        Returns:
            Optional[HumanFeedbackResponse]: The human feedback response if found, None if not found or error

        Raises:
            Exception: If there's an error accessing Redis
        """
        await cls.init_session()
        if cls._cache is None:
            raise FatalSyntheticGenerationError("Failed to initialize session")

        try:
            # The key format is "synthetic:hf:{hf_id}"
            key = f"synthetic:hf:{hf_id}"

            # Get the data from Redis
            data = await cls._cache.get(key)

            logger.info(f"Retrieved human feedback data for ID: {hf_id}, data: {data}")

            if not data:
                logger.warning(f"No human feedback data found for ID: {hf_id}")
                return None

            # Decode and parse the JSON data
            response_data = json.loads(data.decode("utf-8"))

            # Convert to HumanFeedbackResponse model
            return HumanFeedbackResponse.model_validate(response_data)

        except Exception as e:
            logger.error(f"Error retrieving human feedback for ID {hf_id}: {str(e)}")
            raise

    @classmethod
    async def get_improved_task_raw(cls, hf_id: str) -> dict | None:
        """
        Retrieve human feedback data from Redis using the request ID, returning raw dictionary.

        Unlike get_improved_task, this method returns the raw dictionary without model validation,
        preserving additional fields like 'success' and 'hf_id'.

        Args:
            hf_id (str): The human feedback request ID to query

        Returns:
            Optional[dict]: The raw dictionary response if found, None if not found

        Raises:
            Exception: If there's an error accessing Redis
        """
        await cls.init_session()
        if cls._cache is None:
            raise FatalSyntheticGenerationError("Failed to initialize session")

        try:
            # The key format is "synthetic:hf:{hf_id}"
            key = f"synthetic:hf:{hf_id}"

            # Get the data from Redis
            data = await cls._cache.get(key)

            logger.info(f"Retrieved raw human feedback data for ID: {hf_id}")

            if not data:
                logger.warning(f"No human feedback data found for ID: {hf_id}")
                return None

            # Decode and parse the JSON data (return as raw dict)
            return json.loads(data.decode("utf-8"))

        except Exception as e:
            logger.error(
                f"Error retrieving raw human feedback for ID {hf_id}: {str(e)}"
            )
            raise
