"""Backup and restore for the SQLite database.

Public API:
    create_backup(db_path, backup_dir) -> Path   - copies the live DB to a timestamped file
    list_backups(backup_dir) -> list[Path]        - newest-first list of backup files
    restore_backup(backup_path, db_path)          - restores backup (saves safety copy first)

All paths use pathlib for cross-platform compatibility.
"""
from __future__ import annotations

import datetime
import shutil
from pathlib import Path

from app.config import BACKUP_DIR, DB_PATH


def create_backup(db_path: Path = DB_PATH, backup_dir: Path = BACKUP_DIR) -> Path:
    """Copy the live SQLite file to *backup_dir* with a timestamp name.

    Returns the path of the created backup.
    Raises FileNotFoundError if *db_path* does not exist.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"DB file not found: {db_path}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"shop_{ts}.db"
    shutil.copy2(db_path, dest)
    return dest


def list_backups(backup_dir: Path = BACKUP_DIR) -> list[Path]:
    """Return all *.db backup files in *backup_dir*, newest first."""
    if not backup_dir.exists():
        return []
    files = sorted(backup_dir.glob("shop_*.db"), reverse=True)
    return list(files)


def restore_backup(backup_path: Path, db_path: Path = DB_PATH) -> Path:
    """Restore *backup_path* over *db_path*.

    Before overwriting, the current DB is copied to a safety file.
    Returns the path of the safety copy.
    Raises FileNotFoundError if backup does not exist.
    """
    backup_path = Path(backup_path)
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_path}")

    # Create parent dir if needed
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Safety copy of the current DB (if it exists)
    safety_path: Path | None = None
    if db_path.exists():
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safety_path = db_path.parent / f"shop_safety_{ts}.db"
        shutil.copy2(db_path, safety_path)

    shutil.copy2(backup_path, db_path)
    return safety_path

