import asyncio
import time
from typing import Any

from bittensor.core.async_subtensor import AsyncSubstrateInterface
from bittensor.core.subtensor import SubstrateInterface, SubstrateRequestException

last_block_time = time.time()


subtensor_url = "wss://entrypoint-finney.opentensor.ai:443"


def sync_block_handler(obj: Any) -> None:
    global last_block_time
    current_time = time.time()
    time_diff = current_time - last_block_time
    print(f"New block: {obj}")
    print(f"Time since last block: {time_diff:.2f} seconds")
    last_block_time = current_time


def start_sync_block_handler():
    try:
        # Connect to the substrate node
        substrate = SubstrateInterface(subtensor_url)

        # Subscribe to new blocks - simplified subscription
        substrate.subscribe_block_headers(
            subscription_handler=sync_block_handler, finalized_only=True
        )

        # Keep the script running
        while True:
            time.sleep(1)

    except SubstrateRequestException as e:
        print(f"Substrate error: {e}")
    except KeyboardInterrupt:
        print("\nSubscription ended by user")
    except Exception as e:
        print(f"Unexpected error: {e}")


async def async_block_handler(obj: Any) -> None:
    global last_block_time
    current_time = time.time()
    time_diff = current_time - last_block_time
    print(f"Handler 1: New block: {obj}")
    print(f"Time since last block: {time_diff:.2f} seconds")
    last_block_time = current_time


async def start_async_block_handler():
    try:
        # Connect to the substrate node
        async with AsyncSubstrateInterface(subtensor_url) as substrate:
            # Subscribe to new blocks - simplified subscription
            await substrate.subscribe_block_headers(
                subscription_handler=async_block_handler, finalized_only=True
            )
    except SubstrateRequestException as e:
        print(f"Substrate error: {e}")
    except KeyboardInterrupt:
        print("\nSubscription ended by user")
    except Exception as e:
        print(f"Unexpected error: {e}")


async def main():
    # start_sync_block_handler()
    await start_async_block_handler()


if __name__ == "__main__":
    asyncio.run(main())
