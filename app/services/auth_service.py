"""Authentication service.

Public API:
    login(session, username, password) -> User
    logout(session, user)
    change_password(session, user, old_pw, new_pw)
    has_permission(user, permission_code) -> bool
    require_permission(user, permission_code)
    require_override(session, permission_code, manager_username, manager_password)
"""
from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.permissions import (
    PermissionDenied,
    has_permission,
    require_permission,
    ROLE_MANAGER,
)
from app.core.security import (
    verify_password,
    hash_password,
    is_account_locked,
    compute_lockout,
)
from app.models.user import User


class AuthError(Exception):
    """Raised for authentication failures (wrong password, locked, inactive)."""


def _get_user(session: Session, username: str) -> Optional[User]:
    return session.query(User).filter_by(username=username).first()


def login(session: Session, username: str, password: str) -> User:
    """Authenticate user, update failed_attempts / locked_until, audit.

    Raises AuthError on failure.
    """
    user = _get_user(session, username)
    if user is None:
        raise AuthError("اسم المستخدم أو كلمة المرور غير صحيحة")

    if not user.is_active:
        raise AuthError("الحساب غير مفعّل")

    if is_account_locked(user.failed_attempts, user.locked_until):
        raise AuthError("الحساب مقفل مؤقتاً بسبب محاولات دخول متعددة فاشلة")

    if not verify_password(password, user.password_hash):
        user.failed_attempts += 1
        locked_until = compute_lockout(user.failed_attempts)
        if locked_until:
            user.locked_until = locked_until
            log_action(session, "account_locked", user_id=user.id,
                       table_name="users", record_id=user.id,
                       new_value={"reason": "too_many_failed_attempts"})
        session.commit()
        raise AuthError("اسم المستخدم أو كلمة المرور غير صحيحة")

    # Success — reset counters
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login = datetime.datetime.utcnow()
    log_action(session, "login", user_id=user.id, table_name="users", record_id=user.id)
    session.commit()
    return user


def logout(session: Session, user: User) -> None:
    """Record a logout audit event."""
    log_action(session, "logout", user_id=user.id, table_name="users", record_id=user.id)
    session.commit()


def change_password(session: Session, user: User, old_pw: str, new_pw: str) -> None:
    """Change user password after verifying the old one."""
    if not verify_password(old_pw, user.password_hash):
        raise AuthError("كلمة المرور القديمة غير صحيحة")
    user.password_hash = hash_password(new_pw)
    log_action(session, "change_password", user_id=user.id, table_name="users", record_id=user.id)
    session.commit()


def user_has_permission(user: User, permission_code: str) -> bool:
    """Return True if *user* holds *permission_code*."""
    return has_permission(user.permission_codes(), permission_code)


def require_user_permission(user: User, permission_code: str) -> None:
    """Raise PermissionDenied if *user* lacks *permission_code*."""
    require_permission(user.permission_codes(), permission_code, username=user.username)


def require_override(
    session: Session,
    acting_user: User,
    permission_code: str,
    manager_username: str,
    manager_password: str,
) -> User:
    """Require a manager to supply credentials to grant *permission_code*.

    Returns the manager User on success; raises AuthError / PermissionDenied on failure.
    """
    manager = login(session, manager_username, manager_password)
    if manager.role.name != ROLE_MANAGER:
        raise PermissionDenied(permission_code, manager.username)
    log_action(
        session, "manager_override",
        user_id=manager.id,
        table_name="users",
        record_id=acting_user.id,
        new_value={"permission": permission_code, "granted_to": acting_user.username},
    )
    session.commit()
    return manager

