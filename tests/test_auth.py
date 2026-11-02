"""Tests for auth_service: login, logout, change_password, permissions, lockout.

Acceptance criteria (Phase 1):
  - login works for 3 roles
  - PermissionDenied is raised in services for lacking permissions
  - Backup→restore round-trip test passes (see test_backup.py)
"""
import pytest
import datetime

from app.services.auth_service import (
    login, logout, change_password, user_has_permission,
    require_user_permission, require_override, AuthError,
)
from app.core.permissions import (
    PermissionDenied,
    PERM_SALES_CREATE, PERM_COST_VIEW, PERM_SETTINGS_MANAGE,
    PERM_WALLET_USE, PERM_INVENTORY_VIEW,
    ROLE_MANAGER, ROLE_CASHIER, ROLE_WALLET_EMPLOYEE,
)
from app.core.security import hash_password
from app.models.user import User, Role, RolePermission
from app.config import MAX_FAILED_ATTEMPTS


# ── Helpers ───────────────────────────────────────────────────────────────────

def _create_user(session, username, password, role_name):
    """Helper: fetch role and create a user."""
    role = session.query(Role).filter_by(name=role_name).first()
    assert role is not None, f"Role '{role_name}' not seeded"
    user = User(
        username=username,
        password_hash=hash_password(password),
        full_name=f"Test {username}",
        role_id=role.id,
        is_active=True,
    )
    session.add(user)
    session.commit()
    return user


# ── Login for 3 roles ─────────────────────────────────────────────────────────

class TestLoginThreeRoles:
    def test_manager_login(self, db_session):
        """Default seeded admin (manager) can log in."""
        user = login(db_session, "admin", "admin123")
        assert user.username == "admin"
        assert user.role.name == ROLE_MANAGER

    def test_cashier_login(self, db_session):
        _create_user(db_session, "cashier1", "pass123", ROLE_CASHIER)
        user = login(db_session, "cashier1", "pass123")
        assert user.role.name == ROLE_CASHIER

    def test_wallet_employee_login(self, db_session):
        _create_user(db_session, "wallet1", "pass123", ROLE_WALLET_EMPLOYEE)
        user = login(db_session, "wallet1", "pass123")
        assert user.role.name == ROLE_WALLET_EMPLOYEE

    def test_wrong_password_raises(self, db_session):
        with pytest.raises(AuthError):
            login(db_session, "admin", "wrong")

    def test_unknown_user_raises(self, db_session):
        with pytest.raises(AuthError):
            login(db_session, "nobody", "x")

    def test_last_login_updated(self, db_session):
        before = datetime.datetime.utcnow()
        user = login(db_session, "admin", "admin123")
        assert user.last_login is not None
        assert user.last_login >= before


# ── Account lockout ───────────────────────────────────────────────────────────

class TestAccountLockout:
    def test_lockout_after_max_failures(self, db_session):
        _create_user(db_session, "lockme", "correct", ROLE_CASHIER)
        for _ in range(MAX_FAILED_ATTEMPTS):
            with pytest.raises(AuthError):
                login(db_session, "lockme", "wrong")
        # Now the account should be locked
        with pytest.raises(AuthError, match="مقفل"):
            login(db_session, "lockme", "correct")

    def test_failed_attempts_count(self, db_session):
        _create_user(db_session, "countem", "correct", ROLE_CASHIER)
        for i in range(3):
            with pytest.raises(AuthError):
                login(db_session, "countem", "wrong")
        from app.models.user import User as U
        db_session.expire_all()
        u = db_session.query(U).filter_by(username="countem").first()
        assert u.failed_attempts == 3

    def test_successful_login_resets_counter(self, db_session):
        _create_user(db_session, "resetme", "correct", ROLE_CASHIER)
        with pytest.raises(AuthError):
            login(db_session, "resetme", "wrong")
        login(db_session, "resetme", "correct")
        from app.models.user import User as U
        db_session.expire_all()
        u = db_session.query(U).filter_by(username="resetme").first()
        assert u.failed_attempts == 0

    def test_inactive_account_blocked(self, db_session):
        _create_user(db_session, "inactive1", "pass", ROLE_CASHIER)
        from app.models.user import User as U
        u = db_session.query(U).filter_by(username="inactive1").first()
        u.is_active = False
        db_session.commit()
        with pytest.raises(AuthError, match="مفعّل"):
            login(db_session, "inactive1", "pass")


