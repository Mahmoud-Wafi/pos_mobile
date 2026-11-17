"""Excel/CSV import with preview and per-row errors, templates, and real .xlsx export."""
import csv

import pytest
from openpyxl import Workbook, load_workbook

from app.core.imei import luhn_valid, normalize_imei
from app.core.money import egp_to_piasters as E
from app.core.permissions import PermissionDenied, ROLE_CASHIER, ROLE_MANAGER
from app.core.security import hash_password
from app.models.product import Product
from app.models.stock import Device
from app.models.user import AuditLog, Role, User
from app.services import import_export_service as ie
from app.services import inventory_service

GOOD_IMEI = "356938035643809"      # valid Luhn


def _user(s, name, role):
    r = s.query(Role).filter_by(name=role).first()
    u = User(username=name, password_hash=hash_password("Passw0rd!"), full_name=name, role_id=r.id)
    s.add(u); s.commit()
    return u


@pytest.fixture
def mgr(db_session):
    return _user(db_session, "m", ROLE_MANAGER)


def _xlsx(path, headers, rows):
    wb = Workbook(); ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    wb.save(path)
    return path


def test_luhn_and_normalize():
    assert luhn_valid(GOOD_IMEI) and not luhn_valid("356938035643808") and not luhn_valid("123")
    assert normalize_imei("٣٥٦-٩٣٨ 035643809") == GOOD_IMEI


def test_products_arabic_headers_preview_and_commit(db_session, mgr, tmp_path):
    f = _xlsx(tmp_path / "p.xlsx", ie.PRODUCT_TEMPLATE_HEADERS, [
        ["سماعة", "اكسسوار", "111", "Anker", "150", "250", "200", "3", "10", "لا", "90"],
        ["شاحن", "اكسسوار", "222", "", "١٠٠٫٥", "180", "", "", "5", "", ""],     # Arabic digits, blanks
        ["", "اكسسوار", "", "", "1", "2", "", "", "", "", ""],                    # missing name
        ["كابل", "شيء", "333", "", "1", "2", "", "", "", "", ""],                 # bad type
        ["مكرر", "اكسسوار", "111", "", "1", "2", "", "", "", "", ""],             # duplicate barcode in file
        ["رخيص", "اكسسوار", "", "", "100", "50", "80", "", "", "", ""],           # min > sale
    ])
    prev = ie.preview_products(db_session, mgr, f)
    assert [r.ok for r in prev.rows] == [True, True, False, False, False, False]
    assert prev.rows[1].data["cost_price"] == 10050
    assert any("الاسم" in e for e in prev.rows[2].errors)
    assert prev.rows[2].row_no == 4
    assert db_session.query(Product).count() == 0              # preview writes nothing
    n = ie.commit_products(db_session, mgr, prev)
    db_session.commit()
    assert n == 2 and db_session.query(Product).count() == 2
    cable = db_session.query(Product).filter_by(name="سماعة").one()
    assert cable.current_quantity() == 10 and cable.brand.name == "Anker" and cable.warranty_days == 90
    assert db_session.query(AuditLog).filter_by(action="import_products").count() == 1


def test_english_headers_and_csv(db_session, mgr, tmp_path):
    p = tmp_path / "p.csv"
    with open(p, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["name", "type", "barcode", "cost_price", "sale_price", "quantity"])
        w.writerow(["Cable", "accessory", "9", "10", "20", "4"])
    prev = ie.preview_products(db_session, mgr, p)
    assert prev.rows[0].ok and prev.rows[0].data["quantity"] == 4


def test_existing_barcode_is_reported(db_session, mgr, tmp_path):
    inventory_service.create_product(db_session, mgr, {"name": "Old", "type": "accessory", "barcode": "777",
                                                        "cost_price": 1, "sale_price": 2})
    db_session.commit()
    f = _xlsx(tmp_path / "p.xlsx", ["الاسم", "الباركود"], [["New", "777"]])
    assert not ie.preview_products(db_session, mgr, f).rows[0].ok


def test_missing_name_column_and_bad_files(db_session, mgr, tmp_path):
    with pytest.raises(ie.ImportExportError):
        ie.preview_products(db_session, mgr, _xlsx(tmp_path / "a.xlsx", ["x", "y"], [["1", "2"]]))
    junk = tmp_path / "junk.xlsx"; junk.write_bytes(b"nope")
    with pytest.raises(ie.ImportExportError):
        ie.preview_products(db_session, mgr, junk)
    with pytest.raises(ie.ImportExportError):
        ie.preview_products(db_session, mgr, tmp_path / "missing.xlsx")
    txt = tmp_path / "a.txt"; txt.write_text("x")
    with pytest.raises(ie.ImportExportError):
        ie.preview_products(db_session, mgr, txt)


