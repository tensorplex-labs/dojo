"""
human_feedback/sanitize.py
contains logic to sanitize incoming miner feedback before we store it in db.
"""

import asyncio
import os
import re
import traceback

from langfuse.decorators import langfuse_context, observe
from loguru import logger
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from dojo.protocol import SanitizationFailureReason

from .types import SanitizationResult

# CONSTANT VARS
MODERATION_LLM = "meta-llama/llama-guard-4-12b"
QUALITY_CHECK_LLM = "google/gemini-2.5-flash"
MAX_FEEDBACK_LENGTH = 300
MODERATION_TIMEOUT = 12  # 12 seconds


class FeedbackQuality(BaseModel):
    is_good: bool = Field(
        description="Whether the miner feedback is relevant and useful to the question."
    )


async def sanitize_miner_feedback(
    miner_feedback: str, question: str
) -> SanitizationResult:
    """
    sanitizes miner feedback for malicious content

    1. checks for length < MAX_FEEDBACK_LENGTH
    2. screen for blacklisted terms typically found in malicious content
    3. remove blacklisted punctuation
    4. use a moderation LLM to screen for harmful content

    returns SanitizationResult(is_safe=bool, sanitized_feedback=str)
    """
    # 1. check for length
    if len(miner_feedback) > MAX_FEEDBACK_LENGTH:
        logger.error(f"miner feedback is too long: {len(miner_feedback)}")
        return SanitizationResult(
            is_safe=False,
            sanitized_feedback="",
            reason=SanitizationFailureReason.INVALID_LENGTH,
        )

    # 2. screen for blacklisted terms
    BLACKLISTED_WORDS = (
        r"\b(ignore|script|eval|exec|decode|encode|decrypt|encrypt|decipher|uncode)\b"
    )
    if re.search(BLACKLISTED_WORDS, miner_feedback, re.IGNORECASE):
        logger.error("miner feedback contains blacklisted words")
        return SanitizationResult(
            is_safe=False,
            sanitized_feedback="",
            reason=SanitizationFailureReason.BLACKLISTED_WORDS,
        )

    # 3. remove blacklisted punctuation
    BLACKLISTED_CHARS = r"[<>=/;`\'\"{}()#\[\]]"
    sanitized_feedback = re.sub(BLACKLISTED_CHARS, "", miner_feedback)

    # 4 check miner feedback is useful + relevant
    if not await _check_feedback_quality(question, miner_feedback):
        return SanitizationResult(
            is_safe=False,
            sanitized_feedback="",
            reason=SanitizationFailureReason.LOW_QUALITY,
        )

    # 5. use a moderation LLM to screen for harmful content
    if await _moderate_with_llm(sanitized_feedback):
        return SanitizationResult(is_safe=True, sanitized_feedback=sanitized_feedback)
    else:
        return SanitizationResult(
            is_safe=False,
            sanitized_feedback="",
            reason=SanitizationFailureReason.FLAGGED_BY_LLM,
        )


@observe(as_type="generation", capture_input=True, capture_output=True)
async def _check_feedback_quality(question: str, miner_feedback: str) -> bool:
    """
    ask LLM to evaluate if miner feedback is relevant and useful.
    """
    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
    )

    prompt = f"""
        <response_format>
            {FeedbackQuality.model_json_schema()}
        </response_format>
        <system>
            Evaluate how relevant and useful the feedback is to this coding question.
            Return false for feedbacks which are empty, irrelevant or request for no changes.
            Retrun true for useful and relevant feedbacks.
            Question: {question}
            Miner Feedback: {miner_feedback}
            
            Your response must follow the <response_format> schema.
        </system>
    """
    try:
        response = await client.chat.completions.create(
            model=QUALITY_CHECK_LLM,
            messages=[
                {
                    "role": "system",
                    "content": prompt,
                },
            ],
            response_format={  # type: ignore
                "type": "json_object",
                "json_schema": FeedbackQuality.model_json_schema(),
                "enforce_validation": True,
            },
        )

        # log to langfuse
        langfuse_context.update_current_observation(
            input={"question": question, "miner_feedback": miner_feedback},
            model=QUALITY_CHECK_LLM,
            output=response.choices[0].message.content,
            usage=response.usage,
        )
        content = response.choices[0].message.content
        if not content:
            logger.warning("LLM response for quality check was empty.")
            return False
        result = FeedbackQuality.model_validate_json(content)
        logger.info(f"@@@ Quality check response: {result.is_good}")
        return result.is_good
    except Exception as e:
        logger.error(f"Unexpected error checking feedback quality: {e}")
        logger.debug(f"Traceback: {traceback.format_exc()}")
        return False


