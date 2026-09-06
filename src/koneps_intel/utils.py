"""Utilities for logging and secret sanitization."""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Optional

from koneps_intel.config import LOGS_DIR

_REDACTION_PATTERN = re.compile(r"(serviceKey=)([^&]+)", re.IGNORECASE)


def redact_sensitive(text: str) -> str:
    """Redact sensitive query parameters such as serviceKey from URLs and logs."""
    if not text or not isinstance(text, str):
        return text
    return _REDACTION_PATTERN.sub(r"\1[REDACTED]", text)


class SensitiveFilter(logging.Filter):
    """Logging filter ensuring serviceKey and tokens are never printed in plain text."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_sensitive(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: (redact_sensitive(v) if isinstance(v, str) else v)
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    (redact_sensitive(v) if isinstance(v, str) else v)
                    for v in record.args
                )
        return True


def get_logger(
    name: str = "koneps_intel",
    log_dir: Optional[Path] = None,
    log_filename: Optional[str] = None,
    level: int = logging.INFO,
) -> logging.Logger:
    """Configure and return a structured logger with both console and file handlers."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        # Console Handler
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(level)
        console_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        console.setFormatter(console_fmt)
        console.addFilter(SensitiveFilter())
        logger.addHandler(console)

        # File Handler (if log_dir is specified or default)
        target_dir = log_dir or LOGS_DIR
        if target_dir:
            target_dir.mkdir(parents=True, exist_ok=True)
            fname = log_filename or f"{name}.log"
            file_handler = logging.FileHandler(target_dir / fname, encoding="utf-8")
            file_handler.setLevel(level)
            file_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")
            file_handler.setFormatter(file_fmt)
            file_handler.addFilter(SensitiveFilter())
            logger.addHandler(file_handler)

    return logger
