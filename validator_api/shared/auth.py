import time
from typing import Dict, Tuple

from fastapi import HTTPException, Request

from commons.utils import check_stake, verify_hotkey_in_metagraph, verify_signature
from dojo.logging import logging as logger


class ValidatorAuth:
    """Authentication handler for validator operations"""

    _stake_cache: Dict[str, Tuple[bool, float]] = {}
    _stake_cache_ttl: int = 300

    @staticmethod
    async def validate_validator(
        request: Request,
        hotkey: str,
        signature: str,
        message: str,
    ) -> None:
        """
        Validate a validator's credentials and permissions

        Args:
            request: FastAPI request object containing app state
            hotkey: Validator's hotkey
            signature: Signature of the message
            message: Original message that was signed

        Raises:
            HTTPException: If validation fails
        """
        logger.info(f"Validating credentials for hotkey: {hotkey}")

        if not signature.startswith("0x"):
            logger.error(f"Invalid signature format for hotkey: {hotkey}")
            raise HTTPException(status_code=401, detail="Invalid signature format")

        if not verify_signature(hotkey, signature, message):
            logger.error(f"Invalid signature for hotkey: {hotkey}")
            raise HTTPException(status_code=401, detail="Invalid signature")

        hotkey_in_metagraph = verify_hotkey_in_metagraph(
            request.app.state.metagraph, hotkey
        )
        if not hotkey_in_metagraph:
            logger.error(f"Hotkey {hotkey} not found in metagraph")
            raise HTTPException(status_code=401, detail="Hotkey not found in metagraph")

        has_sufficient_stake = ValidatorAuth._check_stake_with_cache(
            request.app.state.subtensor, hotkey
        )
        if not has_sufficient_stake:
            logger.error(f"Insufficient stake for hotkey {hotkey}")
            raise HTTPException(status_code=401, detail="Insufficient stake for hotkey")

        logger.info(f"Successfully validated credentials for hotkey: {hotkey}")

    @staticmethod
    def _check_stake_with_cache(subtensor, hotkey: str) -> bool:
        current_time = time.time()

        if hotkey in ValidatorAuth._stake_cache:
            result, timestamp = ValidatorAuth._stake_cache[hotkey]
            if current_time - timestamp < ValidatorAuth._stake_cache_ttl:
                logger.debug(f"Using cached stake result for hotkey: {hotkey}")
                return result

        logger.debug(f"Cache miss for hotkey: {hotkey}, checking stake")
        result = check_stake(subtensor, hotkey)

        ValidatorAuth._stake_cache[hotkey] = (result, current_time)

        return result
