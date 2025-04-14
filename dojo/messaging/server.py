from typing import List, Type

import orjson
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from loguru import logger

from dojo.messaging.types import PydanticModel, ServerHandlerFunc
from dojo.messaging.utils import create_response, decode_body


class Server:
    def __init__(self, app: FastAPI | None = None) -> None:
        if not app:
            self.app = FastAPI()
        else:
            self.app = app

    def serve_synapse(
        self, synapse: Type[PydanticModel], handler: ServerHandlerFunc[PydanticModel]
    ) -> None:
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
            # TODO: remove after trying to use

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

    async def handler_wrapper(request: Request):
        """Wrapper around the request that handles zstd decompression and payload validation"""
        try:
            body = await decode_body(request)

            print(f"Got request: body: {body=}")
            try:
                data = orjson.loads(body)
            except orjson.JSONDecodeError as e:
                return create_response(
                    success=False, error=f"Invalid JSON, exception: {str(e)}"
                )

            try:
                payload = model.model_validate(data)
            except Exception as e:
                return create_response(
                    success=False, error=f"Validation error: {str(e)}"
                )

            result = await handler(request, payload)

            # Return standardized response format
            return create_response(success=True, body=result)
        except HTTPException as e:
            logger.error(f"HTTPException: {str(e)}")
            raise e
        except Exception as e:
            logger.error(f"Error processing request due to: {str(e)}")
            return create_response(
                success=False, error=f"Internal server error: {str(e)}"
            )

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
