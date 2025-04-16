from typing import Any

import substrateinterface  # pyright: ignore[reportMissingTypeStubs]
import zstandard as zstd
from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import ORJSONResponse
from loguru import logger
from pydantic import BaseModel

from dojo.messaging.types import HOTKEY_HEADER, MESSAGE_HEADER, SIGNATURE_HEADER


def create_response(
    body: dict[str, Any],
    status_code: int = 200,
    error: str | None = None,
    metadata: dict[str, Any] = {},
):
    """
    Helper function to create standardized RESTful API responses

    Args:
        body: The response data
        status_code: HTTP status code (default: 200)
        error: Optional error message for error responses
        metadata: Optional metadata like pagination info, request ID, etc.
    """
    content = {"body": jsonable_encoder(body), "error": error, "metadata": {}}  # pyright: ignore

    if metadata:
        content["metadata"] = jsonable_encoder(metadata)

    return ORJSONResponse(content=content, status_code=status_code)


def verify_signature(hotkey: str, signature: str, message: str) -> bool:
    """
    returns true if input signature was created by input hotkey for input message.
    """
    try:
        keypair = substrateinterface.Keypair(ss58_address=hotkey, ss58_format=42)
        if not keypair.verify(data=message, signature=signature):
            logger.error(f"Invalid signature for address={hotkey}")
            return False

        logger.success(f"Signature verified, signed by {hotkey}")
        return True
    except Exception as e:
        logger.error(f"Error occurred while verifying signature, exception {e}")
        return False


def encode_body(model: BaseModel) -> bytes:
    json_data = model.model_dump_json().encode()
    compressor = zstd.ZstdCompressor(level=3)
    compressed = compressor.compress(json_data)
    return compressed


async def decode_body(request: Request) -> bytes:
    """Handle zstd decoding to make transmission over network smaller"""
    body = await request.body()
    if (
        "content-encoding" in request.headers
        and "zstd" in request.headers["content-encoding"]
    ):
        try:
            decompressor = zstd.ZstdDecompressor()
            body = decompressor.decompress(body)
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Failed to decompress zstd data: {str(e)}"
            )

    return body


def extract_headers(request: Request) -> tuple[str, str, str]:
    """Based on the headers, extract the hotkey, message and signature"""
    try:
        headers: dict[str, Any] = {}
        for header, value in request.headers.items():
            if header.startswith("X-"):
                headers[header] = value
        signature = headers.get(SIGNATURE_HEADER, "")
        hotkey = headers.get(HOTKEY_HEADER, "")
        message = headers.get(MESSAGE_HEADER, "")
        return hotkey, message, signature

    except Exception:
        return "", "", ""


def is_valid_signature(request: Request) -> bool:
    try:
        headers: dict[str, Any] = {}
        for header, value in request.headers.items():
            if header.startswith("X-"):
                headers[header] = value

        signature = headers.get(SIGNATURE_HEADER)
        hotkey = headers.get(HOTKEY_HEADER)
        message = headers.get(MESSAGE_HEADER)
        if not signature or not hotkey or not message:
            return False
        is_valid = verify_signature(hotkey=hotkey, signature=signature, message=message)
        logger.success(f"Signature verified, signed by {hotkey}")
        return is_valid
    except Exception as e:
        logger.error(f"Error occurred while verifying signature, exception {e}")
        return False
