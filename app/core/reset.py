"""Factory reset: an empty shop (no products, customers, sales ...) with only the default admin.

Used by ``scripts/reset_data.py``. The live database is replaced, so the app must be closed.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from app.config import BACKUP_DIR, DATA_DIR, DB_PATH, DECLARATIONS_DIR


def reset_database(db_path: Path = DB_PATH, backup_dir: Path = BACKUP_DIR, keep_backup: bool = True,
                   wipe_backups: bool = False, wipe_files: bool = False) -> Path | None:
    """Delete the database and create a fresh one (migrations + default admin / roles / settings).

    Returns the safety backup made first (None when there was nothing to back up or keep_backup is False).
    """
    from app.core import backup as backup_core
    from app.core import database, startup
    from app.core.seed import seed_database

    safety = None
    if Path(db_path).exists() and keep_backup:
        safety = backup_core.create_backup(db_path, backup_dir)
    database.get_engine().dispose()
    for suffix in ("", "-wal", "-shm", "-journal"):
        Path(str(db_path) + suffix).unlink(missing_ok=True)
    if wipe_backups and Path(backup_dir).exists():
        for f in Path(backup_dir).iterdir():
            if f.is_file() and f != safety:
                f.unlink()
    if wipe_files and Path(DECLARATIONS_DIR).exists():
        shutil.rmtree(DECLARATIONS_DIR, ignore_errors=True)
    startup.run_migrations()
    with database.session_scope() as session:
        seed_database(session)
    return safety


def data_dir() -> Path:
    return DATA_DIR
