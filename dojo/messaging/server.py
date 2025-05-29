import traceback
from http import HTTPStatus
from typing import Any, List, Type

import orjson
import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import ORJSONResponse
from loguru import logger
from pydantic import BaseModel

from dojo.messaging.exceptions import InvalidSignatureException
from dojo.messaging.middleware import SignatureMiddleware, ZstdMiddleware
from dojo.messaging.types import PydanticModel, ServerHandlerFunc
from dojo.messaging.utils import create_response

router = APIRouter()


@router.api_route("/health", methods=["GET", "HEAD"])
async def health_check():
    return ORJSONResponse(content={}, status_code=HTTPStatus.OK)


class Server:
    def __init__(self, app: FastAPI | None = None) -> None:
        self.app = app or FastAPI()
        self.app.include_router(router)
        self.app.add_middleware(ZstdMiddleware)
        self.app.add_middleware(SignatureMiddleware)
        # NOTE: here we register some exception handlers that make it easier to
        # write miner's code
        self._add_http_exception_handler()
        self._add_invalid_signature_exception_handler()
        self.server_task = None
        self.config = None

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
                status_code=HTTPStatus.FORBIDDEN,
            )

    def serve_synapse(
        self, synapse: Type[PydanticModel], handler: ServerHandlerFunc[PydanticModel]
    ) -> None:
        # NOTE: we always want to have signature middleware, as miners should
        # only be reachable by validators
        self.app = _register_route_handler(self.app, handler, model=synapse)

    async def initialise(self, port: int) -> bool:
        try:
            logger.info(f"Server will support the following routes: {self.app.routes=}")
            server_config = uvicorn.Config(
                app=self.app,
                host="0.0.0.0",
                port=port,
                workers=1,
                log_level="info",
                reload=False,
            )
            self.config = server_config
            logger.info(
                f"Using server config host:{server_config.host}, port: {server_config.port}, log_level: {server_config.log_level}"
            )
            server = uvicorn.Server(server_config)
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
    methods: List[str] = ["POST", "HEAD"],
) -> FastAPI:
    """Register a route with a Pydantic model to allow easily adding new endpoints"""

    async def handler_wrapper(request: Request) -> ORJSONResponse:
        """Wrapper around the request that handles zstd decompression and payload validation"""
        try:
            data: dict[str, Any] = {}
            try:
                # NOTE: we should be able to just read the data directly since
                # there's ZstdMiddleware enabled
                data = orjson.loads(await request.body())
            except orjson.JSONDecodeError as e:
                logger.error(f"JSON Decode error: {str(e)}")
                return create_response(
                    error=f"Invalid JSON, exception: {str(e)}",
                    body=data,
                    status_code=400,
                )

            try:
                logger.debug(f"Attempting to validate payload: {data=}")
                payload = model.model_validate(data)
            except Exception as e:
                logger.error(f"Validation error: {str(e)}")
                return create_response(
                    error=f"Validation error: {str(e)}",
                    body=data,
                    status_code=400,
                )

            # TODO: figure out why result is None?
            result = await handler(request, payload)

            logger.success(
                f"Handler: {handler.__name__}, result type:{type(result)}, result:{result}"
            )
            if not isinstance(result, dict):
                if isinstance(result, bytes):
                    result = orjson.loads(result)
                elif issubclass(type(result), BaseModel):
                    result = result.model_dump()
                return create_response(body=result)

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
        path="/" + model.__name__.lstrip("/").rstrip("/"),
        endpoint=handler_wrapper,
        methods=methods,
        operation_id=f"handle_{model.__name__}",
        description=description,
    )
    return app


# if __name__ == "__main__":
#     # Example usage
#     server = Server()
#     # Define your Pydantic model and handler function here
#     # server.serve_synapse(MyModel, my_handler)
#     # asyncio.run(server.initialise())
#     import asyncio
#
#     asyncio.run(server.initialise(port=8888))
