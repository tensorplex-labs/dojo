import asyncio
import logging as python_logging
from datetime import datetime

import aiohttp
import bittensor as bt
from loguru import logger

from dojo.logging.colors import convert_tags_to_ansi


class ValidatorLogForwarder(python_logging.Handler):
    def __init__(
        self,
        batch_size: int = 100,
        flush_interval: float = 1.0,
    ):
        super().__init__()

        from commons.objects import ObjectManager

        self.config = ObjectManager.get_config()

        from dojo import get_dojo_api_base_url

        api_url = get_dojo_api_base_url()

        if api_url:
            if not api_url.startswith(("http://", "https://")):
                api_url = f"https://{api_url}"
            if api_url.endswith("/"):
                api_url = api_url[:-1]

            logger.info(f"Initializing validator API logger with URL: {api_url}")
        else:
            logger.warning("API URL is not set, log forwarding to API will be disabled")

        self.api_url = api_url
        self.wallet = bt.wallet(config=self.config)
        self.hotkey = self.wallet.hotkey.ss58_address
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.log_queue: asyncio.Queue[dict[str, str | int | float]] = asyncio.Queue()
        self._shutdown = False
        self._flush_task = None
        self._session = None  # Will store the aiohttp session
        self._session_lock = asyncio.Lock()  # Lock for session creation

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

    async def get_session(self) -> aiohttp.ClientSession:
        """Get an existing session or create a new one if needed"""
        async with self._session_lock:
            if not self._session or self._session.closed:
                self._session = aiohttp.ClientSession()
            return self._session

    async def send_logs_to_api(self, logs, message_prefix: str = "Log batch") -> None:
        """Send logs to the API with the given message prefix"""
        if not logs or not self.api_url:
            return

        current_time = datetime.now().isoformat()
        message = f"{message_prefix} containing {len(logs)} entries at {current_time}"
        signature = self.sign_message(message)

        api_endpoint = f"{self.api_url}/api/v1/validator/logging"
        session = await self.get_session()

        async with session.post(
            api_endpoint,
            json={"logs": logs},
            headers={
                "X-Hotkey": self.hotkey,
                "X-Signature": signature,
                "X-Message": message,
                "Content-Type": "application/json",
            },
        ) as response:
            if response.status != 200:
                logger.error(f"Failed to send logs to API: {await response.text()}")

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

                await self.send_logs_to_api(logs)

            except Exception as e:
                logger.error(f"Error in _flush_logs: {e}")

    def start(self):
        """Start the flush task"""
        if not self._flush_task:
            # Create the task without explicitly creating a session
            # The session will be created when needed in _flush_logs
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

        await self.send_logs_to_api(logs, "Final log batch")

        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
