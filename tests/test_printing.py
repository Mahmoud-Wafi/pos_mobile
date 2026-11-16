"""Thermal receipt HTML/PDF and the post-sale print dialog (offscreen)."""
import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pypdf import PdfReader

from app.core.money import egp_to_piasters
from app.core.permissions import ROLE_CASHIER, ROLE_MANAGER
from app.core.security import hash_password
from app.models.user import Role, User
from app.services import inventory_service, sales_service, settings_service, shift_service


@pytest.fixture
def posted_sale(db_session):
    def mk(name, role):
        r = db_session.query(Role).filter_by(name=role).first()
        u = User(username=name, password_hash=hash_password("Passw0rd!"), full_name="كاشير " + name, role_id=r.id)
        db_session.add(u)
        db_session.commit()
        return u
    mgr, cashier = mk("pm", ROLE_MANAGER), mk("pc", ROLE_CASHIER)
    shift_service.open_shift(db_session, cashier, opening_cash=0)
    inventory_service.create_category(db_session, mgr, "Acc")
    p = inventory_service.create_product(db_session, mgr, {
        "name": "شاحن سريع", "type": "accessory", "cost_price": egp_to_piasters("200"),
        "sale_price": egp_to_piasters("350"), "min_price": egp_to_piasters("300"),
        "min_stock": 1, "track_imei": False, "warranty_days": 30})
    inventory_service.adjust_stock(db_session, mgr, p, 5, "init")
    db_session.commit()
    sale = sales_service.start_sale(db_session, cashier)
    sales_service.add_line(db_session, cashier, sale, p, quantity=2)
    sales_service.apply_discount(db_session, cashier, sale, egp_to_piasters("10"))
    sales_service.post_sale(db_session, cashier, sale, [{"method": "cash", "amount": sale.total}])
    db_session.commit()
    settings_service.update(db_session, mgr, {"shop_name": "محل النور", "invoice_footer": "نشكركم على ثقتكم",
                                              "shop_phone": "01012345678"})
    db_session.commit()
    return sale


def test_receipt_html_contains_settings_and_totals(db_session, posted_sale):
    from app.printing.thermal import receipt_html

    html = receipt_html(posted_sale, settings_service.get_all(db_session))
    for needle in ("محل النور", "نشكركم على ثقتكم", "01012345678", "شاحن سريع", posted_sale.invoice_no,
                   'dir="rtl"', "690.00"):
        assert needle in html, needle


def test_receipt_renders_to_narrow_pdf(qtbot, db_session, posted_sale, tmp_path):
    from app.ui.print_dialogs import render_receipt_pdf

    out = render_receipt_pdf(posted_sale, settings_service.get_all(db_session), tmp_path / "r.pdf")
    reader = PdfReader(str(out))
    assert len(reader.pages) == 1
    width_mm = float(reader.pages[0].mediabox.width) / 72 * 25.4
    assert 78 <= width_mm <= 82                    # 80 mm roll
    text = reader.pages[0].extract_text() or ""
    # Qt maps the hyphens of "INV-20261116-0001" to private-use glyphs, so compare the digit groups
    assert all(part in text for part in re.findall(r"\d+", posted_sale.invoice_no))
    assert "690.00" in text


def test_post_sale_dialog_builds_a4_pdf(qtbot, db_session, posted_sale, monkeypatch, tmp_path):
    from app.ui import print_dialogs as pd

    monkeypatch.setattr(pd, "DATA_DIR", tmp_path)
    opened = []
    monkeypatch.setattr(pd, "open_file", lambda p: opened.append(p))
    dlg = pd.SaleCompleteDialog(db_session, posted_sale)
    qtbot.addWidget(dlg)
    dlg.open_a4()
    assert len(opened) == 1 and opened[0].exists() and opened[0].name == f"{posted_sale.invoice_no}.pdf"
    assert len(dlg.findChildren(pd.QPushButton)) == 4      # receipt, preview, A4, new sale


def test_receipt_html_date_is_ltr_isolated(db_session, posted_sale):
    from app.printing.thermal import receipt_html

    assert "\u2066" in receipt_html(posted_sale, settings_service.get_all(db_session))
