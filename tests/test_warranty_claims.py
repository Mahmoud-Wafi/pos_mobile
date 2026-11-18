import datetime

import pytest

from app.core import clock
from app.core.money import egp_to_piasters as egp
from app.core.permissions import PermissionDenied, ROLE_CASHIER, ROLE_MANAGER
from app.core.security import hash_password
from app.models.user import Role, User
from app.services import inventory_service, sales_service, shift_service, warranty_service


def _user(s, name, role):
    r = s.query(Role).filter_by(name=role).first()
    u = User(username=name, password_hash=hash_password("Passw0rd!"), full_name=name, role_id=r.id)
    s.add(u)
    s.commit()
    return u


@pytest.fixture
def sold_item(db_session):
    s = db_session
    mgr = _user(s, "m", ROLE_MANAGER)
    p = inventory_service.create_product(s, mgr, {
        "name": "Cable", "type": "accessory", "cost_price": egp("10"), "sale_price": egp("50"),
        "min_price": egp("20"), "min_stock": 1, "track_imei": False, "warranty_days": 30})
    inventory_service.adjust_stock(s, mgr, p, 5, "init")
    shift_service.open_shift(s, mgr, opening_cash=0)
    sale = sales_service.start_sale(s, mgr)          # walk-in: no customer
    sales_service.add_line(s, mgr, sale, p)
    sales_service.post_sale(s, mgr, sale, [{"method": "cash", "amount": sale.total}])
    s.commit()
    return s, mgr, sale.items[0]


def test_walk_in_sale_warranty_lookup_does_not_crash(sold_item):
    s, mgr, item = sold_item
    rows = sales_service.search_warranty(s, item.sale.invoice_no)
    assert rows and rows[0]["customer_name"]


def test_open_update_close_claim(sold_item):
    s, mgr, item = sold_item
    claim = warranty_service.open_claim(s, mgr, item.id, "  does not charge ")
    assert claim.status == "open" and claim.in_warranty is True
    with pytest.raises(warranty_service.WarrantyError):          # only one open claim per item
        warranty_service.open_claim(s, mgr, item.id, "again")
    warranty_service.update_claim(s, mgr, claim.id, "in_repair")
    with pytest.raises(warranty_service.WarrantyError):          # closing needs a resolution
        warranty_service.update_claim(s, mgr, claim.id, "resolved")
    warranty_service.update_claim(s, mgr, claim.id, "resolved", "replaced")
    assert claim.closed_at is not None
    with pytest.raises(warranty_service.WarrantyError):
        warranty_service.update_claim(s, mgr, claim.id, "open")
    assert len(warranty_service.list_claims(s, mgr, status="resolved")) == 1


def test_expired_warranty_is_recorded_not_blocked(sold_item):
    s, mgr, item = sold_item
    item.warranty_end_date = clock.utcnow() - datetime.timedelta(days=1)
    s.commit()
    assert warranty_service.open_claim(s, mgr, item.id, "broken").in_warranty is False


def test_issue_required_and_permission(sold_item):
    s, mgr, item = sold_item
    with pytest.raises(warranty_service.WarrantyError):
        warranty_service.open_claim(s, mgr, item.id, "   ")
    wallet_staff = _user(s, "w", "wallet_employee")
    with pytest.raises(PermissionDenied):
        warranty_service.open_claim(s, wallet_staff, item.id, "x")
