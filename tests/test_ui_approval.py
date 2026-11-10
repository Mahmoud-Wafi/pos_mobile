"""Manager approval dialog + POS discount / price override flow (offscreen)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from app.core.money import egp_to_piasters
from app.core.permissions import ROLE_CASHIER, ROLE_MANAGER, ROLE_WALLET_EMPLOYEE
from app.core.security import hash_password
from app.models.user import AuditLog, Role, User
from app.services import inventory_service, sales_service, shift_service


def _user(session, name, role, pw="Passw0rd!"):
    r = session.query(Role).filter_by(name=role).first()
    u = User(username=name, password_hash=hash_password(pw), full_name=name, role_id=r.id, is_active=True)
    session.add(u)
    session.commit()
    return u


@pytest.fixture
def people(db_session):
    return {
        "mgr": _user(db_session, "boss", ROLE_MANAGER),
        "cashier": _user(db_session, "kasher", ROLE_CASHIER),
        "wallet": _user(db_session, "walleter", ROLE_WALLET_EMPLOYEE),
    }


def test_dialog_rejects_wrong_password(qtbot, db_session, people):
    from app.ui.approval_dialog import ManagerApprovalDialog

    dlg = ManagerApprovalDialog(db_session, people["cashier"], "sales.discount", "why")
    qtbot.addWidget(dlg)
    dlg.user_edit.setText("boss")
    dlg.pass_edit.setText("nope")
    dlg._grant()
    assert dlg.manager is None and dlg.error_lbl.text()


def test_dialog_rejects_non_manager(qtbot, db_session, people):
    from app.i18n import ar
    from app.ui.approval_dialog import ManagerApprovalDialog

    dlg = ManagerApprovalDialog(db_session, people["cashier"], "sales.discount", "why")
    qtbot.addWidget(dlg)
    dlg.user_edit.setText("walleter")
    dlg.pass_edit.setText("Passw0rd!")
    dlg._grant()
    assert dlg.manager is None
    assert dlg.error_lbl.text() == ar.APPROVAL_NOT_MANAGER


def test_dialog_accepts_manager_and_audits(qtbot, db_session, people):
    from app.ui.approval_dialog import ManagerApprovalDialog

    dlg = ManagerApprovalDialog(db_session, people["cashier"], "sales.discount", "why")
    qtbot.addWidget(dlg)
    dlg.user_edit.setText("boss")
    dlg.pass_edit.setText("Passw0rd!")
    dlg._grant()
    assert dlg.manager.username == "boss"
    assert db_session.query(AuditLog).filter_by(action="manager_override").count() == 1


@pytest.fixture
def pos(qtbot, db_session, people):
    from app.ui.pos.pos_window import POSWindow

    shift_service.open_shift(db_session, people["cashier"], opening_cash=egp_to_piasters("500"))
    inventory_service.create_category(db_session, people["mgr"], "Acc")
    p = inventory_service.create_product(db_session, people["mgr"], {
        "name": "Charger", "type": "accessory", "cost_price": egp_to_piasters("200"),
        "sale_price": egp_to_piasters("350"), "min_price": egp_to_piasters("300"),
        "min_stock": 1, "track_imei": False, "warranty_days": 30,
    })
    inventory_service.adjust_stock(db_session, people["mgr"], p, 10, "init")
    db_session.commit()
    w = POSWindow(db_session, people["cashier"])
    qtbot.addWidget(w)
    sales_service.add_line(db_session, people["cashier"], w.current_sale, p, quantity=1)
    w._refresh_cart()
    return w


def test_discount_over_limit_with_manager_approval(pos, people, monkeypatch):
    from app.ui.pos import pos_window

    monkeypatch.setattr(pos_window, "request_manager_approval", lambda *a, **k: people["mgr"])
    pos.disc_edit.setText("100")          # far above the cashier's 5 %
    pos._on_discount_committed()
    assert pos.current_sale.discount == egp_to_piasters("100")


def test_discount_over_limit_declined_resets_to_zero(pos, monkeypatch):
    from app.ui.pos import pos_window

    monkeypatch.setattr(pos_window, "request_manager_approval", lambda *a, **k: None)
    pos.disc_edit.setText("100")
    pos._on_discount_committed()
    assert pos.current_sale.discount == 0
    assert pos.disc_edit.text() == "0.00"


def test_small_discount_needs_no_approval(pos, monkeypatch):
    from app.ui.pos import pos_window

    def _boom(*a, **k):
        raise AssertionError("approval must not be requested")

    monkeypatch.setattr(pos_window, "request_manager_approval", _boom)
    pos.disc_edit.setText("10")
    pos._on_discount_committed()
    assert pos.current_sale.discount == egp_to_piasters("10")
