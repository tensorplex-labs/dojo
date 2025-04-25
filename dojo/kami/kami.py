import asyncio
import os
from typing import Any, Dict, Optional

import aiohttp

from dojo.kami.types import ServeAxonPayload, SubnetMetagraph


class Kami:
    """
    Kami is a class that handles the connection to the Dojo API.
    """

    def __init__(self, url: str = "http://kami:3000"):
        self.url = os.getenv("KAMI_API_URL", url)
        self.session = None
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
        await self.session.close()

    async def get(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send a GET request to the Dojo API.

        Args:
            endpoint (str): The API endpoint to send the request to.
            params (Optional[Dict[str, Any]]): Optional query parameters to include in the request.

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
            raise RuntimeError(f"Error connecting to Dojo API: {e}")

    async def post(
        self, endpoint: str, data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send a POST request to the Dojo API.

        Args:
            endpoint (str): The API endpoint to send the request to.
            data (Optional[Dict[str, Any]]): Optional data to include in the request body.

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
            raise RuntimeError(f"Error connecting to Dojo API: {e}")

    async def get_metagraph(self, netuid: int) -> Dict[str, Any]:
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

    async def get_hotkeys(self, netuid: int) -> Dict[str, Any]:
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


async def aget_effective_stake(hotkey: str, subnet_metagraph: SubnetMetagraph) -> float:
    # With runtime api, you do not need to query root metagraph, you can just get it from the subnet itself.
    idx = subnet_metagraph.get("hotkeys", []).index(hotkey)

    root_stake = 0
    try:
        root_stake = subnet_metagraph.get("taoStake", [])[idx]
    except (ValueError, IndexError):
        logger.trace(
            f"Hotkey {hotkey} not found in root metagraph, defaulting to 0 root_stake"
        )

    alpha_stake = 0
    try:
        alpha_stake = subnet_metagraph.get("alphaStake", [])[idx]
    except (ValueError, IndexError):
        logger.trace(
            f"Hotkey {hotkey} not found in subnet metagraph for netuid: {subnet_metagraph.netuid}, defaulting to 0 alpha_stake"
        )

    effective_stake = (root_stake * 0.18) + alpha_stake

    return effective_stake


async def main():
    kami = Kami(url="http://localhost:3000")
    try:
        (
            metagraph,
            axons,
            hotkeys,
            block,
            stake,
            valid_hotkey,
        ) = await asyncio.gather(
            kami.get_metagraph(52),
            kami.get_axons(1),
            kami.get_hotkeys(1),
            kami.get_current_block(),
            kami.get_stake(1),
            kami.is_hotkey_registered(
                2, "5FbcrSPdZat1pn9D7SfsLXrBLq1U3nLp7n7iLBsPTfcTnenv"
            ),
        )
        print("Metagraph:", metagraph)
        effective_stake = await aget_effective_stake(
            "5E4z3h9yVhmQyCFWNbY9BPpwhx4xFiPwq3eeqmBgVF6KULde", metagraph
        )
        print("Effective stake:", effective_stake)

    except RuntimeError as e:
        print(e)
    finally:
        await kami.close()


if __name__ == "__main__":
    asyncio.run(main())
