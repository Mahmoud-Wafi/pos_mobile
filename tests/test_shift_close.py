"""Close-shift: blind count, difference, permissions, and the dialog."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from app.core.money import egp_to_piasters
from app.core.permissions import PermissionDenied, ROLE_CASHIER, ROLE_MANAGER
from app.core.security import hash_password
from app.models.user import Role, User
from app.services import inventory_service, sales_service, shift_service


def _user(session, name, role):
    r = session.query(Role).filter_by(name=role).first()
    u = User(username=name, password_hash=hash_password("Passw0rd!"), full_name=name, role_id=r.id)
    session.add(u)
    session.commit()
    return u


@pytest.fixture
def mgr(db_session):
    return _user(db_session, "m", ROLE_MANAGER)


@pytest.fixture
def cash1(db_session):
    return _user(db_session, "c1", ROLE_CASHIER)


@pytest.fixture
def cash2(db_session):
    return _user(db_session, "c2", ROLE_CASHIER)


def _sell_cash(session, mgr, cashier, price="350"):
    p = inventory_service.create_product(session, mgr, {
        "name": "Charger", "type": "accessory", "cost_price": egp_to_piasters("200"),
        "sale_price": egp_to_piasters(price), "min_price": egp_to_piasters("300"),
        "min_stock": 1, "track_imei": False, "warranty_days": 30})
    inventory_service.adjust_stock(session, mgr, p, 5, "init")
    session.commit()
    sale = sales_service.start_sale(session, cashier)
    sales_service.add_line(session, cashier, sale, p, quantity=1)
    sales_service.post_sale(session, cashier, sale, [{"method": "cash", "amount": sale.total}])
    session.commit()
    return sale


@pytest.mark.parametrize("counted,expected_diff", [("1350", 0), ("1340", -egp_to_piasters("10")),
                                                   ("1360", egp_to_piasters("10"))])
def test_close_shift_diff(db_session, mgr, cash1, counted, expected_diff):
    shift = shift_service.open_shift(db_session, cash1, opening_cash=egp_to_piasters("1000"))
    db_session.commit()
    _sell_cash(db_session, mgr, cash1)
    closed = shift_service.close_shift(db_session, cash1, shift.id, egp_to_piasters(counted))
    assert closed.expected_cash == egp_to_piasters("1350")
    assert closed.diff == expected_diff and closed.status == "closed"
    assert shift_service.get_active_shift(db_session, cash1.id) is None


def test_cannot_close_someone_elses_shift_unless_manager(db_session, mgr, cash1, cash2):
    shift = shift_service.open_shift(db_session, cash1, opening_cash=0)
    db_session.commit()
    with pytest.raises(PermissionDenied):
        shift_service.close_shift(db_session, cash2, shift.id, 0)
    shift_service.close_shift(db_session, mgr, shift.id, 0)       # manager may


def test_negative_actual_rejected(db_session, cash1):
    shift = shift_service.open_shift(db_session, cash1, opening_cash=0)
    db_session.commit()
    with pytest.raises(ValueError):
        shift_service.close_shift(db_session, cash1, shift.id, -1)


def test_shift_status(db_session, cash1):
    assert shift_service.shift_status(db_session, cash1)["is_open"] is False
    shift_service.open_shift(db_session, cash1, opening_cash=0)
    st = shift_service.shift_status(db_session, cash1)
    assert st["is_open"] and st["opened_at"]


def test_dialog_is_blind_then_shows_result(qtbot, db_session, mgr, cash1):
    from app.ui.shift_dialog import CloseShiftDialog

    shift = shift_service.open_shift(db_session, cash1, opening_cash=egp_to_piasters("1000"))
    db_session.commit()
    _sell_cash(db_session, mgr, cash1)
    dlg = CloseShiftDialog(db_session, cash1, shift)
    qtbot.addWidget(dlg)
    # blind: before confirming, the expected amount (1,350.00) appears nowhere
    texts = " ".join(w.text() for w in dlg.findChildren(type(dlg.hint)))
    assert "1,350" not in texts and "1350" not in texts

    dlg.actual_edit.setText("abc")
    dlg.confirm()
    assert not dlg.closed and dlg.error_lbl.text()

    dlg.actual_edit.setText("1340")
    dlg.confirm()
    assert dlg.closed
    assert "1,350.00" in dlg.result_lbl.text() and "10.00" in dlg.result_lbl.text()


def test_pos_close_shift_flow_updates_state(qtbot, db_session, mgr, cash1, monkeypatch):
    from app.ui.pos import pos_window
    from app.ui.pos.pos_window import POSWindow

    shift_service.open_shift(db_session, cash1, opening_cash=egp_to_piasters("500"))
    db_session.commit()
    pos = POSWindow(db_session, cash1)
    qtbot.addWidget(pos)
    assert not pos.shift_bar.isHidden() and pos.btn_pay.isEnabled()

    class _Auto:                     # stand-in dialog: closes the shift with a perfect count
        def __init__(self, session, user, shift, parent=None):
            self.session, self.user, self.shift, self.closed = session, user, shift, False

        def exec(self):
            shift_service.close_shift(self.session, self.user, self.shift.id, egp_to_piasters("500"))
            self.session.commit()
            self.closed = True

    monkeypatch.setattr("app.ui.shift_dialog.CloseShiftDialog", _Auto)
    with qtbot.waitSignal(pos.shift_changed):
        pos._close_shift_dialog()
    assert pos.shift_bar.isHidden() and not pos.btn_pay.isEnabled()
