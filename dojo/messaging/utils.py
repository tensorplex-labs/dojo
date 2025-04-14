from typing import Any

import substrateinterface  # pyright: ignore[reportMissingTypeStubs]
import zstandard as zstd
from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import ORJSONResponse
from loguru import logger
from pydantic import BaseModel


def create_response(
    body: dict[str, Any],
    status_code: int = 200,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
):
    """
    Helper function to create standardized RESTful API responses

    Args:
        body: The response data
        status_code: HTTP status code (default: 200)
        error: Optional error message for error responses
        metadata: Optional metadata like pagination info, request ID, etc.
    """
    content = {
        "body": jsonable_encoder(body),
    }

    if error:
        content["error"] = error

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
