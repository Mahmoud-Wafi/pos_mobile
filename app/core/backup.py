"""Backup and restore of the SQLite database.

A backup is a zip file ``shop_YYYYmmdd_HHMMSS.zip`` holding ``shop.db`` (made with SQLite's online
backup API, so it is consistent even while the app is writing) and ``manifest.json`` with the app
version, Alembic revision, creation time (UTC) and the sha256 of the database file.

Restore verifies the zip, the sha256, SQLite ``integrity_check`` and that the revision is known to
this version of the app; it keeps a safety backup of the current database, disposes the engine,
removes stale ``-wal`` / ``-shm`` files and replaces the file atomically.

Permission checks live in ``app/services/backup_service.py``; this module is the low-level part.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from app.config import APP_VERSION, BACKUP_DIR, BASE_DIR, DB_PATH
from app.i18n import ar

DB_MEMBER = "shop.db"
MANIFEST = "manifest.json"
FORMAT = 1


class BackupError(Exception):
    """Business error with an Arabic message that can be shown to the user."""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _integrity_ok(db_file: Path) -> bool:
    con = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
    try:
        return con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    except sqlite3.DatabaseError:
        return False
    finally:
        con.close()


def _revision_of(db_file: Path) -> str | None:
    con = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
    try:
        row = con.execute("SELECT version_num FROM alembic_version").fetchone()
        return row[0] if row else None
    except sqlite3.DatabaseError:
        return None
    finally:
        con.close()


def known_revisions() -> set[str]:
    """Every Alembic revision this version of the app knows about."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "migrations"))
    return {rev.revision for rev in ScriptDirectory.from_config(cfg).walk_revisions()}


def _stamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def _unique(path: Path) -> Path:
    n, base = 1, path
    while path.exists():
        path = base.with_name(f"{base.stem}_{n}{base.suffix}")
        n += 1
    return path


# ── create ────────────────────────────────────────────────────────────────────
def create_backup(db_path: Path = DB_PATH, backup_dir: Path = BACKUP_DIR, prefix: str = "shop") -> Path:
    """Write a verified zip backup of the live database and return its path."""
    db_path = Path(db_path)
    if not db_path.exists():
        raise BackupError("ملف قاعدة البيانات غير موجود")
    backup_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=backup_dir) as tmp:
        snapshot = Path(tmp) / DB_MEMBER
        src = sqlite3.connect(str(db_path))
        dst = sqlite3.connect(str(snapshot))
        try:
            src.backup(dst)            # online backup: consistent snapshot of committed data
        finally:
            dst.close()
            src.close()
        if not _integrity_ok(snapshot):
            raise BackupError("فشل فحص سلامة النسخة الاحتياطية؛ لم يتم حفظها")
        manifest = {
            "format": FORMAT,
            "app_version": APP_VERSION,
            "alembic_revision": _revision_of(snapshot),
            "created_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sha256": _sha256(snapshot),
        }
        dest = _unique(backup_dir / f"{prefix}_{_stamp()}.zip")
        partial = dest.with_suffix(".part")
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(snapshot, DB_MEMBER)
            z.writestr(MANIFEST, json.dumps(manifest, indent=2))
        os.replace(partial, dest)
    return dest


# ── list / prune ──────────────────────────────────────────────────────────────
def list_backups(backup_dir: Path = BACKUP_DIR) -> list[Path]:
    """Regular backups (zip, plus legacy .db), newest first. Safety copies are not listed."""
    if not backup_dir.exists():
        return []
    files = [p for p in backup_dir.iterdir()
             if p.name.startswith("shop_") and not p.name.startswith("shop_safety_")
             and p.suffix in (".zip", ".db")]
    return sorted(files, key=lambda p: p.name, reverse=True)


def prune_backups(keep: int, backup_dir: Path = BACKUP_DIR) -> list[Path]:
    """Delete the oldest regular backups beyond ``keep``. Returns what was removed."""
    removed = []
    for old in list_backups(backup_dir)[max(1, keep):]:
        old.unlink(missing_ok=True)
        removed.append(old)
    return removed


def last_backup_time(backup_dir: Path = BACKUP_DIR) -> datetime.datetime | None:
    """Local time of the newest backup, or None."""
    files = list_backups(backup_dir)
    if not files:
        return None
    return datetime.datetime.fromtimestamp(files[0].stat().st_mtime)


def backup_due(backup_dir: Path = BACKUP_DIR, now: datetime.datetime | None = None) -> bool:
    """True when no backup exists for today (local date)."""
    last = last_backup_time(backup_dir)
    return last is None or last.date() < (now or datetime.datetime.now()).date()


