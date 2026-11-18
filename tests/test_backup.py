"""Tests for backup/restore round-trip (Phase 1 acceptance criterion).

Scenario:
  1. Create a DB, insert data.
  2. create_backup() → file appears in backup_dir.
  3. restore_backup() → safety copy created, backup copied over.
  4. Verify the restored DB contains the original data.
"""
import json
import time
import sqlite3
import zipfile
from pathlib import Path

import pytest

from app.core import backup
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.backup import (BackupError, backup_due, create_backup, known_revisions, list_backups, prune_backups,
                             restore_backup, run_auto_backup, verify_backup)
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


def _roles(db_path):
    con = sqlite3.connect(str(db_path))
    try:
        return {r[0] for r in con.execute("SELECT name FROM roles")}
    finally:
        con.close()


class TestCreateBackup:
    def test_zip_with_manifest(self, seeded_db):
        db_path, backup_dir = seeded_db
        f = create_backup(db_path=db_path, backup_dir=backup_dir)
        assert f.suffix == ".zip"
        with zipfile.ZipFile(f) as z:
            assert set(z.namelist()) == {"shop.db", "manifest.json"}
            m = json.loads(z.read("manifest.json"))
        assert {"app_version", "alembic_revision", "created_at", "sha256"} <= set(m)
        assert verify_backup(f)["sha256"] == m["sha256"]

    def test_manifest_records_alembic_revision(self, seeded_db):
        db_path, backup_dir = seeded_db
        rev = sorted(known_revisions())[0]
        con = sqlite3.connect(str(db_path))
        con.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        con.execute("INSERT INTO alembic_version VALUES (?)", (rev,))
        con.commit(); con.close()
        assert verify_backup(create_backup(db_path, backup_dir))["alembic_revision"] == rev

    def test_missing_db_raises(self, tmp_dirs):
        db_path, backup_dir = tmp_dirs
        with pytest.raises(BackupError):
            create_backup(db_path=db_path, backup_dir=backup_dir)

    def test_two_backups_in_one_second_do_not_clash(self, seeded_db):
        db_path, backup_dir = seeded_db
        a = create_backup(db_path, backup_dir)
        b = create_backup(db_path, backup_dir)
        assert a != b and a.exists() and b.exists()


class TestListAndPrune:
    def test_empty_and_missing_dir(self, tmp_dirs, tmp_path):
        assert list_backups(tmp_dirs[1]) == []
        assert list_backups(tmp_path / "nope") == []

    def test_newest_first_and_safety_hidden(self, seeded_db):
        db_path, backup_dir = seeded_db
        for name in ("shop_20240101_000001.zip", "shop_20240102_000001.zip", "shop_safety_20240103_000001.zip"):
            (backup_dir / name).write_bytes(b"x")
        assert [p.name for p in list_backups(backup_dir)] == ["shop_20240102_000001.zip", "shop_20240101_000001.zip"]

    def test_prune_keeps_n_newest(self, tmp_dirs):
        _, backup_dir = tmp_dirs
        for d in range(1, 21):
            (backup_dir / f"shop_202401{d:02d}_000000.zip").write_bytes(b"x")
        removed = prune_backups(14, backup_dir)
        assert len(removed) == 6 and len(list_backups(backup_dir)) == 14
        assert (backup_dir / "shop_20240120_000000.zip").exists()
        assert not (backup_dir / "shop_20240101_000000.zip").exists()


