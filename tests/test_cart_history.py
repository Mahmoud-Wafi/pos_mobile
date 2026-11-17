"""Cart line editing and invoice-history search."""
import pytest

from app.core import clock
from app.core.money import egp_to_piasters as E
from app.core.permissions import ROLE_CASHIER, ROLE_MANAGER
from app.core.security import hash_password
from app.models.user import Role, User
from app.services import inventory_service, sales_service, shift_service
from app.services.sales_service import (
    DiscountLimitExceededError, InsufficientStockError, SaleError)


def _user(s, name, role):
    r = s.query(Role).filter_by(name=role).first()
    u = User(username=name, password_hash=hash_password("Passw0rd!"), full_name=name, role_id=r.id)
    s.add(u); s.commit()
    return u


@pytest.fixture
def env(db_session):
    s = db_session
    mgr, cash = _user(s, "m", ROLE_MANAGER), _user(s, "c", ROLE_CASHIER)
    p = inventory_service.create_product(s, mgr, {
        "name": "Cable", "type": "accessory", "cost_price": E("50"), "sale_price": E("100"),
        "min_price": E("80"), "min_stock": 1, "track_imei": False, "warranty_days": 0})
    inventory_service.adjust_stock(s, mgr, p, 5, "init")
    s.commit()
    shift_service.open_shift(s, cash, opening_cash=0)
    s.commit()
    sale = sales_service.start_sale(s, cash)
    item = sales_service.add_line(s, cash, sale, p, quantity=1)
    return s, mgr, cash, p, sale, item


def test_update_quantity_recalculates(env):
    s, mgr, cash, p, sale, item = env
    sales_service.update_line(s, cash, sale, item.id, quantity=3)
    assert item.line_total == E("300") and sale.total == E("300")


def test_quantity_over_stock_rejected(env):
    s, mgr, cash, p, sale, item = env
    with pytest.raises(InsufficientStockError):
        sales_service.update_line(s, cash, sale, item.id, quantity=6)


def test_zero_quantity_rejected(env):
    s, mgr, cash, p, sale, item = env
    with pytest.raises(ValueError):
        sales_service.update_line(s, cash, sale, item.id, quantity=0)


def test_price_override_needs_manager(env):
    s, mgr, cash, p, sale, item = env
    with pytest.raises(DiscountLimitExceededError):
        sales_service.update_line(s, cash, sale, item.id, unit_price=E("90"))
    sales_service.update_line(s, cash, sale, item.id, unit_price=E("90"), manager_override=mgr)
    assert sale.total == E("90")


def test_line_discount_limit(env):
    s, mgr, cash, p, sale, item = env
    sales_service.update_line(s, cash, sale, item.id, discount=E("5"))  # 5% ok
    assert sale.total == E("95")
    with pytest.raises(DiscountLimitExceededError):
        sales_service.update_line(s, cash, sale, item.id, discount=E("20"))
    sales_service.update_line(s, cash, sale, item.id, discount=E("20"), manager_override=mgr)
    assert sale.total == E("80")


def test_line_discount_cannot_exceed_line(env):
    s, mgr, cash, p, sale, item = env
    with pytest.raises(ValueError):
        sales_service.update_line(s, mgr, sale, item.id, discount=E("101"))


def test_posted_sale_not_editable(env):
    s, mgr, cash, p, sale, item = env
    sales_service.post_sale(s, cash, sale, [{"method": "cash", "amount": sale.total}])
    with pytest.raises(SaleError):
        sales_service.update_line(s, cash, sale, item.id, quantity=2)


def test_search_sales_filters(env):
    s, mgr, cash, p, sale, item = env
    sales_service.post_sale(s, cash, sale, [{"method": "cash", "amount": sale.total}])
    s.commit()
    today = clock.local_today()
    assert [x.id for x in sales_service.search_sales(s, mgr, today, today)] == [sale.id]
    assert sales_service.search_sales(s, mgr, text=sale.invoice_no[-3:])
    assert not sales_service.search_sales(s, mgr, cashier_id=mgr.id)
    assert not sales_service.search_sales(s, mgr, status="void")
