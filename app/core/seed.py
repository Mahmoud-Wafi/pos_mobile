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


def _seed_cash_accounts(session: Session) -> None:
    """Seed default cash accounts: الدرج (drawer), الخزنة (safe)."""
    from app.models.accounting import CashAccount
    accounts = [
        ("الدرج", "drawer"),
        ("الخزنة", "safe"),
    ]
    for name, acct_type in accounts:
        if session.query(CashAccount).filter_by(name=name).first() is None:
            session.add(CashAccount(name=name, type=acct_type, balance=0))


def _seed_expense_categories(session: Session) -> None:
    """Seed standard expense categories."""
    from app.models.accounting import ExpenseCategory
    categories = [
        "إيجار المحل",
        "كهرباء ومرافق",
        "بوفيه وضيافة",
        "مرتبات ومكافآت",
        "أدوات نظافة ومطبوعات",
        "صيانة دورية",
        "مصروفات نثرية عامة",
    ]
    for cat_name in categories:
        if session.query(ExpenseCategory).filter_by(name=cat_name).first() is None:
            session.add(ExpenseCategory(name=cat_name))


def _seed_default_customer(session: Session) -> None:
    """Seed default 'عميل نقدي' (Cash Customer)."""
    from app.models.customer import Customer
    if session.query(Customer).filter_by(name="عميل نقدي").first() is None:
        session.add(Customer(
            name="عميل نقدي",
            phone="",
            credit_limit=0,
            balance=0,
            notes="العميل النقدي الافتراضي للمبيعات المباشرة",
        ))


def seed_database(session: Session) -> None:
    """Idempotent seed: safe to call multiple times."""
    role_map = _seed_roles(session)
    _seed_settings(session)
    _seed_default_manager(session, role_map)
    _seed_cash_accounts(session)
    _seed_expense_categories(session)
    _seed_default_customer(session)
    session.commit()

