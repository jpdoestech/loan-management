"""Centralised application logger.

All modules import ``get_logger(__name__)`` so that every log record
carries the originating module path.  A rotating file handler keeps the
log file below 5 MB with up to 3 backups.
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_DIR = Path(__file__).resolve().parents[2] / "data_files" / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = _LOG_DIR / "app.log"

_FMT = "%(asctime)s  %(levelname)-8s  %(name)-35s  %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"

logging.basicConfig(
    level=logging.DEBUG,
    format=_FMT,
    datefmt=_DATE_FMT,
    handlers=[
        RotatingFileHandler(
            _LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        ),
        logging.StreamHandler(),
    ],
)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger.

    Args:
        name: Typically ``__name__`` of the calling module.

    Returns:
        Configured :class:`logging.Logger` instance.
    """
    return logging.getLogger(name)
