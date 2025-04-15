from typing import Any, Awaitable, Callable, Generic, TypeAlias, TypeVar

from fastapi import Request
from pydantic import BaseModel

PydanticModel = TypeVar("PydanticModel", bound=BaseModel)
# define a pydantic model here so that we can apply these to child of BaseModel
ServerHandlerFunc: TypeAlias = Callable[[Request, PydanticModel], Awaitable[Any]]


SIGNATURE_HEADER = "X-Signature"
HOTKEY_HEADER = "X-Hotkey"
MESSAGE_HEADER = "X-Message"


class StdResponse(BaseModel, Generic[PydanticModel]):
    success: bool
    body: PydanticModel | None = None
    error: str | None = None
    error: str | None = None
