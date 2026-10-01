from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from typing import TYPE_CHECKING

from offsponsr.config import user_config_dir

if TYPE_CHECKING:
    from pathlib import Path

LOG_NAME = 'offsponsr.log'
FORMAT = '%(asctime)s %(levelname)s %(name)s: %(message)s'


def setup_logging(*, console: bool = False) -> Path:
    """Send the app's log to a file in the user's config directory; returns the file's path."""
    path = user_config_dir() / LOG_NAME
    path.parent.mkdir(parents=True, exist_ok=True)

    handlers: list[logging.Handler] = [RotatingFileHandler(path, maxBytes=1_000_000, backupCount=2, encoding='utf-8')]
    if console:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, format=FORMAT, handlers=handlers, force=True)
    return path
