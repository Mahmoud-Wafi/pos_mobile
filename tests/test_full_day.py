"""5.5 — one whole shop day end to end, through the service layer."""
import sqlite3

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import backup as core_backup
from app.core.money import egp_to_piasters as egp
from app.core.permissions import PermissionDenied, ROLE_CASHIER, ROLE_MANAGER
from app.core.security import hash_password
from app.core.database import Base, override_engine
from app.core.seed import seed_database
from app.models.sale import Sale
from app.models.user import Role, User
from app.services import (accounting_service, customer_service, inventory_service,
                          report_service, sales_service, shift_service)


def _user(session, name, role):
    r = session.query(Role).filter_by(name=role).first()
    u = User(username=name, password_hash=hash_password("Passw0rd!"), full_name=name, role_id=r.id)
    session.add(u)
    session.commit()
    return u


def _product(session, mgr, name, price, imei=False):
    p = inventory_service.create_product(session, mgr, {
        "name": name, "type": "phone" if imei else "accessory", "cost_price": egp(price) // 2,
        "sale_price": egp(price), "min_price": egp(price) // 2 + 1, "min_stock": 1,
        "track_imei": imei, "warranty_days": 365 if imei else 30})
    if not imei:
        inventory_service.adjust_stock(session, mgr, p, 10, "init")
    session.commit()
    return p


@pytest.fixture
def file_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'shop.db'}", connect_args={"check_same_thread": False})
    override_engine(engine)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    seed_database(session)
    yield session
    session.close()
    engine.dispose()


def test_a_full_day(file_session, tmp_path):
    s = file_session
    mgr, cashier = _user(s, "boss", ROLE_MANAGER), _user(s, "cash", ROLE_CASHIER)
    charger = _product(s, mgr, "Charger", "300")
    phone = _product(s, mgr, "Phone X", "10000", imei=True)
    inventory_service.add_devices(s, mgr, phone, [
        {"imei1": "490154203237518", "condition": "new", "purchase_cost": egp("5000")}])
    s.commit()
    customer = customer_service.create_customer(s, mgr, {"name": "Ali", "credit_limit": egp("20000")})

    # open shift
    shift = shift_service.open_shift(s, cashier, opening_cash=egp("500"))

    # 1) cash sale
    sale1 = sales_service.start_sale(s, cashier)
    sales_service.add_line(s, cashier, sale1, charger, quantity=2)
    sales_service.post_sale(s, cashier, sale1, [{"method": "cash", "amount": sale1.total}])
    s.commit()
    assert sale1.status == "posted" and sale1.total == egp("600")

    # 2) split cash + credit sale of an IMEI phone
    dev = inventory_service.get_devices_for_product(s, phone.id, status="in_stock")[0]
    sale2 = sales_service.start_sale(s, cashier, customer_id=customer.id)
    sales_service.add_line(s, cashier, sale2, phone, device=dev)
    sales_service.post_sale(s, cashier, sale2, [
        {"method": "cash", "amount": egp("4000")}, {"method": "credit", "amount": sale2.total - egp("4000")}])
    s.commit()
    s.refresh(customer)
    assert customer.balance == egp("6000")
    assert dev.status == "sold"

    # 3) partial return of one charger, back to cash
    item = sale1.items[0]
    sales_service.return_sale_items(s, cashier, sale1.id, [{"sale_item_id": item.id, "quantity": 1}],
                                    reason="defect")
    s.commit()

    # 4) void: a third sale is posted then voided by the manager; stock comes back
    sale3 = sales_service.start_sale(s, cashier)
    sales_service.add_line(s, cashier, sale3, charger, quantity=1)
    sales_service.post_sale(s, cashier, sale3, [{"method": "cash", "amount": sale3.total}])
    s.commit()
    sales_service.void_sale(s, mgr, sale3.id, "customer cancelled")
    s.commit()
    assert sale3.status == "void"
    assert charger.current_quantity() == 10 - 2 + 1  # 2 sold, 1 returned, sale3 voided

    # cashier cannot void
    with pytest.raises(PermissionDenied):
        sales_service.void_sale(s, cashier, sale1.id, "x")

    # 5) close shift (blind count equals the expected cash)
    expected = shift_service.calculate_expected_cash(s, shift.id)
    closed = shift_service.close_shift(s, cashier, shift.id, actual_cash=expected)
    s.commit()
    assert closed.status == "closed" and closed.diff == 0

    # 6) daily close
    report = accounting_service.daily_close(s, mgr)
    assert report["sales"]["count"] == 2   # posted sales only; the voided one is excluded
    assert report["sales"]["total"] == egp("600") + egp("10000")  # gross invoices; returns are tracked separately

    # 7) backup -> change something -> restore -> the change is gone
    db_path, backup_dir = tmp_path / "shop.db", tmp_path / "backups"
    s.commit()
    zipped = core_backup.create_backup(db_path, backup_dir)
    assert zipped in core_backup.list_backups(backup_dir)
    posted_before = s.query(Sale).filter_by(status="posted").count()
    extra = sales_service.start_sale(s, mgr)
    sales_service.add_line(s, mgr, extra, charger, quantity=1)
    shift2 = shift_service.open_shift(s, mgr, opening_cash=0)
    sales_service.post_sale(s, mgr, extra, [{"method": "cash", "amount": extra.total}])
    s.commit()
    assert s.query(Sale).filter_by(status="posted").count() == posted_before + 1
    s.close()
    core_backup.restore_backup(zipped, db_path, backup_dir)
    con = sqlite3.connect(db_path)
    try:
        assert con.execute("select count(*) from sales where status='posted'").fetchone()[0] == posted_before
    finally:
        con.close()


def test_cashier_sees_no_cost_or_profit(db_session):
    s = db_session
    cashier = _user(s, "cash2", ROLE_CASHIER)
    assert "cost.view" not in cashier.permission_codes()
    assert "profit.view" not in cashier.permission_codes()
    ov = report_service.dashboard_overview(s, cashier)
    assert ov["sales"]["today"]["profit"] is None
