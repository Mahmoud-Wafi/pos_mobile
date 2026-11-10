"""User administration, shop settings and audit viewer services."""
import datetime

import pytest

from app.core import clock
from app.core.permissions import PermissionDenied, ROLE_CASHIER, ROLE_MANAGER
from app.core.security import hash_password, verify_password
from app.models.user import AuditLog, Role, User
from app.services import audit_service, settings_service, user_service
from app.services.user_service import UserAdminError


@pytest.fixture
def admin(db_session):
    return db_session.query(User).filter_by(username="admin").first()


@pytest.fixture
def cashier(db_session):
    role = db_session.query(Role).filter_by(name=ROLE_CASHIER).first()
    u = User(username="cash", password_hash=hash_password("secret1"), full_name="Cash", role_id=role.id)
    db_session.add(u)
    db_session.commit()
    return u


def _role_id(session, name):
    return session.query(Role).filter_by(name=name).first().id


def test_only_manager_can_manage_users(db_session, cashier):
    with pytest.raises(PermissionDenied):
        user_service.list_users(db_session, cashier)
    with pytest.raises(PermissionDenied):
        user_service.create_user(db_session, cashier, "x", "X", 1, "secret1")


def test_create_user_validations_and_audit(db_session, admin):
    rid = _role_id(db_session, ROLE_CASHIER)
    u = user_service.create_user(db_session, admin, "newbie", "New Bie", rid, "secret1")
    assert verify_password("secret1", u.password_hash)
    assert db_session.query(AuditLog).filter_by(action="create_user").count() == 1
    with pytest.raises(UserAdminError):
        user_service.create_user(db_session, admin, "newbie", "Dup", rid, "secret1")
    with pytest.raises(UserAdminError):
        user_service.create_user(db_session, admin, "short", "S", rid, "123")


def test_cannot_deactivate_self_or_last_manager(db_session, admin, cashier):
    with pytest.raises(UserAdminError):
        user_service.update_user(db_session, admin, admin.id, is_active=False)
    with pytest.raises(UserAdminError):       # demoting the only manager
        user_service.update_user(db_session, admin, admin.id, role_id=_role_id(db_session, ROLE_CASHIER))
    # with a second manager, demotion is fine
    second = user_service.create_user(db_session, admin, "mgr2", "Mgr 2", _role_id(db_session, ROLE_MANAGER), "secret1")
    user_service.update_user(db_session, second, admin.id, role_id=_role_id(db_session, ROLE_CASHIER))
    assert admin.role.name == ROLE_CASHIER


def test_reset_password_unlocks(db_session, admin, cashier):
    cashier.failed_attempts = 5
    cashier.locked_until = clock.utcnow() + datetime.timedelta(minutes=10)
    user_service.reset_password(db_session, admin, cashier.id, "brandnew1")
    assert verify_password("brandnew1", cashier.password_hash)
    assert cashier.failed_attempts == 0 and cashier.locked_until is None


def test_settings_update_validation(db_session, admin, cashier):
    settings_service.update(db_session, admin, {"shop_name": "محل النور", "idle_lock_minutes": "15"})
    assert settings_service.get(db_session, "shop_name") == "محل النور"
    assert settings_service.get_all(db_session)["idle_lock_minutes"] == "15"
    with pytest.raises(settings_service.SettingsError):
        settings_service.update(db_session, admin, {"cashier_discount_limit_pct": "150"})
    with pytest.raises(settings_service.SettingsError):
        settings_service.update(db_session, admin, {"shop_name": "  "})
    with pytest.raises(settings_service.SettingsError):
        settings_service.update(db_session, admin, {"nope": "1"})
    with pytest.raises(PermissionDenied):
        settings_service.update(db_session, cashier, {"shop_name": "x"})


def test_audit_viewer_filters_and_permission(db_session, admin, cashier):
    user_service.reset_password(db_session, admin, cashier.id, "brandnew1")
    rows = audit_service.list_entries(db_session, admin, action="reset_password")
    assert len(rows) == 1 and rows[0].user_id == admin.id
    today = clock.local_today()
    assert audit_service.list_entries(db_session, admin, start_date=today, end_date=today)
    assert not audit_service.list_entries(db_session, admin, start_date=today - datetime.timedelta(days=5),
                                          end_date=today - datetime.timedelta(days=4))
    with pytest.raises(PermissionDenied):
        audit_service.list_entries(db_session, cashier)
