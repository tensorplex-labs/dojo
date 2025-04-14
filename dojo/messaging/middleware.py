import http
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from dojo.messaging.utils import verify_signature


class SignatureMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        signature = request.headers.get("X-Signature", "")
        hotkey = request.headers.get("X-Hotkey", "")
        message = request.headers.get("X-Message", "")
        if not hotkey or not signature or not message:
            message = f"{http.HTTPStatus(400).phrase}, missing \
                    headers, expected: X-Hotkey, X-Signature, X-Message, \
                    got: {hotkey=}, {signature=}, {message=}"
            return Response(content=message, status_code=400)
        if not verify_signature(hotkey, signature, message):
            return Response(content=http.HTTPStatus(403).phrase, status_code=403)

        # otherwise, proceed with the normal request
        response = await call_next(request)
        return response