# ── verify / restore ──────────────────────────────────────────────────────────
def verify_backup(backup_path: Path, extract_to: Path | None = None) -> dict:
    """Check a backup file; returns its manifest. Raises BackupError if it is unusable.

    When ``extract_to`` is given the verified database is left there as ``shop.db``.
    """
    backup_path = Path(backup_path)
    if not backup_path.exists():
        raise BackupError("ملف النسخة الاحتياطية غير موجود")
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(extract_to) if extract_to else Path(tmp)
        work.mkdir(parents=True, exist_ok=True)
        db_file = work / DB_MEMBER
        if backup_path.suffix == ".zip":
            try:
                with zipfile.ZipFile(backup_path) as z:
                    names = set(z.namelist())
                    if names != {DB_MEMBER, MANIFEST}:
                        raise BackupError("محتوى ملف النسخة الاحتياطية غير صحيح")
                    manifest = json.loads(z.read(MANIFEST))
                    with z.open(DB_MEMBER) as src, open(db_file, "wb") as out:
                        while chunk := src.read(1 << 20):
                            out.write(chunk)
            except (zipfile.BadZipFile, json.JSONDecodeError, KeyError) as exc:
                raise BackupError("ملف النسخة الاحتياطية تالف أو غير صالح") from exc
            if manifest.get("sha256") != _sha256(db_file):
                raise BackupError("ملف النسخة الاحتياطية تم تعديله أو تلف (فشل فحص البصمة)")
        else:   # legacy plain .db backup from earlier versions
            db_file.write_bytes(backup_path.read_bytes())
            manifest = {"format": 0, "alembic_revision": _revision_of(db_file)}
        if not _integrity_ok(db_file):
            raise BackupError("قاعدة البيانات داخل النسخة تالفة")
        rev = manifest.get("alembic_revision")
        if rev and rev not in known_revisions():
            raise BackupError("هذه النسخة من إصدار أحدث من البرنامج؛ حدّث البرنامج أولاً")
        if extract_to is not None and not (Path(extract_to) / DB_MEMBER).exists():
            raise BackupError("تعذر تجهيز النسخة للاستعادة")
        return manifest


def _dispose_engine() -> None:
    from app.core import database

    if database._engine is not None:
        database._engine.dispose()


def _safety_copy(db_path: Path, backup_dir: Path) -> Path | None:
    """Keep the current database before it is replaced; a damaged one is copied as-is."""
    if not db_path.exists():
        return None
    try:
        return create_backup(db_path, backup_dir, prefix="shop_safety")
    except (BackupError, sqlite3.DatabaseError):
        import shutil

        backup_dir.mkdir(parents=True, exist_ok=True)
        dest = _unique(backup_dir / f"shop_safety_{_stamp()}.damaged.db")
        shutil.copy2(db_path, dest)
        return dest


def restore_backup(backup_path: Path, db_path: Path = DB_PATH, backup_dir: Path | None = None) -> Path | None:
    """Replace ``db_path`` with the verified backup. Returns the safety backup of the old database.

    The caller must close its own sessions first and restart the app afterwards.
    """
    db_path = Path(db_path)
    backup_dir = Path(backup_dir) if backup_dir else db_path.parent / "backups"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    staging = db_path.parent / f".restore_{_stamp()}"
    try:
        verify_backup(backup_path, extract_to=staging)
        safety = _safety_copy(db_path, backup_dir)
        _dispose_engine()
        for suffix in ("-wal", "-shm"):
            Path(str(db_path) + suffix).unlink(missing_ok=True)
        os.replace(staging / DB_MEMBER, db_path)
        return safety
    finally:
        for f in staging.glob("*"):
            f.unlink(missing_ok=True)
        if staging.exists():
            staging.rmdir()


OFFSITE_STATUS_FILE = "offsite_status.txt"


def copy_offsite(zip_path: Path, dest_dir: Path | str, keep: int = 14, backup_dir: Path = BACKUP_DIR) -> Path:
    """Copy a backup zip to another folder (USB drive, synced cloud folder) and verify the copy.

    The copy is written under a temporary name and renamed only after it verifies, so a half-written
    file never looks like a good backup. The result is recorded for the status bar.
    """
    import shutil

    dest = Path(dest_dir)
    try:
        if not str(dest_dir).strip():
            raise BackupError(ar.OFFSITE_NOT_SET)
        dest.mkdir(parents=True, exist_ok=True)
        tmp = dest / (".part_" + zip_path.name)
        shutil.copy2(zip_path, tmp)
        try:
            verify_backup(tmp)
        except BackupError:
            tmp.unlink(missing_ok=True)
            raise
        final = dest / zip_path.name
        os.replace(tmp, final)
        prune_backups(keep, dest)
        _write_offsite_status(backup_dir, True, str(dest))
        return final
    except BackupError as exc:
        _write_offsite_status(backup_dir, False, str(exc))
        raise
    except OSError as exc:
        _write_offsite_status(backup_dir, False, str(exc))
        raise BackupError(ar.OFFSITE_FAILED) from exc


def _write_offsite_status(backup_dir: Path, ok: bool, detail: str) -> None:
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        (backup_dir / OFFSITE_STATUS_FILE).write_text(f"{'ok' if ok else 'fail'}|{stamp}|{detail}", encoding="utf-8")
    except OSError:
        pass


def offsite_status(backup_dir: Path = BACKUP_DIR) -> tuple[str, str, str] | None:
    """(state, time, detail) of the last off-site copy; state is 'ok' or 'fail'. None if never tried."""
    try:
        state, when, detail = (backup_dir / OFFSITE_STATUS_FILE).read_text(encoding="utf-8").split("|", 2)
        return state, when, detail
    except (OSError, ValueError):
        return None


def run_auto_backup(retention: int = 14, force: bool = False, db_path: Path = DB_PATH,
                    backup_dir: Path = BACKUP_DIR, offsite_dir: str = "") -> Path | None:
    """Daily / on-close backup: creates one when due (or forced), then prunes. Never raises."""
    import logging

    try:
        if not force and not backup_due(backup_dir):
            return None
        path = create_backup(db_path, backup_dir)
        prune_backups(retention, backup_dir)
        if offsite_dir.strip():
            try:
                copy_offsite(path, offsite_dir, retention, backup_dir)
            except Exception:   # the local backup succeeded; the failure is recorded for the status bar
                import logging as _lg
                _lg.getLogger("pos").exception("off-site backup copy failed")
        return path
    except Exception:           # a failed automatic backup must never stop the shop working
        logging.getLogger("pos").exception("automatic backup failed")
        return None
