import logging
from typing import Any, Awaitable, Callable, Generic, TypeAlias, TypeVar

import aiohttp
from fastapi import Request
from loguru import logger
from pydantic import BaseModel, ConfigDict

PydanticModel = TypeVar("PydanticModel", bound=BaseModel)
# define a pydantic model here so that we can apply these to child of BaseModel
ServerHandlerFunc: TypeAlias = Callable[[Request, PydanticModel], Awaitable[Any]]


class StdResponse(BaseModel, Generic[PydanticModel]):
    """Standardized response that preserves error and metadata returned from `server.py`"""

    # WARN: extra ignore to ignore extra fields,
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    body: PydanticModel
    error: str | None = None
    metadata: dict[str, Any] = {}
    client_response: aiohttp.ClientResponse | None
    exception: BaseException | None = None


SIGNATURE_HEADER = "x-signature"
HOTKEY_HEADER = "x-hotkey"
MESSAGE_HEADER = "x-message"


class InterceptHandler(logging.Handler):
    def emit(self, record):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Use the logging record's information instead of trying to calculate depth
        try:
            logger.patch(
                lambda r: r.update(
                    name=record.name,
                    function=record.funcName,
                    file=record.pathname,
                    line=record.lineno,
                    module=record.module,
                )
            ).log(level, record.getMessage())
        except:  # noqa: E722
            pass
