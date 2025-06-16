import asyncio

from loguru import logger

from commons.objects import ObjectManager
from dojo.chain import get_async_subtensor
from dojo.utils.config import source_dotenv

source_dotenv()


async def main():
    miner = await ObjectManager.get_miner()
    if not miner:
        logger.error("Miner not found")
        return

    async def shutdown_miner():
        try:
            subtensor = await get_async_subtensor()
            if subtensor:
                await subtensor.close()
        except Exception as e:
            logger.trace(
                f"Attempted to close subtensor connection but failed due to {e}"
            )
            pass

    running_tasks = [
        asyncio.create_task(miner.log_miner_status()),
        asyncio.create_task(miner.run()),
        # asyncio.create_task(
        #     start_block_subscriber(
        #         callbacks=[miner.block_headers_callback], max_interval_sec=60
        #     )
        # ),
        asyncio.create_task(miner.block_updater()),
    ]

    # NOTE: blocking call that starts the uvicorn server
    await miner.start_server()

    logger.info("Performing shutdown tasks...")
    await shutdown_miner()
    for task in running_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            logger.info(f"Cancelled task {task.get_name()}")
        except Exception as e:
            logger.error(f"Task {task.get_name()} raised an exception: {e}")
            pass

    logger.info("Done, exiting main function.")


if __name__ == "__main__":
    asyncio.run(main())
