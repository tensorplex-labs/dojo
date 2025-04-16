import http
from typing import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import ORJSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from dojo.messaging.types import HOTKEY_HEADER, MESSAGE_HEADER, SIGNATURE_HEADER
from dojo.messaging.utils import create_response, verify_signature


class SignatureMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> ORJSONResponse | Response:
        signature = request.headers.get(SIGNATURE_HEADER, "")
        hotkey = request.headers.get(HOTKEY_HEADER, "")
        message = request.headers.get(MESSAGE_HEADER, "")
        if not hotkey or not signature or not message:
            message = f"{http.HTTPStatus(400).phrase}, missing \
                    headers, expected: {SIGNATURE_HEADER}, {HOTKEY_HEADER}, {MESSAGE_HEADER}, \
                    got: {hotkey=}, {signature=}, {message=}"
            return create_response(body={}, status_code=400, error=message)

        if not verify_signature(hotkey, signature, message):
            return create_response(
                body={},
                status_code=403,
                error=f"{http.HTTPStatus(403).phrase} due to invalid signature",
            )

        # otherwise, proceed with the normal request
        response = await call_next(request)
        return response
