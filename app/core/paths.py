"""Filesystem locations that work both from source and from a PyInstaller bundle."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "MobileShopPOS"


def resource_dir() -> Path:
    """Folder holding read-only bundled files (assets/, migrations/, alembic.ini)."""
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle)
    return Path(__file__).resolve().parent.parent.parent


def default_data_dir() -> Path:
    """Per-user writable data folder (DB, backups, logs, PDFs)."""
    override = os.environ.get("POS_DATA_DIR")
    if override:
        return Path(override)
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / APP_DIR_NAME
