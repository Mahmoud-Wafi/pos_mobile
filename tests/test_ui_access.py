"""Offscreen smoke tests: login flow and per-role screen visibility."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from app.core.permissions import ROLE_CASHIER, ROLE_MANAGER, ROLE_WALLET_EMPLOYEE
from app.core.security import hash_password
from app.models.user import Role, User
from app.ui.access import can_open, allowed_screens


def _make_user(session, username, role_name, password="Str0ng-pass"):
    role = session.query(Role).filter_by(name=role_name).first()
    u = User(username=username, password_hash=hash_password(password),
             full_name=username, role_id=role.id, is_active=True)
    session.add(u)
    session.commit()
    return u


def test_access_map_wallet_employee_sees_only_wallets(db_session):
    u = _make_user(db_session, "w1", ROLE_WALLET_EMPLOYEE)
    assert set(allowed_screens(u.permission_codes())) == {"dashboard", "wallets"}


def test_access_map_cashier_has_no_cost_screens(db_session):
    u = _make_user(db_session, "c1", ROLE_CASHIER)
    screens = set(allowed_screens(u.permission_codes()))
    assert {"pos", "returns", "inventory", "customers", "accounting", "reports"} <= screens
    assert "settings" not in screens


def test_access_map_manager_sees_everything(db_session):
    u = db_session.query(User).join(Role).filter(Role.name == ROLE_MANAGER).first()
    assert len(allowed_screens(u.permission_codes())) == 10
    assert can_open(u.permission_codes(), "settings")


@pytest.mark.parametrize("role,hidden_idx,visible_idx", [
    (ROLE_WALLET_EMPLOYEE, {1, 2, 3, 4, 6, 7, 8, 9}, {0, 5}),
    (ROLE_CASHIER, {9}, {0, 1, 2, 3, 7, 8}),
    (ROLE_MANAGER, set(), set(range(10))),
])
def test_main_window_nav_per_role(qtbot, db_session, role, hidden_idx, visible_idx):
    from app.ui.main_window import MainWindow

    u = (db_session.query(User).join(Role).filter(Role.name == role).first()
         or _make_user(db_session, f"u_{role}", role))
    win = MainWindow(user_id=u.id)
    qtbot.addWidget(win)
    for i in hidden_idx:
        assert win.nav_buttons[i].isHidden(), f"nav {i} should be hidden for {role}"
    for i in visible_idx:
        assert not win.nav_buttons[i].isHidden(), f"nav {i} should be visible for {role}"


def test_main_window_requires_user(db_session):
    from app.ui.main_window import MainWindow

    with pytest.raises(ValueError):
        MainWindow()


def test_login_dialog_rejects_bad_password_and_locks(qtbot, db_session):
    from app.ui.login_dialog import LoginDialog

    _make_user(db_session, "lock_me", ROLE_CASHIER, password="Right-pass1")
    dlg = LoginDialog()
    qtbot.addWidget(dlg)
    dlg.user_edit.setText("lock_me")
    for _ in range(5):
        dlg.pass_edit.setText("wrong")
        dlg._attempt()
        assert dlg.user_id is None and dlg.error_lbl.text()
    dlg.pass_edit.setText("Right-pass1")
    dlg._attempt()
    assert dlg.user_id is None           # account is locked even with the right password


def test_login_dialog_accepts_good_credentials(qtbot, db_session):
    from app.ui.login_dialog import LoginDialog

    u = _make_user(db_session, "ok_user", ROLE_CASHIER, password="Right-pass1")
    dlg = LoginDialog()
    qtbot.addWidget(dlg)
    dlg.user_edit.setText("ok_user")
    dlg.pass_edit.setText("Right-pass1")
    dlg._attempt()
    assert dlg.user_id == u.id


def test_default_password_detection(db_session):
    from app.ui.login_dialog import uses_default_password

    admin = db_session.query(User).filter_by(username="admin").first()
    assert uses_default_password(admin)
    strong = _make_user(db_session, "strong", ROLE_CASHIER, password="Str0ng-pass")
    assert not uses_default_password(strong)