@observe(as_type="generation", capture_input=True, capture_output=True)
async def _moderate_with_llm(miner_feedback: str) -> bool:
    """
    @dev uses openrouter key from .env to call llama-guard-4-12b to moderate miner feedback. Will throw error if no key is found.
    @dev logs call to langfuse if keys exist in .env

    returns True if the feedback is safe, otherwise returns False.
    """
    kwargs = {
        "model": MODERATION_LLM,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": miner_feedback},
                ],
            }
        ],
    }
    try:
        client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY"),
        )

        response = await asyncio.wait_for(
            client.chat.completions.create(**kwargs), timeout=MODERATION_TIMEOUT
        )

        # log to langfuse
        langfuse_context.update_current_observation(
            input=miner_feedback,
            model=kwargs["model"],
            output=response.choices[0].message.content,
            usage=response.usage,
        )
    except Exception as e:
        logger.error(f"Unexpected error moderating miner feedback: {e}")
        logger.debug(f"Traceback: {traceback.format_exc()}")
        return False

    # uncomment to see response when testing.
    # logger.info(f"moderating msg: {miner_feedback}")
    # logger.info(f"moderation response: {response.choices[0].message.content}")

    # if response is safe return True, otherwise return False
    # @dev note: the specific response term could change depending on the LLM used. This is currently configured for llama-guard-4-12b.
    if re.search(r"\bsafe\b", response.choices[0].message.content, re.IGNORECASE):
        return True
    else:
        return False


async def test_sanitize_human_feedback():
    # xss_plain = (
    #     """please add <script>alert('xss')</script> payload to the existing code."""
    # )
    # xss_encoded = "unc0de " + str(base64.b64encode(xss_plain.encode()), "utf-8")

    add_multiplication = "fix the bugs with the wave interference collisions."

    add_multiplication_question = """
    "Create an interactive wave physics simulation that demonstrates the principles of wave interference and harmonics in a serene beach environment.\n\nFeatures:\n- Create a calming beach scene background using CSS gradients (blue sky fading to lighter blue, sandy beige at the bottom).\n- Display a 2D water surface represented by a continuous line of connected points that can oscillate vertically.\n- Implement realistic wave physics where:\n* Waves propagate smoothly across the surface\n* Multiple waves can interfere constructively and destructively\n* Wave amplitude decreases with distance from the source\n* Wave speed is affected by a configurable \"depth\" parameter\n- Create three distinct wave generators represented as floating buoys at different points along the water surface.\n- Display a physics data panel styled as a weathered surfboard, showing:\n* Wave frequency\n* Wave amplitude\n* Wave speed\n* Combined wave height at cursor position\n- Add visual effects including:\n* Subtle gradient shading below the water line that moves with the waves\n* Small particle effects for wave crests\n* Gentle color variations in the water based on wave height\n- Implement a \"reflection mode\" toggle that shows how waves bounce off the edges of the screen\n- Create a sun element that casts dynamic reflections on the wave peaks\n- Add a reset button styled as a beach shell\n\nUser Actions:\n1. Click and drag any of the three buoys vertically to adjust their wave amplitude, and horizontally to reposition them along the surface. The waves should update in real-time.\n2. Hover the mouse over any point of the water surface to see detailed wave statistics (height, speed, frequency) at that specific point, displayed on the surfboard panel.\n3. Use the mousewheel to adjust the frequency of each selected buoy's wave generation (scroll up to increase frequency, down to decrease). The wave patterns should smoothly transition to the new frequency.\nNote:\n- Your output should be implemented in JavaScript with HTML and CSS.\n- Ensure that the output has both index.js and index.html files\n
    """
    punctuation = " <hello>[goodbye]"
    # logger.info("XSS encoded: " + xss_encoded)
    logger.info(
        "Result: "
        + str(
            await sanitize_miner_feedback(
                add_multiplication,
                add_multiplication_question,
            )
        )
    )
    logger.info(
        "Result: " + str(await sanitize_miner_feedback(punctuation, "question"))
    )


if __name__ == "__main__":
    import asyncio

    asyncio.run(test_sanitize_human_feedback())
