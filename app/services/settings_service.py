"""Shop settings (name, address, footer, warranty text, limits) with validation + audit."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.permissions import PERM_SETTINGS_MANAGE, require_permission
from app.core.seed import DEFAULT_SETTINGS
from app.models.user import Setting, User

# key -> (min, max) for integer settings
_INT_RANGES = {
    "cashier_discount_limit_pct": (0, 100),
    "idle_lock_minutes": (0, 1440),
}


class SettingsError(Exception):
    pass


def get_all(session: Session) -> dict[str, str]:
    """All settings with defaults filled in (no permission needed: receipts read these)."""
    values = dict(DEFAULT_SETTINGS)
    for row in session.query(Setting).all():
        values[row.key] = row.value or ""
    return values


def get(session: Session, key: str, default: str = "") -> str:
    row = session.query(Setting).filter_by(key=key).first()
    if row is not None and row.value is not None:
        return row.value
    return DEFAULT_SETTINGS.get(key, default)


def update(session: Session, actor: User, changes: dict[str, str]) -> None:
    require_permission(actor.permission_codes(), PERM_SETTINGS_MANAGE, actor.username)
    for key, value in changes.items():
        if key not in DEFAULT_SETTINGS:
            raise SettingsError(f"إعداد غير معروف: {key}")
        value = (value or "").strip()
        if key in _INT_RANGES:
            lo, hi = _INT_RANGES[key]
            try:
                number = int(value)
            except ValueError:
                raise SettingsError(f"القيمة يجب أن تكون رقماً صحيحاً: {key}") from None
            if not lo <= number <= hi:
                raise SettingsError(f"القيمة يجب أن تكون بين {lo} و {hi}: {key}")
            value = str(number)
        if key == "shop_name" and not value:
            raise SettingsError("اسم المحل مطلوب")
        row = session.query(Setting).filter_by(key=key).first()
        old = row.value if row else None
        if row is None:
            session.add(Setting(key=key, value=value))
        else:
            row.value = value
        if old != value:
            log_action(session, "update_setting", user_id=actor.id, table_name="settings",
                       old_value={key: old}, new_value={key: value})
    session.flush()
