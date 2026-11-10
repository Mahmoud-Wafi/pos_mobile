"""Read access to the audit log."""
from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.core import clock
from app.core.permissions import PERM_AUDIT_VIEW, require_permission
from app.models.user import AuditLog, User


def list_entries(
    session: Session,
    actor: User,
    *,
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
    limit: int = 500,
) -> list[AuditLog]:
    require_permission(actor.permission_codes(), PERM_AUDIT_VIEW, actor.username)
    q = session.query(AuditLog)
    if user_id is not None:
        q = q.filter(AuditLog.user_id == user_id)
    if action:
        q = q.filter(AuditLog.action.ilike(f"%{action.strip()}%"))
    if start_date or end_date:
        s, e = clock.day_bounds_utc(start_date or end_date, end_date or start_date)
        q = q.filter(AuditLog.timestamp >= s, AuditLog.timestamp <= e)
    return q.order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()).limit(limit).all()
