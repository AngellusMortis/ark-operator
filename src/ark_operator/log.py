"""ARK Operator logging."""

import json
import logging
import sys
from typing import Literal

from rich.logging import RichHandler

LoggingFormat = Literal["rich", "json", "auto"]
LoggingLevel = Literal[
    "CRITICAL", "FATAL", "ERROR", "WARN", "WARNING", "INFO", "DEBUG", "NOTSET"
]
JSON_FIELDS = [
    "message",
    "levelname",
    "name",
    "asctime",
    "threadName",
    "module",
    "funcName",
    "levelno",
    "pathname",
    "lineno",
    "filename",
]


def init_logging(
    logging_format: LoggingFormat | None = None, level: LoggingLevel = "NOTSET"
) -> None:
    """
    Initialize logging.

    If not provided, will default to rich if on a TTY, otherwise, JSON. Value of `None`
    will skip logging setup.
    """

    if logging_format == "auto":
        # pretty logger when running with a TTY, JSON logger for Splunk
        logging_format = "rich" if (sys.stdin and sys.stdin.isatty()) else "json"

    match logging_format:
        case "rich":
            logging.basicConfig(
                level=level,
                format="%(message)s",
                datefmt="[%X]",
                handlers=[RichHandler()],
            )
        case "json":
            handler = logging.StreamHandler()
            format_str = "".join([f"%({m})" for m in JSON_FIELDS])
            formatter = json.JsonFormatter(format_str)  # type: ignore[attr-defined]
            handler.setFormatter(formatter)

            logging.basicConfig(
                level=level,
                format="%(message)s",
                handlers=[handler],
            )
