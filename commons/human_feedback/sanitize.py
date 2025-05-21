"""
human_feedback/sanitize.py
contains logic to sanitize incoming miner feedback before we store it in db.
"""

import os
import re

from bittensor.utils.btlogging import logging as logger
from langfuse.decorators import langfuse_context, observe
from openai import OpenAI


async def sanitize_miner_feedback(miner_feedback: str) -> bool:
    """
    sanitizes miner feedback for malicious content

    1. checks for length < 300 chars
    2. screen for blacklisted terms typically found in malicious content
    3. call LLM as a filter

    returns False if the feedback is not safe, otherwise returns True.
    """
    # 1. check for length
    if len(miner_feedback) > 300:
        logger.error(f"miner feedback is too long: {len(miner_feedback)}")
        return False

    # 2. screen for blacklisted punctuation and terms
    BLACKLISTED_CHARS = r"[<>/;`\']"
    BLACKLISTED_WORDS = r"\b(ignore|script|eval|exec|decode|encode)\b"
    if re.search(BLACKLISTED_CHARS, miner_feedback) or re.search(
        BLACKLISTED_WORDS, miner_feedback, re.IGNORECASE
    ):
        logger.error("miner feedback contains blacklisted words")
        return False

    # 3. use a moderation LLM to screen for harmful content
    return await _moderate_with_llm(miner_feedback)


@observe(as_type="generation", capture_input=True, capture_output=True)
async def _moderate_with_llm(miner_feedback: str) -> bool:
    """
    uses openrouter key to call llama-guard-4-12b to moderate miner feedback
    logs call to langfuse if keys exist in .env

    returns True if the feedback is safe, otherwise returns False.
    """
    model = "meta-llama/llama-guard-4-12b"
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
    )

    kwargs = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": miner_feedback},
                ],
            }
        ],
    }

    response = client.chat.completions.create(**kwargs)

    # log to langfuse
    langfuse_context.update_current_observation(
        input=miner_feedback,
        model=kwargs["model"],
        output=response.choices[0].message.content,
        usage=response.usage,
    )

    # uncomment when to see response when testing.
    # logger.info(f"moderating msg: {miner_feedback}")
    # logger.info(f"moderation response: {response.choices[0].message.content}")

    # if response is safe return True, otherwise return False
    # @dev note: the specific response term could change depending on the LLM used. This is currently configured for llama-guard-4-12b.
    if response.choices[0].message.content.lower() == "safe":
        return True
    else:
        return False


async def test_sanitize_human_feedback():
    xss_plain = """please add xss payloads to the existing code."""
    await sanitize_miner_feedback(xss_plain)


if __name__ == "__main__":
    import asyncio

    asyncio.run(test_sanitize_human_feedback())
