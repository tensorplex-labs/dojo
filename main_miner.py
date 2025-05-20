import asyncio
import logging as python_logging

from commons.objects import ObjectManager
from dojo.chain import get_async_subtensor
from dojo.logging import (
    configure_logger,
    get_log_level,
    logger,
    python_logging_to_loguru,
)
from dojo.utils.config import source_dotenv

source_dotenv()

log_level = get_log_level(ObjectManager.get_config())
configure_logger(log_level)
python_logging_to_loguru(level=getattr(python_logging, log_level))


async def shutdown_miner():
    try:
        subtensor = await get_async_subtensor()
        if subtensor:
            await subtensor.close()
    except Exception as e:
        logger.trace(f"Attempted to close subtensor connection but failed due to {e}")
        pass


async def main():
    miner = await ObjectManager.get_miner()

    tasks = [
        asyncio.create_task(miner.log_miner_status()),
        asyncio.create_task(miner.run()),
        # asyncio.create_task(
        #     start_block_subscriber(
        #         callbacks=[miner.block_headers_callback], max_interval_sec=60
        #     )
        # ),
        asyncio.create_task(miner.block_updater()),
    ]

    await asyncio.gather(*tasks)

    logger.info("Performing shutdown tasks...")
    await shutdown_miner()
    logger.info("Done, exiting main function.")


if __name__ == "__main__":
    asyncio.run(main())
