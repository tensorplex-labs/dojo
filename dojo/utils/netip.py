import ipaddress
import aiohttp


async def get_int_ip_address(ip: str) -> int:
    """Convert an IP address to an integer representation."""
    try:
        # Convert the IP address to an integer
        return int(ipaddress.ip_address(ip))
    except ValueError as e:
        raise ValueError(f"Invalid IP address '{ip}': {e}") from e


async def get_public_ip() -> str:
    """Fetch the public IP address of the machine."""
    async with aiohttp.ClientSession() as session:
        async with session.get("https://api.ipify.org") as response:
            if response.status != 200:
                raise RuntimeError(
                    f"Failed to fetch public IP, status code: {response.status}"
                )
            return await response.text()
