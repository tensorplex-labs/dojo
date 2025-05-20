import asyncio
import gc
import logging as python_logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from commons.api.middleware import LimitContentLengthMiddleware
from commons.dataset.synthetic import SyntheticAPI
from commons.exceptions import FatalSyntheticGenerationError
from commons.objects import ObjectManager
from database.client import connect_db, disconnect_db
from dojo.chain import get_async_subtensor
from dojo.logging import (
    ValidatorLogForwarder,
    configure_logger,
    forwarded_log_filter,
    get_log_level,
    logger,
    python_logging_to_loguru,
)
from dojo.utils.config import source_dotenv

source_dotenv()

log_level = get_log_level(ObjectManager.get_config)
configure_logger(log_level)
python_logging_to_loguru(level=getattr(python_logging, log_level))
api_log_forwarder = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Performing startup tasks...")
    await connect_db()
    # Setup validator API logging
    global api_log_forwarder
    api_log_forwarder = ValidatorLogForwarder()
    api_log_forwarder.start()

    # Add the handler directly to Loguru with the filter
    log_forwarder_handler = logger.add(
        api_log_forwarder,
        level=log_level,
        format="{message}",
        filter=forwarded_log_filter,
        colorize=True,
    )

    yield

    # Cleanup logging handlers
    if api_log_forwarder:
        try:
            # Remove the Loguru handler we added
            if log_forwarder_handler:
                logger.remove(log_forwarder_handler)
        except Exception as e:
            print(f"Error removing Loguru handlers: {e}")

        # Stop the handler and flush logs
        await api_log_forwarder.stop()

    await _shutdown_validator()


def _check_fatal_errors(task: asyncio.Task):
    """if a fatal error is detected, shut down the validator."""
    try:
        task.result()
    except FatalSyntheticGenerationError as e:
        logger.error(f"Fatal Error - shutting down validator: {e}")
        asyncio.create_task(_shutdown_validator())
    finally:
        gc.collect()


async def _shutdown_validator():
    logger.info("Performing shutdown tasks...")
    validator = await ObjectManager.get_validator()
    if validator:
        validator.subtensor.substrate.close()
        await validator.save_state()
    await SyntheticAPI.close_session()
    await disconnect_db()
    try:
        subtensor = await get_async_subtensor()
        if subtensor:
            await subtensor.close()
    except Exception as e:
        logger.trace(f"Attempted to close subtensor connection but failed due to {e}")
        pass

    logger.info("Cancelling remaining tasks ...")
    tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
    for task in tasks:
        task.cancel()


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
)
app.add_middleware(LimitContentLengthMiddleware)


async def main():
    validator = await ObjectManager.get_validator()
    config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=ObjectManager.get_config().api.port,
        workers=1,
        log_level="debug",
        log_config=None,  # Disable uvicorn's default logging config
    )
    server = uvicorn.Server(config)
    running_tasks = [
        asyncio.create_task(validator.log_validator_status()),
        asyncio.create_task(validator.run()),
        asyncio.create_task(validator.update_tasks_polling()),
        asyncio.create_task(validator.score_and_send_feedback()),
        asyncio.create_task(validator.send_heartbeats()),
        # asyncio.create_task(
        #     start_block_subscriber(
        #         callbacks=[validator.block_headers_callback], max_interval_sec=60
        #     )
        # ),
        asyncio.create_task(validator.block_updater()),
        asyncio.create_task(validator.cleanup_resources()),
    ]
    # set a callback on validator.run() to check for fatal errors.
    running_tasks[1].add_done_callback(_check_fatal_errors)

    await server.serve()

    for task in running_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            logger.info(f"Cancelled task {task.get_name()}")
        except Exception as e:
            logger.error(f"Task {task.get_name()} raised an exception: {e}")
            pass

    logger.info("Exiting main function.")


if __name__ == "__main__":
    asyncio.run(main())
