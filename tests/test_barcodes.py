import pytest

from app.core.money import egp_to_piasters as egp
from app.core.permissions import ROLE_MANAGER
from app.core.security import hash_password
from app.models.product import ProductBarcode
from app.models.user import Role, User
from app.services import inventory_service as inv


def _mgr(s):
    r = s.query(Role).filter_by(name=ROLE_MANAGER).first()
    u = User(username="bm", password_hash=hash_password("Passw0rd!"), full_name="b", role_id=r.id)
    s.add(u)
    s.commit()
    return u


def _prod(s, u, name, **extra):
    p = inv.create_product(s, u, {"name": name, "type": "accessory", "cost_price": egp("1"),
                                  "sale_price": egp("2"), "min_price": 0, "min_stock": 0,
                                  "track_imei": False, "warranty_days": 0, **extra})
    s.commit()
    return p


def test_normalize_handles_arabic_digits_spaces_and_scanner_newline():
    assert inv.normalize_barcode(" ٦٢٢١٢٣ 45\r\n") == "62212345"
    assert inv.normalize_barcode(None) == ""


def test_any_barcode_finds_the_same_product(db_session):
    s, u = db_session, _mgr(db_session)
    p = _prod(s, u, "Cable", barcode="111", extra_barcodes=["222", "٣٣٣"])
    for code in ("111", "222", "333", " 222\n"):
        assert inv.find_product_by_barcode(s, code) is p
        assert inv.find_by_barcode_or_imei(s, code) is p
    assert inv.find_product_by_barcode(s, "999") is None
    assert p.all_barcodes() == ["111", "222", "333"]
    assert inv.find_product_by_barcode(s, f"P{p.id:06d}") is p      # the code printed on labels


def test_search_matches_extra_barcodes(db_session):
    s, u = db_session, _mgr(db_session)
    p = _prod(s, u, "Cable", barcode="111", extra_barcodes=["222"])
    _prod(s, u, "Other", barcode="333")
    assert inv.search_products(s, "222") == [p]


def test_barcode_cannot_belong_to_two_products(db_session):
    s, u = db_session, _mgr(db_session)
    a = _prod(s, u, "A", barcode="111", extra_barcodes=["222"])
    with pytest.raises(inv.InventoryError):
        _prod(s, u, "B", barcode="222")                         # main barcode clashes with an extra one
    b = _prod(s, u, "B", barcode="333")
    with pytest.raises(inv.InventoryError):
        inv.update_product(s, u, b.id, {"extra_barcodes": ["111"]})
    with pytest.raises(inv.InventoryError):
        inv.update_product(s, u, b.id, {"barcode": "222"})
    inv.update_product(s, u, a.id, {"extra_barcodes": ["444"]})  # replaces the list
    assert a.all_barcodes() == ["111", "444"] and s.query(ProductBarcode).count() == 1


def test_deleting_an_unused_product_removes_its_extra_barcodes(db_session):
    s, u = db_session, _mgr(db_session)
    p = _prod(s, u, "Gone", barcode="111", extra_barcodes=["222"])
    inv.delete_product(s, u, p.id)
    s.commit()
    assert s.query(ProductBarcode).count() == 0 and inv.find_product_by_barcode(s, "222") is None
