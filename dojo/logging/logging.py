import logging as python_logging

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


def get_log_level(config):
    try:
        if config.logging.trace:
            return "TRACE"
        elif config.logging.debug:
            return "DEBUG"
    except Exception as e:
        print(f"Failed to configure logging: {str(e)}")
    return "INFO"


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

    # Configures the root logger
    python_logging.root.handlers.clear()
    python_logging.root.setLevel(level)
    python_logging.root.addHandler(InterceptHandler())

    # Configures the named loggers
    # Disable propagation to prevent duplicate logs and add the InterceptHandler
    for name in python_logging.root.manager.loggerDict:
        python_logging.getLogger(name).propagate = False
        python_logging.getLogger(name).handlers.clear()
        python_logging.getLogger(name).addHandler(InterceptHandler())


# Function to configure logger with given level
def configure_logger(level):
    logger.remove()
    logger.add(
        sink=lambda msg: print(msg, end="", flush=True),
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level:^15}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
        level=level,
        filter=forwarded_log_filter,
    )


# Clears the default loguru handler and then add a customised version
forwarded_log_filter = ForwardedLogFilter()

# Set default level to INFO to avoid dealing with circular imports.
# Reconfigure it in miner or validator code as necessary
configure_logger("INFO")
