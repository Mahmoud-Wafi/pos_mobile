"""Permission-checked, audited backup operations (backup.manage)."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.core import backup as core
from app.core.audit import log_action
from app.core.permissions import PERM_BACKUP_MANAGE, require_permission
from app.models.user import User
from app.i18n import ar
from app.services import settings_service


def create(session: Session, actor: User) -> Path:
    require_permission(actor.permission_codes(), PERM_BACKUP_MANAGE, actor.username)
    path = core.create_backup()
    core.prune_backups(retention(session))
    offsite = offsite_dir(session)
    if offsite:
        try:
            core.copy_offsite(path, offsite, retention(session))
        except core.BackupError:
            pass                                  # recorded in the status file; the local backup stands
    log_action(session, "create_backup", user_id=actor.id, table_name="backup", new_value={"file": path.name})
    session.commit()
    return path


def listing(session: Session, actor: User) -> list[Path]:
    require_permission(actor.permission_codes(), PERM_BACKUP_MANAGE, actor.username)
    return core.list_backups()


def restore(session: Session, actor: User, backup_path: Path) -> Path | None:
    """Verify and restore. The audit row is written first (the live DB is replaced afterwards)."""
    require_permission(actor.permission_codes(), PERM_BACKUP_MANAGE, actor.username)
    core.verify_backup(backup_path)                       # fail early, before touching anything
    log_action(session, "restore_backup", user_id=actor.id, table_name="backup",
               new_value={"file": Path(backup_path).name})
    session.commit()
    session.close()
    return core.restore_backup(backup_path)


def retention(session: Session) -> int:
    try:
        return max(1, int(settings_service.get(session, "backup_retention", "14")))
    except ValueError:
        return 14


def auto_enabled(session: Session) -> bool:
    return settings_service.get(session, "auto_backup", "1") != "0"


def offsite_dir(session: Session) -> str:
    return settings_service.get(session, "offsite_backup_dir", "").strip()


def copy_offsite_now(session: Session, actor: User) -> Path:
    """Copy the newest backup to the off-site folder. Raises BackupError (Arabic) on failure."""
    require_permission(actor.permission_codes(), PERM_BACKUP_MANAGE, actor.username)
    latest = core.list_backups()
    if not latest:
        raise core.BackupError(ar.NO_BACKUP_YET)
    final = core.copy_offsite(latest[0], offsite_dir(session), retention(session))
    log_action(session, "offsite_backup", user_id=actor.id, table_name="backup", new_value={"file": final.name})
    session.commit()
    return final
