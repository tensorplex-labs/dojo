"""
A set of chain-related utility functions.

Configure as needed in __init__.py for module level access.
"""

from .types import BlockHeader


def parse_block_headers(raw_block_header: dict):
    return BlockHeader.model_validate(raw_block_header)
