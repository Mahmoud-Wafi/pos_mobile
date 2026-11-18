import pytest

from app.core.money import egp_to_piasters as egp
from app.core.permissions import PermissionDenied, ROLE_CASHIER, ROLE_MANAGER, ROLE_WALLET_EMPLOYEE
from app.core.security import hash_password
from app.models.accounting import CashAccount
from app.models.user import Role, User
from app.services import repair_service as rs, shift_service


def _user(s, name, role):
    r = s.query(Role).filter_by(name=role).first()
    u = User(username=name, password_hash=hash_password("Passw0rd!"), full_name=name, role_id=r.id)
    s.add(u)
    s.commit()
    return u


@pytest.fixture
def env(db_session):
    s = db_session
    mgr, cashier = _user(s, "m", ROLE_MANAGER), _user(s, "c", ROLE_CASHIER)
    shift_service.open_shift(s, cashier, opening_cash=0)
    return s, mgr, cashier


DATA = {"customer_name": "Hassan", "customer_phone": "01012345678", "device_desc": "iPhone 11",
        "issue": "screen cracked", "estimate": egp("800")}


def _drawer(s):
    return s.query(CashAccount).filter_by(type="drawer").first().balance


def test_create_with_deposit_goes_to_drawer(env):
    s, mgr, cashier = env
    before = _drawer(s)
    t = rs.create_ticket(s, cashier, DATA, deposit=egp("200"))
    s.commit()
    assert t.ticket_no.startswith("REP-") and t.status == "received"
    assert t.paid == egp("200") and t.final_price == egp("800") and t.balance == egp("600")
    assert _drawer(s) == before + egp("200")
    t2 = rs.create_ticket(s, cashier, DATA)
    assert t2.ticket_no != t.ticket_no


def test_deposit_needs_open_shift(env):
    s, mgr, cashier = env
    with pytest.raises(rs.RepairError):
        rs.create_ticket(s, mgr, DATA, deposit=egp("50"))     # manager has no open shift
    s.rollback()
    assert rs.create_ticket(s, mgr, DATA).paid == 0           # no cash, no shift needed


def test_validation(env):
    s, _m, cashier = env
    for bad in ({"customer_name": " "}, {"device_desc": ""}, {"issue": ""}):
        with pytest.raises(rs.RepairError):
            rs.create_ticket(s, cashier, {**DATA, **bad})
    with pytest.raises(PermissionDenied):
        rs.create_ticket(s, _user(s, "w", ROLE_WALLET_EMPLOYEE), DATA)


def test_full_flow_deliver_requires_ready_and_paid(env):
    s, mgr, cashier = env
    t = rs.create_ticket(s, cashier, DATA, deposit=egp("300"))
    with pytest.raises(rs.RepairError):
        rs.deliver(s, cashier, t.id)                          # not ready
    rs.set_status(s, cashier, t.id, "diagnosing")
    with pytest.raises(rs.RepairError):
        rs.set_status(s, cashier, t.id, "delivered")          # not a manual move
    rs.set_pricing(s, cashier, t.id, egp("900"))
    rs.set_status(s, cashier, t.id, "ready")
    assert t.ready_at is not None
    with pytest.raises(rs.RepairError):
        rs.deliver(s, cashier, t.id)                          # balance due
    rs.add_payment(s, cashier, t.id, t.balance)
    rs.deliver(s, cashier, t.id)
    assert t.status == "delivered" and t.paid == egp("900") and t.delivered_at
    with pytest.raises(rs.RepairError):
        rs.add_payment(s, cashier, t.id, 100)                 # closed


def test_parts_cost_needs_cost_permission(env):
    s, mgr, cashier = env
    t = rs.create_ticket(s, cashier, DATA)
    with pytest.raises(PermissionDenied):
        rs.set_pricing(s, cashier, t.id, egp("900"), parts_cost=egp("300"))
    rs.set_pricing(s, mgr, t.id, egp("900"), parts_cost=egp("300"))
    assert t.parts_cost == egp("300")


def test_cancel_refunds_deposit_and_needs_return_permission(env):
    s, mgr, cashier = env
    t = rs.create_ticket(s, cashier, DATA, deposit=egp("100"))
    before = _drawer(s)
    with pytest.raises(rs.RepairError):
        rs.cancel(s, cashier, t.id, " ")
    rs.cancel(s, cashier, t.id, "customer changed mind")
    assert t.status == "cancelled" and t.paid == 0 and _drawer(s) == before - egp("100")


def test_shift_close_counts_repair_cash(env):
    s, mgr, cashier = env
    shift = shift_service.get_active_shift(s, cashier.id)
    rs.create_ticket(s, cashier, DATA, deposit=egp("250"))
    s.commit()
    assert shift_service.calculate_expected_cash(s, shift.id) == egp("250")


def test_search_and_message(env):
    s, mgr, cashier = env
    t = rs.create_ticket(s, cashier, DATA)
    assert rs.list_tickets(s, cashier, text="iphone") == [t]
    assert rs.list_tickets(s, cashier, status="active") == [t]
    assert rs.list_tickets(s, cashier, status="delivered") == []
    assert rs.egypt_phone("٠١٠١٢٣٤٥٦٧٨") == "201012345678"
    assert rs.egypt_phone("12") is None
    msg = rs.ready_message(t, "Shop", "800.00 ج.م")
    assert "iPhone 11" in msg and t.ticket_no in msg
    assert rs.whatsapp_link(t.customer_phone, msg).startswith("https://wa.me/201012345678?text=")
    assert rs.whatsapp_link("abc", msg) is None


def test_daily_close_counts_delivered_repair_profit(env):
    from app.services import accounting_service
    s, mgr, cashier = env
    t = rs.create_ticket(s, cashier, DATA)
    rs.set_pricing(s, mgr, t.id, egp("900"), parts_cost=egp("300"))
    rs.set_status(s, cashier, t.id, "ready")
    rs.add_payment(s, cashier, t.id, egp("900"))
    rs.deliver(s, cashier, t.id)
    s.commit()
    before = accounting_service.daily_close(s, mgr)
    assert before["repairs"] == {"count": 1, "income": egp("900"), "profit": egp("600")}
    assert before["net_profit"] >= egp("600")


def test_slip_pdf_is_written(env, tmp_path):
    from pypdf import PdfReader
    from app.printing.repair_slip import generate_repair_slip_pdf
    s, mgr, cashier = env
    t = rs.create_ticket(s, cashier, DATA, deposit=egp("100"))
    out = generate_repair_slip_pdf(t, tmp_path / "slip.pdf", "محل", "0100")
    assert len(PdfReader(str(out)).pages) == 1
