"""Arabic PDFs: Cairo font embedded, Arabic text present, shop settings used."""
import os
import shutil
import unicodedata

import pytest
from pypdf import PdfReader

from app.core.money import egp_to_piasters
from app.core.permissions import ROLE_CASHIER, ROLE_MANAGER
from app.core.security import hash_password
from app.models.accounting import CashAccount
from app.models.user import Role, User
from app.printing.receipt import generate_warranty_invoice_pdf
from app.services import inventory_service, purchase_service, sales_service, settings_service, shift_service


def _text(path) -> str:
    raw = "".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    return unicodedata.normalize("NFKC", raw)      # presentation forms -> base Arabic letters


def _fonts(path) -> set[str]:
    names = set()
    for page in PdfReader(str(path)).pages:
        for f in (page["/Resources"].get("/Font") or {}).values():
            names.add(str(f.get_object()["/BaseFont"]))
    return names


def _letters_present(expected: str, text: str) -> bool:
    return {c for c in expected if not c.isspace()} <= set(text)


def _export(path, name):
    out = os.environ.get("PDF_OUT")
    if out:
        os.makedirs(out, exist_ok=True)
        shutil.copy(path, os.path.join(out, name))


@pytest.fixture
def people(db_session):
    def mk(name, role):
        r = db_session.query(Role).filter_by(name=role).first()
        u = User(username=name, password_hash=hash_password("Passw0rd!"), full_name="سعيد " + name, role_id=r.id)
        db_session.add(u)
        db_session.commit()
        return u
    return mk("mgr", ROLE_MANAGER), mk("csh", ROLE_CASHIER)


@pytest.fixture
def phone(db_session, people):
    mgr, _ = people
    inventory_service.create_category(db_session, mgr, "Phones")
    p = inventory_service.create_product(db_session, mgr, {
        "name": "آيفون 15 برو", "type": "phone", "cost_price": egp_to_piasters("40000"),
        "sale_price": egp_to_piasters("46000"), "min_price": egp_to_piasters("44000"),
        "min_stock": 1, "track_imei": True, "warranty_days": 365})
    db_session.commit()
    return p


def test_invoice_pdf_arabic(db_session, people, phone, tmp_path):
    mgr, cashier = people
    shift_service.open_shift(db_session, cashier, opening_cash=0)
    dev = inventory_service.add_devices(db_session, mgr, phone, [
        {"imei1": "352001111222333", "condition": "new", "purchase_cost": egp_to_piasters("40000")}])[0]
    db_session.commit()
    sale = sales_service.start_sale(db_session, cashier)
    sales_service.add_line(db_session, cashier, sale, phone, device=dev)
    sales_service.post_sale(db_session, cashier, sale, [{"method": "cash", "amount": sale.total}])
    db_session.commit()

    out = generate_warranty_invoice_pdf(
        sale, tmp_path / "inv.pdf", shop_name="محل النور للموبايلات", warranty_text="ضمان سنة كاملة على الجهاز",
        shop_phone="01012345678", shop_address="القاهرة - شارع التحرير", footer="شكراً لزيارتكم")
    text = _text(out)
    assert _letters_present("محل النور للموبايلات", text)
    assert _letters_present("ضمان سنة كاملة", text)
    assert _letters_present("فاتورة بيع وشهادة ضمان", text)
    assert "352001111222333" in text and sale.invoice_no in text and "01012345678" in text
    assert any("Cairo" in f for f in _fonts(out)), _fonts(out)
    _export(out, "invoice.pdf")


def test_declaration_pdf_arabic_and_settings(db_session, people, phone, tmp_path):
    mgr, _ = people
    drawer = db_session.query(CashAccount).filter_by(type="drawer").first()   # the seeded drawer is the one used
    drawer.balance = egp_to_piasters("100000")
    db_session.commit()
    settings_service.update(db_session, mgr, {"shop_name": "محل الأمل", "shop_phone": "0223456789"})
    used = purchase_service.record_used_device_purchase(
        db_session, mgr, seller_name="أحمد محمود حسن إبراهيم", seller_national_id="29501011234567",
        seller_phone="01099887766", product_id=phone.id, imei1="352011998877665",
        price=egp_to_piasters(32000), condition_notes="حالة ممتازة، بطارية 95%")
    db_session.commit()

    path = purchase_service.generate_declaration(db_session, mgr, used.id, dest_path=tmp_path / "decl.pdf")
    text = _text(path)
    assert _letters_present("أحمد محمود حسن إبراهيم", text)
    assert _letters_present("إقرار بيع وتنازل ملكية جهاز مستعمل", text)
    assert _letters_present("محل الأمل", text)                 # shop name came from settings
    assert "29501011234567" in text and "352011998877665" in text and "0223456789" in text
    assert any("Cairo" in f for f in _fonts(path))
    _export(path, "declaration.pdf")


def test_shaped_arabic_has_no_missing_glyphs():
    """Every character emitted by shape() must exist in the bundled Cairo font."""
    from app.printing import pdf_common as pc

    sample = ("محل النور للموبايلات المجموع الفرعي ضمان سنة كاملة على الجهاز إقرار بيع وتنازل ملكية "
              "أحمد محمود حسن إبراهيم الرقم القومي رقم الهاتف توقيع البائع بصمة إبهام العين زين نون")
    have = pc._supported()
    missing = {hex(ord(c)) for c in pc.shape(sample) if not c.isspace() and ord(c) not in have}
    assert not missing, missing


def test_dates_stay_left_to_right_in_arabic_line():
    from app.printing import pdf_common as pc

    shaped = pc.shape("التاريخ: " + pc.ltr("2026-11-14 22:47"))
    assert shaped.startswith("2026-11-14 22:47")      # visual order: date block intact, label to its right
