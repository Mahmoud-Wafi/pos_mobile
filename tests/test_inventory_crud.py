"""Edit / delete / write-off rules for products and devices."""
import pytest

from app.core.money import egp_to_piasters as egp
from app.core.permissions import PermissionDenied, ROLE_CASHIER, ROLE_MANAGER
from app.core.security import hash_password
from app.models.product import Product
from app.models.stock import Device, Stock, StockMovement
from app.models.user import Role, User
from app.services import inventory_service as inv, sales_service, shift_service


def _user(s, name, role):
    r = s.query(Role).filter_by(name=role).first()
    u = User(username=name, password_hash=hash_password("Passw0rd!"), full_name=name, role_id=r.id)
    s.add(u)
    s.commit()
    return u


def _product(s, mgr, name="Cable", imei=False, **kw):
    p = inv.create_product(s, mgr, {"name": name, "type": "phone" if imei else "accessory",
                                    "cost_price": egp("10"), "sale_price": egp("50"), "min_price": egp("20"),
                                    "min_stock": 1, "track_imei": imei, "warranty_days": 30, **kw})
    s.commit()
    return p


@pytest.fixture
def mgr(db_session):
    return _user(db_session, "m", ROLE_MANAGER)


def test_update_product_fields_and_validation(db_session, mgr):
    s = db_session
    p = _product(s, mgr)
    inv.update_product(s, mgr, p.id, {"name": " Cable 2m ", "sale_price": egp("60"), "cost_price": egp("12"),
                                      "barcode": "123"})
    assert p.name == "Cable 2m" and p.sale_price == egp("60") and p.cost_price == egp("12")
    with pytest.raises(inv.InventoryError):
        inv.update_product(s, mgr, p.id, {"name": "  "})
    with pytest.raises(inv.InventoryError):
        inv.update_product(s, mgr, p.id, {"sale_price": -1})
    other = _product(s, mgr, "Other")
    with pytest.raises(inv.InventoryError):
        inv.update_product(s, mgr, other.id, {"barcode": "123"})      # barcode already used


def test_cost_needs_cost_permission(db_session, mgr):
    s = db_session
    p = _product(s, mgr)
    cashier = _user(s, "c", ROLE_CASHIER)
    with pytest.raises(PermissionDenied):
        inv.update_product(s, cashier, p.id, {"cost_price": egp("1")})


def test_type_locked_after_history(db_session, mgr):
    s = db_session
    fresh = _product(s, mgr, "Fresh")
    inv.update_product(s, mgr, fresh.id, {"type": "card"})             # nothing happened yet: allowed
    used = _product(s, mgr, "Used")
    inv.adjust_stock(s, mgr, used, 3, "init")
    s.commit()
    with pytest.raises(inv.InventoryError):
        inv.update_product(s, mgr, used.id, {"type": "phone", "track_imei": True})


def test_delete_unused_product_but_not_one_with_history(db_session, mgr):
    s = db_session
    unused, used = _product(s, mgr, "Unused"), _product(s, mgr, "Used")
    inv.adjust_stock(s, mgr, used, 2, "init")
    s.commit()
    inv.delete_product(s, mgr, unused.id)
    s.commit()
    assert s.get(Product, unused.id) is None and s.query(Stock).filter_by(product_id=unused.id).count() == 0
    with pytest.raises(inv.InventoryError):
        inv.delete_product(s, mgr, used.id)
    inv.update_product(s, mgr, used.id, {"is_active": False})          # the offered alternative
    assert used.is_active is False


def test_edit_in_stock_device_and_imei_uniqueness(db_session, mgr):
    s = db_session
    phone = _product(s, mgr, "Phone", imei=True)
    d1, d2 = inv.add_devices(s, mgr, phone, [{"imei1": "490154203237518"}, {"imei1": "352001111222333"}])
    s.commit()
    inv.update_device(s, mgr, d1.id, {"imei2": "111111111111119", "condition": "used", "notes": " scratch ",
                                       "purchase_cost": egp("4000"), "extra_cost": egp("50")})
    assert d1.condition == "used" and d1.notes == "scratch" and d1.total_cost == egp("4050")
    with pytest.raises(inv.DuplicateIMEI):
        inv.update_device(s, mgr, d2.id, {"imei1": d1.imei1})
    with pytest.raises(inv.InventoryError):
        inv.update_device(s, mgr, d2.id, {"imei1": " "})


def test_delete_mistaken_device_keeps_stock_in_sync(db_session, mgr):
    s = db_session
    phone = _product(s, mgr, "Phone", imei=True)
    d1, d2 = inv.add_devices(s, mgr, phone, [{"imei1": "490154203237518"}, {"imei1": "352001111222333"}])
    s.commit()
    inv.delete_device(s, mgr, d1.id)
    s.commit()
    assert s.get(Device, d1.id) is None and phone.current_quantity() == 1
    assert inv.stock_matches_movements(s, phone)
    assert s.query(StockMovement).filter_by(device_id=d1.id).count() == 0


def test_sold_device_is_locked_and_cannot_be_deleted(db_session, mgr):
    s = db_session
    phone = _product(s, mgr, "Phone", imei=True)
    (dev,) = inv.add_devices(s, mgr, phone, [{"imei1": "490154203237518"}])
    shift_service.open_shift(s, mgr, opening_cash=0)
    sale = sales_service.start_sale(s, mgr)
    sales_service.add_line(s, mgr, sale, phone, device=dev)
    sales_service.post_sale(s, mgr, sale, [{"method": "cash", "amount": sale.total}])
    s.commit()
    with pytest.raises(inv.InventoryError):
        inv.delete_device(s, mgr, dev.id)
    with pytest.raises(inv.InventoryError):
        inv.update_device(s, mgr, dev.id, {"imei1": "999999999999999"})
    inv.update_device(s, mgr, dev.id, {"notes": "customer called"})     # notes always allowed
    with pytest.raises(inv.InventoryError):
        inv.write_off_device(s, mgr, dev.id, "lost")


def test_write_off_in_stock_device(db_session, mgr):
    s = db_session
    phone = _product(s, mgr, "Phone", imei=True)
    d1, d2 = inv.add_devices(s, mgr, phone, [{"imei1": "490154203237518"}, {"imei1": "352001111222333"}])
    s.commit()
    with pytest.raises(inv.InventoryError):
        inv.write_off_device(s, mgr, d1.id, "  ")
    inv.write_off_device(s, mgr, d1.id, "water damage")
    s.commit()
    assert d1.status == "damaged" and phone.current_quantity() == 1
    assert inv.stock_matches_movements(s, phone)