def test_cashier_cannot_import(db_session, tmp_path):
    cashier = _user(db_session, "c", ROLE_CASHIER)
    with pytest.raises(PermissionDenied):
        ie.preview_products(db_session, cashier, _xlsx(tmp_path / "a.xlsx", ["الاسم"], [["x"]]))


def test_devices_import_validates_imei(db_session, mgr, tmp_path):
    phone = inventory_service.create_product(db_session, mgr, {
        "name": "Samsung A15", "type": "phone", "cost_price": E("7000"), "sale_price": E("8000"),
        "min_price": E("7500"), "track_imei": True})
    db_session.commit()
    f = _xlsx(tmp_path / "d.xlsx", ie.DEVICE_TEMPLATE_HEADERS, [
        ["Samsung A15", GOOD_IMEI, "", "جديد", "7500"],
        ["Samsung A15", "356938035643808", "", "مستعمل", ""],       # Luhn fails -> warning only
        ["Samsung A15", "12345", "", "", ""],                       # too short -> error
        ["Samsung A15", GOOD_IMEI, "", "", ""],                     # duplicate in file
        ["Unknown", "490154203237518", "", "", ""],                 # unknown product
        ["Samsung A15", "490154203237518", "", "تالف", ""],         # bad condition
    ])
    prev = ie.preview_devices(db_session, mgr, f)
    assert [r.ok for r in prev.rows] == [True, True, False, False, False, False]
    assert prev.rows[1].warnings and prev.rows[1].data["purchase_cost"] == E("7000")   # defaults to product cost
    n = ie.commit_devices(db_session, mgr, prev)
    db_session.commit()
    assert n == 2 and db_session.query(Device).count() == 2 and phone.current_quantity() == 2
    again = ie.preview_devices(db_session, mgr, f)                  # now already in stock
    assert not again.rows[0].ok


def test_templates_roundtrip_and_are_rtl(db_session, mgr, tmp_path):
    for kind in ("products", "devices"):
        p = ie.write_template(kind, tmp_path / f"{kind}.xlsx")
        wb = load_workbook(p)
        assert wb.active.sheet_view.rightToLeft is True
        assert wb.active["A1"].font.bold
    headers, rows = ie.read_table(tmp_path / "products.xlsx")
    assert headers == ie.PRODUCT_TEMPLATE_HEADERS and len(rows) == 1
    prev = ie.preview_products(db_session, mgr, tmp_path / "products.xlsx")       # the example row is valid
    assert prev.rows[0].ok


def test_export_xlsx_and_csv(db_session, mgr, tmp_path):
    p = inventory_service.create_product(db_session, mgr, {"name": "Cable", "type": "accessory", "cost_price": E("50"),
                                                            "sale_price": E("100.5"), "min_price": E("80")})
    inventory_service.adjust_stock(db_session, mgr, p, 7, "init")
    db_session.commit()
    x = ie.export_products(db_session, mgr, tmp_path / "out.xlsx")
    ws = load_workbook(x).active
    assert ws.sheet_view.rightToLeft is True
    head = [c.value for c in ws[1]]
    assert "سعر التكلفة" in head
    row = {h: c.value for h, c in zip(head, ws[2])}
    assert row["الاسم"] == "Cable" and row["سعر البيع"] == 100.5 and row["الكمية"] == 7
    c = ie.export_products(db_session, mgr, tmp_path / "out.csv")
    raw = c.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")                                       # BOM for Excel
    assert "Cable" in raw.decode("utf-8-sig")


def test_cashier_export_hides_cost(db_session, mgr, tmp_path):
    inventory_service.create_product(db_session, mgr, {"name": "Cable", "type": "accessory", "cost_price": E("50"),
                                                        "sale_price": E("100")})
    db_session.commit()
    cashier = _user(db_session, "c2", ROLE_CASHIER)
    ws = load_workbook(ie.export_products(db_session, cashier, tmp_path / "c.xlsx")).active
    assert "سعر التكلفة" not in [c.value for c in ws[1]]


def test_export_report_xlsx(mgr, tmp_path):
    data = {"rows": [{"invoice": "INV-1", "total": 12550, "customer": "x"}]}
    ws = load_workbook(ie.export_report(mgr, data, tmp_path / "r.xlsx")).active
    assert [c.value for c in ws[2]] == ["INV-1", 125.5, "x"]
