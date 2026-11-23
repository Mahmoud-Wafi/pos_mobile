"""POS scan flow, cart editing, held invoices, payment shortcuts, invoice history (offscreen)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QDialog

from app.core.money import egp_to_piasters as E
from app.core.permissions import ROLE_CASHIER, ROLE_MANAGER
from app.core.security import hash_password
from app.models.user import Role, User
from app.services import inventory_service, sales_service, shift_service


def _user(s, name, role):
    r = s.query(Role).filter_by(name=role).first()
    u = User(username=name, password_hash=hash_password("Passw0rd!"), full_name=name, role_id=r.id)
    s.add(u); s.commit()
    return u


@pytest.fixture
def shop(db_session):
    s = db_session
    mgr, cash = _user(s, "m", ROLE_MANAGER), _user(s, "c", ROLE_CASHIER)
    cable = inventory_service.create_product(s, mgr, {
        "name": "Cable USB", "type": "accessory", "cost_price": E("50"), "sale_price": E("100"),
        "min_price": E("80"), "min_stock": 1, "track_imei": False, "warranty_days": 0})
    inventory_service.adjust_stock(s, mgr, cable, 10, "init")
    phone = inventory_service.create_product(s, mgr, {
        "name": "Phone X", "type": "phone", "cost_price": E("1000"), "sale_price": E("1500"),
        "min_price": E("1200"), "min_stock": 0, "track_imei": True, "warranty_days": 365})
    inventory_service.add_devices(s, mgr, phone, [
        {"imei1": "111111111111111", "condition": "new", "purchase_cost": E("1000")},
        {"imei1": "222222222222222", "condition": "new", "purchase_cost": E("1000")}])
    s.commit()
    shift_service.open_shift(s, cash, opening_cash=0)
    s.commit()
    return s, mgr, cash, cable, phone


def _pos(qtbot, s, user):
    from app.ui.pos.pos_window import POSWindow
    w = POSWindow(s, user)
    qtbot.addWidget(w)
    return w


def test_scan_same_accessory_bumps_quantity(qtbot, shop):
    s, mgr, cash, cable, phone = shop
    w = _pos(qtbot, s, cash)
    w._add_to_cart(cable); w._add_to_cart(cable)
    assert len(w.current_sale.items) == 1 and w.current_sale.items[0].quantity == 2


def test_imei_scan_adds_that_exact_unit(qtbot, shop):
    s, mgr, cash, cable, phone = shop
    w = _pos(qtbot, s, cash)
    w.scan_edit.setText("222222222222222")
    w._on_scan_or_search()
    assert [i.device.imei1 for i in w.current_sale.items] == ["222222222222222"]


def test_same_device_cannot_be_added_twice(qtbot, shop):
    s, mgr, cash, cable, phone = shop
    w = _pos(qtbot, s, cash)
    dev = inventory_service.find_by_barcode_or_imei(s, "111111111111111")
    w._add_to_cart(dev.product, device=dev)
    with pytest.raises(sales_service.SaleError):
        w._add_to_cart(dev.product, device=dev)


def test_devices_listed_oldest_first(shop):
    s, mgr, cash, cable, phone = shop
    devs = inventory_service.get_devices_for_product(s, phone.id, status="in_stock")
    assert [d.imei1 for d in devs] == ["111111111111111", "222222222222222"]


def test_remove_then_undo_restores_line(qtbot, shop):
    s, mgr, cash, cable, phone = shop
    w = _pos(qtbot, s, cash)
    w._add_to_cart(cable)
    w._remove_item(w.current_sale.items[0].id)
    assert not w.current_sale.items and not w.undo_bar.isHidden()
    w._undo_remove()
    assert len(w.current_sale.items) == 1 and w.current_sale.total == E("100")


def test_empty_drafts_not_listed_as_held(qtbot, shop, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.Ok)
    s, mgr, cash, cable, phone = shop
    w = _pos(qtbot, s, cash)
    w._new_invoice(); w._new_invoice()
    assert sales_service.list_held_sales(s) == []
    w._add_to_cart(cable)
    w._hold_invoice()
    held = sales_service.list_held_sales(s)
    assert len(held) == 1 and held[0].items


def test_payment_quick_cash_and_change(qtbot):
    from app.ui.pos.payment_dialog import PaymentDialog
    d = PaymentDialog(E("350"), "x")
    qtbot.addWidget(d)
    d._set_cash(E("500"))
    assert d.btn_confirm.isEnabled()
    assert "150" in d.lbl_rem_val.text()
    d._confirm()
    assert d.payments_breakdown == [{"method": "cash", "amount": E("500")}]


def test_payment_cash_autofills_remainder(qtbot):
    from app.ui.pos.payment_dialog import PaymentDialog
    d = PaymentDialog(E("350"), "x")
    qtbot.addWidget(d)
    d.wallet_edit.setText("100")
    d.wallet_edit.textEdited.emit("100")
    assert d.cash_edit.text() in ("250", "250.00")


def test_history_search_return_void(qtbot, shop):
    from app.ui.invoices.history_view import InvoiceHistoryWidget
    s, mgr, cash, cable, phone = shop
    sale = sales_service.start_sale(s, cash)
    sales_service.add_line(s, cash, sale, cable, quantity=2)
    sales_service.post_sale(s, cash, sale, [{"method": "cash", "amount": sale.total}])
    s.commit()
    w = InvoiceHistoryWidget(s, cash)
    qtbot.addWidget(w)
    w.refresh()
    assert w.table.rowCount() == 1
    assert not w.b_void.isVisibleTo(w)           # cashier cannot void
    mw = InvoiceHistoryWidget(s, mgr)
    qtbot.addWidget(mw)
    mw.refresh()
    assert mw.table.rowCount() == 1 and mw.b_void.isVisibleTo(mw)
    mw.show()
    mw.table.setCurrentCell(0, 0)
    assert mw.b_void.isEnabled() and "Cable USB" in mw.details.toPlainText()
    sales_service.void_sale(s, mgr, sale.id, "test")
    s.commit()
    mw.refresh()
    assert mw.table.item(0, 4).text() == "ملغاة"


def test_cashier_history_limited_to_own(shop):
    s, mgr, cash, cable, phone = shop
    shift_service.open_shift(s, mgr, opening_cash=0); s.commit()
    sale = sales_service.start_sale(s, mgr)
    sales_service.add_line(s, mgr, sale, cable)
    sales_service.post_sale(s, mgr, sale, [{"method": "cash", "amount": sale.total}])
    s.commit()
    assert sales_service.search_sales(s, cash) == []
    assert len(sales_service.search_sales(s, mgr)) == 1


def test_switching_screens_keeps_the_draft_invoice(qtbot, db_session):
    """Regression: a screen switch used to roll back and detach the POS draft sale."""
    from app.core.security import hash_password
    from app.models.user import Role, User
    from app.services import sales_service
    from app.ui.main_window import MainWindow

    role = db_session.query(Role).filter_by(name="manager").first()
    u = User(username="sw", password_hash=hash_password("Passw0rd!"), full_name="sw", role_id=role.id)
    db_session.add(u)
    db_session.commit()
    win = MainWindow(user_id=u.id)
    qtbot.addWidget(win)
    win.show()
    win._show_pos()
    sale = win.pos_view.current_sale
    win._show_dashboard()
    win._show_pos()
    assert sale in win.session            # still attached
    assert sale.status == "held"
    assert sales_service.list_held_sales(win.session) is not None


def test_catalogue_card_click_adds_to_cart_and_filters(qtbot, shop):
    s, mgr, cash, cable, phone = shop
    w = _pos(qtbot, s, cash)
    w.resize(1200, 800)
    w.show()
    qtbot.wait(30)
    grid = w.product_grid
    assert {p.name for p in grid.visible_products()} == {"Cable USB", "Phone X"}
    # category chip and the scan box both narrow the grid
    grid._set_type("phone")
    assert [p.name for p in grid.visible_products()] == ["Phone X"]
    grid._set_type("all")
    w.scan_edit.setText("cable")
    assert [p.name for p in grid.visible_products()] == ["Cable USB"]
    # clicking an accessory card = scanning it
    card = next(c for c in grid._cards if c.product_id == cable.id)
    card.clicked.emit()
    assert len(w.current_sale.items) == 1 and w.current_sale.items[0].product_id == cable.id


def test_catalogue_disables_sold_out_accessory(qtbot, shop):
    s, mgr, cash, cable, phone = shop
    inventory_service.adjust_stock(s, mgr, cable, 0, "empty")
    s.commit()
    w = _pos(qtbot, s, cash)
    w.show()
    qtbot.wait(30)
    card = next(c for c in w.product_grid._cards if c.product_id == cable.id)
    got = []
    card.clicked.connect(lambda: got.append(1))
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    QTest.mouseClick(card, Qt.LeftButton)
    assert not got
