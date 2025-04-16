from typing import Any, Awaitable, Callable, Generic, TypeAlias, TypeVar

from fastapi import Request
from pydantic import BaseModel

PydanticModel = TypeVar("PydanticModel", bound=BaseModel)
# define a pydantic model here so that we can apply these to child of BaseModel
ServerHandlerFunc: TypeAlias = Callable[[Request, PydanticModel], Awaitable[Any]]


class StdResponse(BaseModel, Generic[PydanticModel]):
    """Standardized response that preserves error and metadata returned from `server.py`"""

    body: PydanticModel
    error: str | None = None
    metadata: dict[str, Any] = {}


SIGNATURE_HEADER = "x-signature"
HOTKEY_HEADER = "x-hotkey"
MESSAGE_HEADER = "x-message"
