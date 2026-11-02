"""Tests for backup/restore round-trip (Phase 1 acceptance criterion).

Scenario:
  1. Create a DB, insert data.
  2. create_backup() → file appears in backup_dir.
  3. restore_backup() → safety copy created, backup copied over.
  4. Verify the restored DB contains the original data.
"""
import shutil
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.backup import create_backup, list_backups, restore_backup
from app.core.database import Base, override_engine
from app.core.seed import seed_database


@pytest.fixture
def tmp_dirs(tmp_path):
    """Return (db_path, backup_dir) inside a temp directory."""
    db_path = tmp_path / "shop.db"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    return db_path, backup_dir


@pytest.fixture
def seeded_db(tmp_dirs):
    """Create a seeded SQLite file at db_path; return (engine, db_path, backup_dir)."""
    db_path, backup_dir = tmp_dirs
    from sqlalchemy import event

    engine = create_engine(f"sqlite:///{db_path}", echo=False)

    def _pragmas(conn, _rec):
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    event.listen(engine, "connect", _pragmas)
    override_engine(engine)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as session:
        seed_database(session)
    engine.dispose()
    return db_path, backup_dir


class TestCreateBackup:
    def test_creates_file(self, seeded_db):
        db_path, backup_dir = seeded_db
        backup_file = create_backup(db_path=db_path, backup_dir=backup_dir)
        assert backup_file.exists()
        assert backup_file.suffix == ".db"

    def test_file_in_backup_dir(self, seeded_db):
        db_path, backup_dir = seeded_db
        backup_file = create_backup(db_path=db_path, backup_dir=backup_dir)
        assert backup_file.parent == backup_dir

    def test_raises_if_db_missing(self, tmp_dirs):
        db_path, backup_dir = tmp_dirs
        with pytest.raises(FileNotFoundError):
            create_backup(db_path=db_path, backup_dir=backup_dir)


class TestListBackups:
    def test_empty_dir(self, tmp_dirs):
        _, backup_dir = tmp_dirs
        assert list_backups(backup_dir) == []

    def test_lists_newest_first(self, seeded_db):
        import time
        db_path, backup_dir = seeded_db
        b1 = create_backup(db_path=db_path, backup_dir=backup_dir)
        time.sleep(1.1)  # ensure different timestamp
        b2 = create_backup(db_path=db_path, backup_dir=backup_dir)
        backups = list_backups(backup_dir)
        assert backups[0] == b2  # newest first
        assert backups[1] == b1

    def test_non_existent_dir_returns_empty(self, tmp_path):
        assert list_backups(tmp_path / "nonexistent") == []


class TestRestoreBackup:
    def test_round_trip(self, seeded_db):
        """Backup → restore → data intact."""
        db_path, backup_dir = seeded_db

        # Take backup
        backup_file = create_backup(db_path=db_path, backup_dir=backup_dir)

        # Corrupt the DB by truncating it
        db_path.write_bytes(b"corrupted!")

        # Restore
        safety = restore_backup(backup_path=backup_file, db_path=db_path)

        # Safety copy should exist
        assert safety is not None
        assert safety.exists()

        # Restored DB should be readable and contain roles
        from sqlalchemy import event as sa_event
        engine = create_engine(f"sqlite:///{db_path}", echo=False)
        override_engine(engine)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT name FROM roles ORDER BY name")).fetchall()
        engine.dispose()
        role_names = {row[0] for row in result}
        assert "manager" in role_names
        assert "cashier" in role_names
        assert "wallet_employee" in role_names

    def test_safety_copy_created_when_db_exists(self, seeded_db):
        db_path, backup_dir = seeded_db
        backup_file = create_backup(db_path=db_path, backup_dir=backup_dir)
        safety = restore_backup(backup_path=backup_file, db_path=db_path)
        assert safety is not None
        assert safety.exists()

    def test_raises_if_backup_missing(self, tmp_dirs):
        db_path, backup_dir = tmp_dirs
        with pytest.raises(FileNotFoundError):
            restore_backup(backup_path=backup_dir / "nonexistent.db", db_path=db_path)

    def test_no_safety_copy_if_db_absent(self, tmp_dirs):
        """If there's no existing DB, safety copy should be None."""
        db_path, backup_dir = tmp_dirs
        # Create a fake backup file to restore from
        fake_backup = backup_dir / "shop_20240101_120000.db"
        fake_backup.write_bytes(b"fake")
        safety = restore_backup(backup_path=fake_backup, db_path=db_path)
        assert safety is None