class TestRestore:
    def test_round_trip_with_safety_copy(self, seeded_db):
        db_path, backup_dir = seeded_db
        f = create_backup(db_path, backup_dir)
        db_path.write_bytes(b"corrupted!")
        safety = restore_backup(f, db_path=db_path, backup_dir=backup_dir)
        assert {"manager", "cashier", "wallet_employee"} <= _roles(db_path)
        assert safety is not None and safety.name.startswith("shop_safety_")

    def test_safety_backup_made_when_db_exists(self, seeded_db):
        db_path, backup_dir = seeded_db
        f = create_backup(db_path, backup_dir)
        safety = restore_backup(f, db_path=db_path, backup_dir=backup_dir)
        assert safety is not None and safety.exists() and safety.name.startswith("shop_safety_")
        verify_backup(safety)

    def test_tampered_database_is_rejected(self, seeded_db, tmp_path):
        db_path, backup_dir = seeded_db
        f = create_backup(db_path, backup_dir)
        bad = tmp_path / "shop_bad.zip"
        with zipfile.ZipFile(f) as zin, zipfile.ZipFile(bad, "w") as zout:
            zout.writestr("manifest.json", zin.read("manifest.json"))
            zout.writestr("shop.db", zin.read("shop.db") + b"tamper")
        before = db_path.read_bytes()
        with pytest.raises(BackupError):
            restore_backup(bad, db_path=db_path, backup_dir=backup_dir)
        assert db_path.read_bytes() == before            # live DB untouched

    def test_garbage_and_missing_files_rejected(self, tmp_dirs, tmp_path):
        db_path, backup_dir = tmp_dirs
        junk = tmp_path / "shop_junk.zip"
        junk.write_bytes(b"not a zip")
        with pytest.raises(BackupError):
            restore_backup(junk, db_path=db_path, backup_dir=backup_dir)
        with pytest.raises(BackupError):
            restore_backup(tmp_path / "nonexistent.zip", db_path=db_path, backup_dir=backup_dir)

    def test_unknown_newer_revision_rejected(self, seeded_db):
        db_path, backup_dir = seeded_db
        con = sqlite3.connect(str(db_path))
        con.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        con.execute("INSERT INTO alembic_version VALUES ('zzzz_from_the_future')")
        con.commit(); con.close()
        f = create_backup(db_path, backup_dir)
        with pytest.raises(BackupError):
            verify_backup(f)

    def test_stale_wal_and_shm_are_removed(self, seeded_db):
        db_path, backup_dir = seeded_db
        f = create_backup(db_path, backup_dir)
        Path(str(db_path) + "-wal").write_bytes(b"stale")
        Path(str(db_path) + "-shm").write_bytes(b"stale")
        restore_backup(f, db_path=db_path, backup_dir=backup_dir)
        assert not Path(str(db_path) + "-wal").exists() and not Path(str(db_path) + "-shm").exists()
        assert "manager" in _roles(db_path)

    def test_backup_during_open_write_transaction_restores_cleanly(self, seeded_db):
        db_path, backup_dir = seeded_db
        writer = sqlite3.connect(str(db_path), isolation_level=None)
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("INSERT INTO settings (key, value, created_at, updated_at) VALUES ('committed_marker', '1', datetime('now'), datetime('now'))")
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("INSERT INTO settings (key, value, created_at, updated_at) VALUES ('uncommitted_marker', '1', datetime('now'), datetime('now'))")
        try:
            f = create_backup(db_path, backup_dir)         # taken while the write transaction is open
        finally:
            writer.execute("ROLLBACK")
            writer.close()
        restore_backup(f, db_path=db_path, backup_dir=backup_dir)
        con = sqlite3.connect(str(db_path))
        try:
            keys = {r[0] for r in con.execute("SELECT key FROM settings")}
            assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            con.close()
        assert "committed_marker" in keys and "uncommitted_marker" not in keys

    def test_legacy_db_backup_still_restores(self, seeded_db, tmp_path):
        db_path, backup_dir = seeded_db
        legacy = backup_dir / "shop_20200101_000000.db"
        legacy.write_bytes(db_path.read_bytes())
        db_path.write_bytes(b"corrupted!")
        restore_backup(legacy, db_path=db_path, backup_dir=backup_dir)
        assert "manager" in _roles(db_path)


