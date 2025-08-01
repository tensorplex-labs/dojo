import asyncio
import gc
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from database import connect_db, disconnect_db
from dojo.api.middleware import LimitContentLengthMiddleware
from dojo.api.synthetic_api import FatalSyntheticGenerationError, SyntheticAPI
from dojo.chain import get_async_subtensor
from dojo.human_feedback import FeedbackLoop
from dojo.objects import ObjectManager
from dojo.utils import source_dotenv, validate_services

source_dotenv()

ENABLE_HFL = os.getenv("ENABLE_HFL", "true").lower() == "true"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Performing startup tasks...")
    await connect_db()
    yield
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
    if not await validate_services():
        raise RuntimeError("Services are not valid")

    validator = await ObjectManager.get_validator()
    if not validator:
        raise RuntimeError("Validator not found")

    feedback_loop = FeedbackLoop()

    config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=ObjectManager.get_config().api.port,
        workers=1,
        log_level="info",
        reload=False,
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
    ]
    if ENABLE_HFL:
        running_tasks.extend(
            [
                asyncio.create_task(feedback_loop.start_feedback_loop(validator)),
                asyncio.create_task(feedback_loop.update_tf_task_results(validator)),
                asyncio.create_task(feedback_loop.create_sf_tasks(validator)),
                asyncio.create_task(feedback_loop.update_sf_task_results(validator)),
                asyncio.create_task(feedback_loop.create_next_tf_tasks(validator)),
            ]
        )
    else:
        logger.info("HFL is disabled, skipping HFL tasks")

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

    logger.info("Done, exiting main function.")


if __name__ == "__main__":
    asyncio.run(main())
