from typing import Any, Awaitable, Callable, Dict, Generic, TypeAlias, TypeVar

from fastapi import Request
from pydantic import BaseModel

# TODO: clean these 2 type vars up
PydanticModel = TypeVar("PydanticModel", bound=BaseModel)
StdResponseBody: TypeAlias = Dict[str, Any] | PydanticModel

# define a pydantic model here so that we can apply these to child of BaseModel
ServerHandlerFunc: TypeAlias = Callable[[Request, PydanticModel], Awaitable[Any]]


class StdResponse(BaseModel, Generic[PydanticModel]):
    success: bool
    body: Dict[str, Any] | PydanticModel | None = None
    error: str | None = None
    error: str | None = None


# TODO: remove this after testing
# Define your payload models
class PayloadA(BaseModel):
    field1: str
    field2: str
