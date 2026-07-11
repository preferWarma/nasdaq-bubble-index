"""Logging configuration helpers."""

from __future__ import annotations

import logging
import logging.config
from pathlib import Path


def default_log_config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "config" / "logging.conf"


def configure_logging(config_path: str | Path | None = None, log_level: str | None = None) -> None:
    path = Path(config_path) if config_path else default_log_config_path()
    if path.exists():
        logging.config.fileConfig(path, disable_existing_loggers=False)
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    if log_level:
        level = logging.getLevelName(log_level.upper())
        logging.getLogger().setLevel(level)
        logging.getLogger("bubble_index").setLevel(level)
