"""Database seed: roles, permissions, default settings, initial manager user.

Run once on first startup (or in tests via seed_database()).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.permissions import (
    ROLE_MANAGER, ROLE_CASHIER, ROLE_WALLET_EMPLOYEE,
    MANAGER_PERMISSIONS, CASHIER_PERMISSIONS, WALLET_EMPLOYEE_PERMISSIONS,
)
from app.core.security import hash_password
from app.models.user import Role, RolePermission, User, Setting


DEFAULT_SETTINGS: dict[str, str] = {
    "shop_name": "محل الموبايلات",
    "shop_address": "",
    "shop_phone": "",
    "invoice_footer": "شكراً لتعاملكم معنا",
    "warranty_text": "الضمان وفق شروط الشركة المصنّعة",
    "cashier_discount_limit_pct": "5",
    "idle_lock_minutes": "10",
}


def _seed_roles(session: Session) -> dict[str, Role]:
    """Create roles and their permissions if they don't exist."""
    role_map: dict[str, Role] = {}
    role_perms = {
        ROLE_MANAGER: MANAGER_PERMISSIONS,
        ROLE_CASHIER: CASHIER_PERMISSIONS,
        ROLE_WALLET_EMPLOYEE: WALLET_EMPLOYEE_PERMISSIONS,
    }
    for role_name, perms in role_perms.items():
        role = session.query(Role).filter_by(name=role_name).first()
        if role is None:
            role = Role(name=role_name)
            session.add(role)
            session.flush()
        role_map[role_name] = role

        existing_codes = {rp.permission_code for rp in role.permissions}
        for code in perms:
            if code not in existing_codes:
                session.add(RolePermission(role_id=role.id, permission_code=code))
    return role_map


def _seed_settings(session: Session) -> None:
    """Insert default settings if missing."""
    for key, value in DEFAULT_SETTINGS.items():
        if session.query(Setting).filter_by(key=key).first() is None:
            session.add(Setting(key=key, value=value))


def _seed_default_manager(session: Session, role_map: dict[str, Role]) -> None:
    """Create default manager account if no manager exists."""
    manager_role = role_map[ROLE_MANAGER]
    if session.query(User).filter_by(role_id=manager_role.id).first() is None:
        session.add(User(
            username="admin",
            password_hash=hash_password("admin123"),
            full_name="مدير النظام",
            role_id=manager_role.id,
            is_active=True,
        ))


def seed_database(session: Session) -> None:
    """Idempotent seed: safe to call multiple times."""
    role_map = _seed_roles(session)
    _seed_settings(session)
    _seed_default_manager(session, role_map)
    session.commit()

