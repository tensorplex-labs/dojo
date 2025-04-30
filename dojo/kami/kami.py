import json
import os
from typing import Any, Dict

import aiohttp
from bittensor_commit_reveal import get_encrypted_commit
from loguru import logger

from dojo.kami.types import (
    ServeAxonPayload,
    SetWeightsPayload,
    SubnetMetagraph,
)


class Kami:
    """
    Kami is a class that handles the connection to the Kami API.
    """

    # TODO: change back to `http://kami:3000` before release
    def __init__(self, url: str = "http://localhost:3000"):
        self.url = os.getenv("KAMI_API_URL", url).rstrip("/")
        self.session: aiohttp.ClientSession | None = None
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _ensure_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()

    async def close(self):
        """
        Close the aiohttp session.
        """
        if self.session is not None:
            await self.session.close()

    async def get(
        self, endpoint: str, params: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """
        Send a GET request to the Kami API.

        Args:
            endpoint (str): The API endpoint to send the request to.
            params (Dict[str, Any] | None): Optional query parameters to include in the request.

        Returns:
            Dict[str, Any]: The JSON response from the API.
        """
        try:
            await self._ensure_session()
            if self.session is None:
                raise ValueError("Session is not initialized.")
            url = f"{self.url}/{endpoint}"
            async with self.session.get(
                url, headers=self.headers, params=params
            ) as response:
                return await response.json()
        except aiohttp.ClientError as e:
            message = f"Error connecting to Kami API: {e}"
            logger.error(message)
            raise RuntimeError(f"Error connecting to Kami API: {e}")
        except json.decoder.JSONDecodeError as e:
            logger.error(f"Error decoding JSON response: {e}")
            raise e
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise e

    async def post(
        self, endpoint: str, data: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """
        Send a POST request to the Kami API.

        Args:
            endpoint (str): The API endpoint to send the request to.
            data (Dict[str, Any] | None): Optional data to include in the request body.

        Returns:
            Dict[str, Any]: The JSON response from the API.
        """
        try:
            await self._ensure_session()
            if self.session is None:
                raise ValueError("Session is not initialized.")
            url = f"{self.url}/{endpoint}"
            async with self.session.post(
                url, headers=self.headers, json=data
            ) as response:
                return await response.json()
        except aiohttp.ClientError as e:
            message = f"Error connecting to Kami API: {e}"
            logger.error(message)
            raise RuntimeError(message)
        except json.decoder.JSONDecodeError as e:
            logger.error(f"Error decoding JSON response: {e}")
            raise e
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise e

    async def get_metagraph(self, netuid: int) -> SubnetMetagraph:
        """
        Get the metagraph for a given netuid.

        Args:
            netuid (int): The netuid to get the metagraph for.

        Returns:
            Dict[str, Any]: The JSON response from the API.
        """
        get_metagraph = await self.get(f"chain/subnet-metagraph/{netuid}")
        metagraph = get_metagraph.get("data", {})
        return metagraph

    async def get_hotkeys(self, netuid: int) -> list[str]:
        """
        Get the neurons for a given netuid.

        Args:
            netuid (int): The netuid to get the neurons for.

        Returns:
            Dict[str, Any]: The JSON response from the API.
        """
        get_metagraph = await self.get(f"chain/subnet-metagraph/{netuid}")
        metagraph = get_metagraph.get("data", {})
        hotkeys = metagraph.get("hotkeys", [])
        return hotkeys

    async def get_axons(self, netuid: int) -> Dict[str, Any]:
        """
        Get the neurons for a given netuid.

        Args:
            netuid (int): The netuid to get the neurons for.

        Returns:
            Dict[str, Any]: The JSON response from the API.
        """
        get_metagraph = await self.get(f"chain/subnet-metagraph/{netuid}")
        metagraph = get_metagraph.get("data", {})
        axons = metagraph.get("axons", [])
        return axons

    async def get_stake(self, netuid: int) -> Dict[str, Any]:
        """
        Get the root stake.

        Returns:
            Dict[str, Any]: The JSON response from the API.
        """
        result = dict[str, int]()
        get_metagraph = await self.get(f"chain/subnet-metagraph/{netuid}")
        metagraph = get_metagraph.get("data", {})
        alpha_stake = metagraph.get("alphaStake", [])
        root_stake = metagraph.get("taoStake", [])

        result["alpha_stake"] = alpha_stake
        result["root_stake"] = root_stake

        return result

    async def get_current_block(self) -> int:
        """
        Get the neurons for a given netuid.

        Returns:
            int: The current finalized block.
        """
        result = await self.get("chain/latest-block")
        latest_block = result.get("data", {}).get("blockNumber", "")
        return latest_block

    async def get_subnet_hyperparameters(self, netuid: int) -> Dict[str, Any]:
        """
        Get the subnet hyperparameters for a given netuid.

        Args:
            netuid (int): The netuid to get the hyperparameters for.

        Returns:
            Dict[str, Any]: The JSON response from the API.
        """
        result = await self.get(f"chain/subnet-hyperparameters/{netuid}")
        hyperparameters = result.get("data", {})
        return hyperparameters

    async def is_hotkey_registered(
        self, netuid: int, hotkey: str, block: int | None = None
    ) -> bool:
        """
        Check if a hotkey is registered.

        Args:
            netuid (int): The netuid to check.
            hotkey (string): The hotkey to check.
            block (int): The block number to check.

        Returns:
            bool: True if the hotkey is registered, False otherwise.
        """
        result = dict[str, bool]()
        if block is None:
            result = await self.get(
                f"chain/check-hotkey?netuid={netuid}&hotkey={hotkey}"
            )
        else:
            result = await self.get(
                f"chain/check-hotkey?netuid={netuid}&hotkey={hotkey}&block={block}"
            )
        return result.get("data", {}).get("isHotkeyValid", False)

    async def serve_axon(self, payload: ServeAxonPayload) -> Dict[str, Any]:
        """
        Serve axons for a given payload.

        Args:
            payload (ServeAxonPayload): The payload to serve.

        Returns:
            Dict[str, Any]: The JSON response from the API.
        """
        return await self.post("chain/serve-axon", data=payload.model_dump())

    async def set_weights(self, payload: SetWeightsPayload) -> Dict[str, Any]:
        """
        Set weights for a given payload.

        Args:
            payload (SetWeightsPayload): The payload to set weights for.

        Returns:
            Dict[str, Any]: The JSON response from the API.
        """
        get_hpams = await self.get_subnet_hyperparameters(payload.netuid)
        if get_hpams.get("commitRevealWeightsEnabled", False):
            tempo = get_hpams.get("tempo", 0)
            reveal_period = get_hpams.get("commitRevealPeriod", 0)
            if tempo == 0 or reveal_period == 0:
                raise ValueError(
                    "Tempo and reveal round must be greater than 0 for commit reveal weights."
                )

            print(
                f"Commit reveal weights enabled: tempo: {tempo}, reveal_period: {reveal_period}"
            )

            # Encrypt `commit_hash` with t-lock and `get reveal_round`
            commit_for_reveal, reveal_round = get_encrypted_commit(
                uids=payload.dests,
                weights=payload.weights,
                version_key=payload.version_key,
                tempo=tempo,
                current_block=await self.get_current_block(),
                netuid=payload.netuid,
                subnet_reveal_period_epochs=reveal_period,
            )

            print(f"Commit for reveal: {commit_for_reveal}")
            print(f"Reveal round: {reveal_round}")

            cr_payload = {
                "netuid": payload.netuid,
                "commit": commit_for_reveal.hex(),
                "reveal_round": reveal_round,
            }

            return await self.post("chain/set-commit-reveal-weights", data=cr_payload)

        return await self.post("chain/set-weights", data=payload.model_dump())
