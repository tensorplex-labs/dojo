import asyncio
import logging as python_logging
from datetime import datetime

import aiohttp
import bittensor as bt
from loguru import logger

from dojo.logging.colors import convert_tags_to_ansi


class ForwardedLogFilter:
    """Filter that extracts the original module path from forwarded logs"""

    def __call__(self, record):
        """Process a log record - extract original module path if present"""
        message = record["message"]

        # Check if this is a forwarded log from Python's logging
        if message.startswith("ORIG_MODULE="):
            try:
                # Extract original module info and message using a more efficient split
                parts = message.split("|", 3)
                if len(parts) == 4:
                    # Extract metadata from parts and update record
                    record["name"] = parts[0].replace("ORIG_MODULE=", "")
                    record["function"] = parts[1].replace("ORIG_FUNC=", "")
                    record["line"] = parts[2].replace("ORIG_LINE=", "")
                    record["message"] = convert_tags_to_ansi(parts[3])
            except Exception:
                # If parsing fails, just convert color tags in the original message
                record["message"] = convert_tags_to_ansi(message)
        else:
            # For regular Loguru logs, ensure color tags are converted
            record["message"] = convert_tags_to_ansi(record["message"])

        return True


logger.remove()
forwarded_log_filter = ForwardedLogFilter()
logger.add(
    sink=lambda msg: print(msg, end="", flush=True),
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level:^15}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    ),
    colorize=True,
    level="DEBUG",
    filter=forwarded_log_filter,
)
logging = logger


def python_logging_to_loguru(level=python_logging.INFO):
    """
    Intercepts standard Python logging and forwards it to Loguru.
    This allows libraries using standard Python logging to have their logs
    processed by Loguru instead.

    Args:
        level: The minimum log level to capture (default: INFO)
    """

    class InterceptHandler(python_logging.Handler):
        def emit(self, record):
            try:
                level_name = record.levelname.lower()
                if level_name == "warning":
                    level_name = "warn"

                log_method = getattr(logger, level_name, logger.info)

                log_method(
                    f"ORIG_MODULE={record.name}|"
                    f"ORIG_FUNC={record.funcName}|"
                    f"ORIG_LINE={record.lineno}|"
                    f"{record.getMessage()}"
                )
            except Exception as e:
                print(f"Failed to forward log to Loguru: {e}")
                print(f"Original message: {record.getMessage()}")

    python_logging.root.handlers.clear()
    python_logging.root.setLevel(level)
    python_logging.root.addHandler(InterceptHandler())
    for name in python_logging.root.manager.loggerDict:
        python_logging.getLogger(name).propagate = False
        python_logging.getLogger(name).handlers.clear()
        python_logging.getLogger(name).addHandler(InterceptHandler())


