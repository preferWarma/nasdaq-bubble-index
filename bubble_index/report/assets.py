"""Static asset helpers for generated reports."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from .constants import STATIC_ASSET_FILES

logger = logging.getLogger(__name__)


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def static_assets_dir() -> Path:
    return project_root() / "static"


def copy_static_assets(out_dir: Path) -> None:
    source_dir = static_assets_dir()
    target_dir = out_dir / "static"
    target_dir.mkdir(parents=True, exist_ok=True)
    for filename in STATIC_ASSET_FILES:
        source = source_dir / filename
        if not source.exists():
            logger.warning("Static asset missing, interactive charts may not load: %s", source)
            continue
        shutil.copy2(source, target_dir / filename)
