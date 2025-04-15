import traceback
from typing import Any, List, Type

import orjson
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import ORJSONResponse
from loguru import logger

from dojo.messaging.exceptions import InvalidSignatureException
from dojo.messaging.middleware import SignatureMiddleware
from dojo.messaging.types import PydanticModel, ServerHandlerFunc
from dojo.messaging.utils import create_response, decode_body


class Server:
    def __init__(self, app: FastAPI | None = None) -> None:
        self.app = FastAPI() or app
        self.app.add_middleware(SignatureMiddleware)
        # NOTE: here we register some exception handlers that make it easier to
        # write miner's code
        self._add_http_exception_handler()
        self._add_invalid_signature_exception_handler()

    def _add_http_exception_handler(self) -> None:
        """Register exception handlers to standardize error responses"""

        @self.app.exception_handler(HTTPException)
        async def http_exception_handler(  # pyright: ignore[reportUnusedFunction]
            request: Request, exc: HTTPException
        ) -> ORJSONResponse:
            """Convert HTTPExceptions to standardized response format"""
            logger.error(f"HTTPException: {str(exc)}")
            return create_response(
                error=str(exc.detail), body={}, status_code=exc.status_code
            )

    def _add_invalid_signature_exception_handler(self) -> None:
        """Register invalid signature exception handler to standardize error responses"""

        @self.app.exception_handler(InvalidSignatureException)
        async def invalid_signature_exc_handler(  # pyright: ignore[reportUnusedFunction]
            request: Request, exc: InvalidSignatureException
        ) -> ORJSONResponse:
            """Convert InvalidSignatureException to standardized response format"""
            logger.error(f"HTTPException: {str(exc)}")
            return create_response(
                error=str(exc),
                body={},
                status_code=403,
            )

    def serve_synapse(
        self, synapse: Type[PydanticModel], handler: ServerHandlerFunc[PydanticModel]
    ) -> None:
        # NOTE: we always want to have signature middleware, as miners should
        # only be reachable by validators
        self.app = _register_route_handler(self.app, handler, model=synapse)

    async def initialise(self, server_config: uvicorn.Config | None = None) -> bool:
        try:
            logger.info(f"Server will support the following routes: {self.app.routes=}")
            default_config = uvicorn.Config(
                app=self.app,
                host="0.0.0.0",
                port=8888,
                workers=1,
                log_level="info",
                reload=False,
            )
            if not server_config:
                logger.info(
                    f"Server config not provided, using default config: host:{default_config.host}, port: {default_config.port}, log_level: {default_config.log_level}"
                )
            server = uvicorn.Server(
                default_config if not server_config else server_config
            )
            await server.serve()

            return True
        except Exception as e:
            logger.error(f"Error starting server: {str(e)}")
            return False


def _register_route_handler(
    app: FastAPI,
    handler: ServerHandlerFunc[PydanticModel],
    model: Type[PydanticModel],
    # NOTE: let's just default to post for now
    methods: List[str] = ["POST"],
) -> FastAPI:
    """Register a route with a Pydantic model to allow easily adding new endpoints"""

    async def handler_wrapper(request: Request) -> ORJSONResponse:
        """Wrapper around the request that handles zstd decompression and payload validation"""
        try:
            body: bytes = await decode_body(request)
            logger.info(f"Got request: body: {body=}")
            data: dict[str, Any] = {}
            try:
                logger.info("Attempting to decode body")
                logger.info(f"Type: {type(body)} Body: {body}")
                data = orjson.loads(body)
            except orjson.JSONDecodeError as e:
                logger.error(f"JSON Decode error: {str(e)}")
                return create_response(
                    error=f"Invalid JSON, exception: {str(e)}",
                    body=data,
                    status_code=400,
                )

            try:
                logger.info(f"Attempting to validate payload: {data=}")
                payload = model.model_validate(data)
            except Exception as e:
                return create_response(
                    error=f"Validation error: {str(e)}",
                    body=data,
                    status_code=400,
                )

            result = await handler(request, payload)

            # Return standardized response format
            return create_response(body=result)
        except HTTPException as e:
            logger.error(f"HTTPException: {str(e)}")
            raise e
        except Exception as e:
            traceback.print_exc()
            logger.error(f"Error processing request due to: {str(e)}")
            # TODO: add more context here
            return create_response(error=f"Internal server error: {str(e)}", body={})

    # grab docstrings from underlying function
    description = handler.__doc__ if handler.__doc__ else handler_wrapper.__doc__
    handler_wrapper.__name__ = handler.__name__
    app.add_api_route(
        path="/" + model.__name__.lstrip("/"),
        endpoint=handler_wrapper,
        methods=methods,
        operation_id=f"handle_{model.__name__}",
        description=description,
    )
    return app
