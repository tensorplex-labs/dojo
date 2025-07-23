"""
A set of chain-related utility functions.

Configure as needed in __init__.py for module level access.
"""

from loguru import logger
from typing import Any
from dojo.utils.netip import get_int_ip_address

from kami import AxonInfo, ServeAxonPayload
from .types import BlockHeader


def parse_block_headers(raw_block_header: dict[str, Any]) -> BlockHeader:  # pyright: ignore[reportExplicitAny]
    return BlockHeader.model_validate(raw_block_header)