# ── Permission checks ─────────────────────────────────────────────────────────

class TestPermissions:
    def test_manager_has_cost_view(self, db_session):
        user = login(db_session, "admin", "admin123")
        assert user_has_permission(user, PERM_COST_VIEW)

    def test_cashier_lacks_cost_view(self, db_session):
        _create_user(db_session, "c2", "pass", ROLE_CASHIER)
        user = login(db_session, "c2", "pass")
        assert not user_has_permission(user, PERM_COST_VIEW)

    def test_wallet_employee_has_wallet_use(self, db_session):
        _create_user(db_session, "w2", "pass", ROLE_WALLET_EMPLOYEE)
        user = login(db_session, "w2", "pass")
        assert user_has_permission(user, PERM_WALLET_USE)

    def test_wallet_employee_lacks_sales_create(self, db_session):
        _create_user(db_session, "w3", "pass", ROLE_WALLET_EMPLOYEE)
        user = login(db_session, "w3", "pass")
        assert not user_has_permission(user, PERM_SALES_CREATE)

    def test_require_permission_raises_for_cashier(self, db_session):
        _create_user(db_session, "c3", "pass", ROLE_CASHIER)
        user = login(db_session, "c3", "pass")
        with pytest.raises(PermissionDenied) as exc_info:
            require_user_permission(user, PERM_SETTINGS_MANAGE)
        assert exc_info.value.permission_code == PERM_SETTINGS_MANAGE

    def test_require_permission_passes_for_manager(self, db_session):
        user = login(db_session, "admin", "admin123")
        # Should not raise
        require_user_permission(user, PERM_SETTINGS_MANAGE)

    def test_cashier_has_sales_create(self, db_session):
        _create_user(db_session, "c4", "pass", ROLE_CASHIER)
        user = login(db_session, "c4", "pass")
        assert user_has_permission(user, PERM_SALES_CREATE)

    def test_cashier_has_inventory_view(self, db_session):
        _create_user(db_session, "c5", "pass", ROLE_CASHIER)
        user = login(db_session, "c5", "pass")
        assert user_has_permission(user, PERM_INVENTORY_VIEW)


# ── Change password ───────────────────────────────────────────────────────────

class TestChangePassword:
    def test_change_password_success(self, db_session):
        user = login(db_session, "admin", "admin123")
        change_password(db_session, user, "admin123", "newpass456")
        # Login with new password
        user2 = login(db_session, "admin", "newpass456")
        assert user2.id == user.id

    def test_wrong_old_password_fails(self, db_session):
        user = login(db_session, "admin", "admin123")
        with pytest.raises(AuthError):
            change_password(db_session, user, "wrongold", "newpass456")


# ── Manager override ──────────────────────────────────────────────────────────

class TestManagerOverride:
    def test_override_succeeds_with_manager(self, db_session):
        _create_user(db_session, "cashier_ov", "pass", ROLE_CASHIER)
        cashier = login(db_session, "cashier_ov", "pass")
        # Manager grants override
        manager = require_override(
            db_session, cashier, PERM_COST_VIEW, "admin", "admin123"
        )
        assert manager.role.name == ROLE_MANAGER

    def test_override_fails_with_wrong_password(self, db_session):
        _create_user(db_session, "cashier_ov2", "pass", ROLE_CASHIER)
        cashier = login(db_session, "cashier_ov2", "pass")
        with pytest.raises(AuthError):
            require_override(
                db_session, cashier, PERM_COST_VIEW, "admin", "wrongpw"
            )

    def test_override_fails_if_non_manager(self, db_session):
        _create_user(db_session, "cashier_a", "pass", ROLE_CASHIER)
        _create_user(db_session, "cashier_b", "pass", ROLE_CASHIER)
        cashier_a = login(db_session, "cashier_a", "pass")
        with pytest.raises(PermissionDenied):
            require_override(
                db_session, cashier_a, PERM_COST_VIEW, "cashier_b", "pass"
            )


# ── Logout ────────────────────────────────────────────────────────────────────

class TestLogout:
    def test_logout_creates_audit_entry(self, db_session):
        from app.models.user import AuditLog
        user = login(db_session, "admin", "admin123")
        logout(db_session, user)
        entry = (
            db_session.query(AuditLog)
            .filter_by(action="logout", user_id=user.id)
            .first()
        )
        assert entry is not None