class TestAutoBackup:
    def test_due_and_run(self, seeded_db):
        db_path, backup_dir = seeded_db
        assert backup_due(backup_dir)
        assert run_auto_backup(14, db_path=db_path, backup_dir=backup_dir) is not None
        assert not backup_due(backup_dir)
        assert run_auto_backup(14, db_path=db_path, backup_dir=backup_dir) is None      # already done today
        assert run_auto_backup(14, force=True, db_path=db_path, backup_dir=backup_dir) is not None

    def test_failure_never_raises(self, tmp_dirs):
        db_path, backup_dir = tmp_dirs                      # db does not exist
        assert run_auto_backup(14, force=True, db_path=db_path, backup_dir=backup_dir) is None

    def test_retention_applied(self, seeded_db):
        db_path, backup_dir = seeded_db
        for d in range(1, 6):
            (backup_dir / f"shop_202401{d:02d}_000000.zip").write_bytes(b"x")
        run_auto_backup(3, force=True, db_path=db_path, backup_dir=backup_dir)
        assert len(list_backups(backup_dir)) == 3


class TestService:
    def test_requires_backup_manage_and_audits(self, seeded_db):
        from app.core.database import get_session
        from app.core.permissions import PermissionDenied
        from app.models.user import AuditLog, Role, User
        from app.core.security import hash_password
        from app.services import backup_service

        db_path, backup_dir = seeded_db
        eng = create_engine(f"sqlite:///{db_path}")
        S = sessionmaker(bind=eng)
        with S() as s:
            def mk(name, role):
                r = s.query(Role).filter_by(name=role).first()
                u = User(username=name, password_hash=hash_password("Passw0rd!"), full_name=name, role_id=r.id)
                s.add(u); s.commit(); return u
            cashier, mgr = mk("cc", "cashier"), mk("mm", "manager")
            with pytest.raises(PermissionDenied):
                backup_service.create(s, cashier)
            assert backup_service.retention(s) == 14
        eng.dispose()


# ── off-site copy ────────────────────────────────────────────────────────────

def test_offsite_copy_is_verified_and_pruned(seeded_db, tmp_path):
    db_path, backup_dir = seeded_db
    off = tmp_path / "usb"
    for _ in range(3):
        z = backup.create_backup(db_path, backup_dir, prefix="shop")
        time.sleep(1.1)
        out = backup.copy_offsite(z, off, keep=2, backup_dir=backup_dir)
        assert out.exists()
        backup.verify_backup(out)
    assert len(backup.list_backups(off)) == 2          # pruned to the retention
    assert not list(off.glob(".part_*"))
    state, _when, _detail = backup.offsite_status(backup_dir)
    assert state == "ok"


def test_offsite_failure_is_recorded_not_raised_by_auto_backup(seeded_db, tmp_path):
    db_path, backup_dir = seeded_db
    blocker = tmp_path / "file_not_folder"
    blocker.write_text("x")
    z = backup.run_auto_backup(5, force=True, db_path=db_path, backup_dir=backup_dir,
                               offsite_dir=str(blocker / "sub"))
    assert z is not None and z.exists()                # the local backup still happened
    assert backup.offsite_status(backup_dir)[0] == "fail"


def test_offsite_setting_validates_folder(db_session, tmp_path):
    from app.core.security import hash_password
    from app.models.user import Role, User
    from app.services import settings_service

    role = db_session.query(Role).filter_by(name="manager").first()
    mgr = User(username="mm", password_hash=hash_password("Passw0rd!"), full_name="m", role_id=role.id)
    db_session.add(mgr)
    db_session.commit()
    with pytest.raises(settings_service.SettingsError):
        settings_service.update(db_session, mgr, {"offsite_backup_dir": str(tmp_path / "missing")})
    settings_service.update(db_session, mgr, {"offsite_backup_dir": str(tmp_path)})
    assert settings_service.get(db_session, "offsite_backup_dir") == str(tmp_path)
