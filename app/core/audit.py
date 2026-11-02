"""Audit log helper.

Call `log_action(session, ...)` inside an open transaction; the log entry
is committed together with the operation it records.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from app.models.user import AuditLog


def log_action(
    session,
    action: str,
    user_id: Optional[int] = None,
    table_name: Optional[str] = None,
    record_id: Optional[int] = None,
    old_value: Optional[Any] = None,
    new_value: Optional[Any] = None,
    reason: Optional[str] = None,
) -> AuditLog:
    """Create and add an AuditLog entry to *session* (not yet committed)."""
    entry = AuditLog(
        user_id=user_id,
        action=action,
        table_name=table_name,
        record_id=record_id,
        old_value=json.dumps(old_value, ensure_ascii=False) if old_value is not None else None,
        new_value=json.dumps(new_value, ensure_ascii=False) if new_value is not None else None,
        reason=reason,
    )
    session.add(entry)
    return entry