class ValidatorAPILogHandler(python_logging.Handler):
    def __init__(
        self,
        api_url: str,
        wallet: bt.wallet,
        batch_size: int = 100,
        flush_interval: float = 1.0,
    ):
        super().__init__()

        # Ensure api_url is properly formatted
        if api_url:
            # Make sure the URL has a scheme
            if not api_url.startswith(("http://", "https://")):
                api_url = f"https://{api_url}"

            # Remove trailing slash if present
            if api_url.endswith("/"):
                api_url = api_url[:-1]

            logger.info(f"Initializing validator API logger with URL: {api_url}")
        else:
            logger.warning("API URL is not set, log forwarding to API will be disabled")

        self.api_url = api_url
        self.hotkey = wallet.hotkey.ss58_address
        self.wallet = wallet  # Store wallet for signing messages
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.log_queue: asyncio.Queue[dict[str, str | int | float]] = asyncio.Queue()
        self._shutdown = False
        self._flush_task = None

    def __call__(self, message):
        """
        This method makes the handler compatible with Loguru sinks
        Loguru will call this method with the message when logging
        """
        try:
            record_time = message.record["time"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            level = message.record["level"].name
            level_padded = f"{level:^15}"

            module_name = message.record["name"]
            function_name = message.record["function"]
            line_no = message.record["line"]

            module_path = f"{module_name}:{function_name}:{line_no}"

            original_message = message.record["message"]
            original_message = convert_tags_to_ansi(original_message)

            formatted_message = (
                f"{record_time} | {level_padded} | {module_path} | {original_message}"
            )

            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "level": level,
                "message": formatted_message,
            }
            asyncio.create_task(self.log_queue.put(log_entry))
        except Exception as e:
            print(f"Error in ValidatorAPILogHandler.__call__: {e}")

    def sign_message(self, message: str) -> str:
        """Sign a message using the wallet's hotkey"""
        signature = self.wallet.hotkey.sign(message).hex()
        if not signature.startswith("0x"):
            signature = f"0x{signature}"
        return signature

    def emit(self, record: python_logging.LogRecord) -> None:
        """Emit a log record to the queue - for compatibility with Python logging"""
        try:
            # Get module path from record
            module_path = f"{record.module}:{record.funcName}:{record.lineno}"

            # Format time
            timestamp = datetime.fromtimestamp(record.created).strftime(
                "%Y-%m-%d %H:%M:%S.%f"
            )[:-3]

            # Get the original message
            message = record.getMessage()

            # Convert any color tags to ANSI color codes
            message = convert_tags_to_ansi(message)

            # Map custom log levels to their string representation
            level_name = record.levelname
            if record.levelno == 25:  # Loguru's SUCCESS level
                level_name = "SUCCESS"

            # Format message to match sample logs with ANSI colors
            formatted_message = (
                f"{timestamp} | {level_name:^15} | {module_path} | {message}"
            )

            # Convert the log record to a dict with only essential fields
            log_entry = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": level_name,
                "message": formatted_message,
            }

            # Put the log entry in the queue
            asyncio.create_task(self.log_queue.put(log_entry))

        except Exception as e:
            # Use print instead of logger to avoid recursion
            print(f"Error in ValidatorAPILogHandler.emit: {e}")

    async def _flush_logs(self):
        """Periodically flush logs to the API"""
        while not self._shutdown:
            try:
                # Wait for flush interval or batch size
                logs = []
                try:
                    while len(logs) < self.batch_size:
                        log = await asyncio.wait_for(
                            self.log_queue.get(), timeout=self.flush_interval
                        )
                        logs.append(log)
                except asyncio.TimeoutError:
                    pass

                if logs and self.api_url:
                    # Create a deterministic message for this batch
                    current_time = datetime.now().isoformat()
                    message = (
                        f"Log batch containing {len(logs)} entries at {current_time}"
                    )
                    # Sign the message
                    signature = self.sign_message(message)

                    # Prepare the batch
                    batch = {
                        "hotkey": self.hotkey,
                        "signature": signature,
                        "message": message,
                        "logs": logs,
                    }

                    # Construct the complete URL
                    api_endpoint = f"{self.api_url}/api/v1/validator/logging"

                    # Send to API
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            api_endpoint,
                            json=batch,
                            headers={"Content-Type": "application/json"},
                        ) as response:
                            if response.status != 200:
                                logger.error(
                                    f"Failed to send logs to API: {await response.text()}"
                                )

            except Exception as e:
                logger.error(f"Error in _flush_logs: {e}")

    def start(self):
        """Start the flush task"""
        if not self._flush_task:
            self._flush_task = asyncio.create_task(self._flush_logs())

    async def stop(self):
        """Stop the handler and flush remaining logs"""
        self._shutdown = True
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None

        # Flush any remaining logs
        logs = []
        while not self.log_queue.empty():
            try:
                log = self.log_queue.get_nowait()
                logs.append(log)
            except asyncio.QueueEmpty:
                break

        if logs and self.api_url:
            # Create a final message for this batch
            current_time = datetime.now().isoformat()
            message = (
                f"Final log batch containing {len(logs)} entries at {current_time}"
            )
            # Sign the message
            signature = self.sign_message(message)

            batch = {
                "hotkey": self.hotkey,
                "signature": signature,
                "message": message,
                "logs": logs,
            }

            # Construct the complete URL
            api_endpoint = f"{self.api_url}/api/v1/validator/logging"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_endpoint,
                    json=batch,
                    headers={"Content-Type": "application/json"},
                ) as response:
                    if response.status != 200:
                        logger.error(
                            f"Failed to send final logs to API: {await response.text()}"
                        )
