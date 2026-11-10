"""User administration (manager only): create, edit, deactivate, reset password, unlock."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.permissions import PERM_USERS_MANAGE, ROLE_MANAGER, require_permission
from app.core.security import hash_password
from app.models.user import Role, User

MIN_PASSWORD_LEN = 6


class UserAdminError(Exception):
    """Business-rule violation while administering users."""


def _require(actor: User) -> None:
    require_permission(actor.permission_codes(), PERM_USERS_MANAGE, actor.username)


def list_users(session: Session, actor: User) -> list[User]:
    _require(actor)
    return session.query(User).order_by(User.username).all()


def list_roles(session: Session, actor: User) -> list[Role]:
    _require(actor)
    return session.query(Role).order_by(Role.name).all()


def _check_password(pw: str) -> None:
    if len(pw or "") < MIN_PASSWORD_LEN:
        raise UserAdminError("كلمة المرور يجب أن تكون 6 خانات على الأقل")


def _active_managers(session: Session) -> int:
    return (
        session.query(User).join(Role, User.role_id == Role.id)
        .filter(Role.name == ROLE_MANAGER, User.is_active.is_(True)).count()
    )


def create_user(session: Session, actor: User, username: str, full_name: str,
                role_id: int, password: str) -> User:
    _require(actor)
    username = (username or "").strip()
    if not username or not (full_name or "").strip():
        raise UserAdminError("اسم المستخدم والاسم الكامل مطلوبان")
    if session.query(User).filter_by(username=username).first():
        raise UserAdminError(f"اسم المستخدم '{username}' مستخدم بالفعل")
    if session.get(Role, role_id) is None:
        raise UserAdminError("الدور غير موجود")
    _check_password(password)
    user = User(username=username, full_name=full_name.strip(), role_id=role_id,
                password_hash=hash_password(password), is_active=True, created_by=actor.id)
    session.add(user)
    session.flush()
    log_action(session, "create_user", user_id=actor.id, table_name="users", record_id=user.id,
               new_value={"username": username, "role_id": role_id})
    return user


def update_user(session: Session, actor: User, user_id: int, *, full_name: Optional[str] = None,
                role_id: Optional[int] = None, is_active: Optional[bool] = None) -> User:
    _require(actor)
    user = session.get(User, user_id)
    if user is None:
        raise UserAdminError("المستخدم غير موجود")
    old = {"full_name": user.full_name, "role_id": user.role_id, "is_active": user.is_active}

    if is_active is False and user.id == actor.id:
        raise UserAdminError("لا يمكنك تعطيل حسابك الحالي")

    new_role = session.get(Role, role_id) if role_id is not None else user.role
    if role_id is not None and new_role is None:
        raise UserAdminError("الدور غير موجود")

    # never leave the shop without an active manager
    was_active_manager = user.is_active and user.role.name == ROLE_MANAGER
    will_be_active_manager = (user.is_active if is_active is None else is_active) and new_role.name == ROLE_MANAGER
    if was_active_manager and not will_be_active_manager and _active_managers(session) <= 1:
        raise UserAdminError("يجب أن يبقى مدير نشط واحد على الأقل")

    if full_name is not None:
        if not full_name.strip():
            raise UserAdminError("الاسم الكامل مطلوب")
        user.full_name = full_name.strip()
    if role_id is not None:
        user.role_id = role_id
    if is_active is not None:
        user.is_active = is_active
    session.flush()
    session.expire(user, ["role"])   # role_id changed: drop the cached relationship
    log_action(session, "update_user", user_id=actor.id, table_name="users", record_id=user.id,
               old_value=old,
               new_value={"full_name": user.full_name, "role_id": user.role_id, "is_active": user.is_active})
    return user


def reset_password(session: Session, actor: User, user_id: int, new_password: str) -> None:
    _require(actor)
    user = session.get(User, user_id)
    if user is None:
        raise UserAdminError("المستخدم غير موجود")
    _check_password(new_password)
    user.password_hash = hash_password(new_password)
    user.failed_attempts = 0
    user.locked_until = None
    log_action(session, "reset_password", user_id=actor.id, table_name="users", record_id=user.id)
    session.flush()


def unlock_user(session: Session, actor: User, user_id: int) -> None:
    _require(actor)
    user = session.get(User, user_id)
    if user is None:
        raise UserAdminError("المستخدم غير موجود")
    user.failed_attempts = 0
    user.locked_until = None
    log_action(session, "unlock_user", user_id=actor.id, table_name="users", record_id=user.id)
    session.flush()
