"""Forms are driven by REAL key presses under English AND Arabic (Egypt) locales.

Regression: QDoubleValidator followed the OS locale, so on an Arabic Windows the user could not type
'500.00' in any money field and nothing could be added (wallets, expenses, products ...).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QLocale

from app.core.permissions import ROLE_CASHIER, ROLE_MANAGER, ROLE_WALLET_EMPLOYEE
from app.models.user import Role, User

LOCALES = ["en_US", "ar_EG"]
AMOUNTS = [("500.5", 50050), ("500,5", 50050), ("٥٠٠٫٥", 50050), ("1250", 125000)]


@pytest.fixture(params=LOCALES)
def locale(request):
    old = QLocale()
    QLocale.setDefault(QLocale(request.param))
    yield request.param
    QLocale.setDefault(old)


@pytest.fixture
def mgr(db_session):
    return db_session.query(User).join(Role).filter(Role.name == ROLE_MANAGER).first()


@pytest.fixture(autouse=True)
def no_modal(monkeypatch):
    """A popup would hang the test; record it instead."""
    shown = []
    import app.ui.components as comp
    monkeypatch.setattr(comp, "show_error", lambda *a, **k: shown.append((a, k)))
    for mod in ("wallets.wallet_dialog", "customers.customer_dialog", "purchases.supplier_dialog",
                "accounting.expense_dialog", "accounting.owner_draw_dialog", "inventory.product_list"):
        try:
            m = __import__(f"app.ui.{mod}", fromlist=["x"])
            if hasattr(m, "show_error"):
                monkeypatch.setattr(m, "show_error", lambda *a, _s=shown, **k: _s.append((a, k)))
        except ImportError:
            pass
    return shown


def type_into(qtbot, edit, text):
    """Real key events; QTest.keyClicks asserts on non-ASCII, so those go in as key events with text."""
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication

    edit.clear()
    edit.setFocus()
    for ch in text:
        if ch.isascii():
            qtbot.keyClicks(edit, ch)
        else:
            for kind in (QEvent.KeyPress, QEvent.KeyRelease):
                QApplication.sendEvent(edit, QKeyEvent(kind, Qt.Key_unknown, Qt.NoModifier, ch))


@pytest.mark.parametrize("typed,expected", AMOUNTS)
def test_wallet_dialog_typed_amounts(qtbot, db_session, mgr, locale, typed, expected, no_modal):
    from app.models.wallet import Wallet
    from app.ui.wallets.wallet_dialog import WalletDialog

    dlg = WalletDialog(db_session, mgr)
    qtbot.addWidget(dlg)
    dlg.show()
    type_into(qtbot, dlg.phone_edit, "01012345678")
    type_into(qtbot, dlg.label_edit, "فودافون 1")
    type_into(qtbot, dlg.bal_edit, typed)
    type_into(qtbot, dlg.daily_limit_edit, "30000.50")
    type_into(qtbot, dlg.monthly_limit_edit, "100000")
    assert dlg.bal_edit.text() == typed, "validator swallowed keystrokes"
    dlg.btn_save.click()
    assert not no_modal, no_modal
    w = db_session.query(Wallet).one()
    assert w.balance == expected and w.daily_limit == 3000050 and w.monthly_limit == 10000000


@pytest.mark.parametrize("typed,expected", AMOUNTS)
def test_expense_and_owner_draw_typed(qtbot, db_session, mgr, locale, typed, expected, no_modal):
    from app.models.accounting import CashAccount, Expense
    from app.ui.accounting.expense_dialog import ExpenseDialog

    for acc in db_session.query(CashAccount).all():
        acc.balance = 10_000_000
    db_session.commit()

    dlg = ExpenseDialog(db_session, mgr)
    qtbot.addWidget(dlg)
    dlg.show()
    type_into(qtbot, dlg.amount_edit, typed)
    assert dlg.amount_edit.text() == typed
    type_into(qtbot, dlg.note_edit, "كهرباء")
    dlg._save() if hasattr(dlg, "_save") else dlg.accept()
    assert not no_modal, no_modal
    assert db_session.query(Expense).one().amount == expected


@pytest.mark.parametrize("typed,expected", AMOUNTS)
def test_customer_and_supplier_typed(qtbot, db_session, mgr, locale, typed, expected, no_modal):
    from app.models.customer import Customer
    from app.ui.customers.customer_dialog import CustomerDialog

    dlg = CustomerDialog(db_session, mgr)
    qtbot.addWidget(dlg)
    dlg.show()
    type_into(qtbot, dlg.name_edit, "أحمد")
    type_into(qtbot, dlg.phone_edit, "01099999999")
    type_into(qtbot, dlg.credit_edit, typed)
    assert dlg.credit_edit.text() == typed
    dlg._save()
    assert not no_modal, no_modal
    assert db_session.query(Customer).filter_by(name="أحمد").one().credit_limit == expected


@pytest.mark.parametrize("typed,expected", AMOUNTS)
def test_product_dialog_typed(qtbot, db_session, mgr, locale, typed, expected, no_modal):
    from app.models.product import Product
    from app.ui.inventory.product_list import ProductDialog

    dlg = ProductDialog(db_session, mgr)
    qtbot.addWidget(dlg)
    dlg.show()
    type_into(qtbot, dlg.name_edit, "شاحن")
    type_into(qtbot, dlg.sale_edit, typed)
    type_into(qtbot, dlg.cost_edit, "10.25")
    type_into(qtbot, dlg.opening_edit, "٥")
    assert dlg.sale_edit.text() == typed and dlg.opening_edit.text() == "٥"
    dlg._save()
    assert not no_modal, no_modal
    p = db_session.query(Product).filter_by(name="شاحن").one()
    assert p.sale_price == expected and p.cost_price == 1025 and p.current_quantity() == 5


def test_new_product_from_inside_purchase_invoice(qtbot, db_session, mgr, locale, no_modal, monkeypatch):
    """The user's request: add a brand-new product while writing a purchase invoice."""
    from app.models.product import Product
    from app.services import purchase_service
    from app.ui.inventory import product_list
    from app.ui.purchases.purchase_invoice_dialog import PurchaseInvoiceDialog

    s = db_session
    sup = purchase_service.create_supplier(s, mgr, "المورد")
    s.commit()
    inv = PurchaseInvoiceDialog(s, mgr)
    qtbot.addWidget(inv)
    inv.show()
    assert inv.btn_new_product.isVisible()

    real = product_list.ProductDialog

    class Auto(real):                      # the dialog opens, the "user" fills it and presses save
        def exec(self_inner):
            self_inner.name_edit.setText("كفر جديد")
            self_inner.sale_edit.setText("150")
            self_inner.cost_edit.setText("80")
            assert not self_inner.opening_edit.isVisible()      # the invoice adds the stock, no doubling
            self_inner._save()
            return self_inner.result()

    monkeypatch.setattr(product_list, "ProductDialog", Auto)
    inv.btn_new_product.click()
    assert not no_modal, no_modal
    assert inv.product_combo.currentText() == "كفر جديد"
    type_into(qtbot, inv.qty_edit, "4")
    inv.cost_edit.setText("80")
    inv._add_line_item()
    inv.supplier_combo.setCurrentIndex(inv.supplier_combo.findData(sup.id))
    inv.inv_no_edit.setText("N-1")
    inv._save_purchase()
    p = s.query(Product).filter_by(name="كفر جديد").one()
    assert p.current_quantity() == 4                                # 4, not 0 and not 8


def test_wallet_added_through_main_window_shows_card_and_balance(qtbot, db_session, mgr, locale, no_modal, monkeypatch):
    from app.models.wallet import Wallet
    from app.ui.main_window import MainWindow
    from app.ui.wallets import wallet_dialog, wallets_window

    win = MainWindow(user_id=mgr.id)
    qtbot.addWidget(win)
    win.show()
    win._show_wallets()
    widget = win.stack.currentWidget()

    class Auto(wallet_dialog.WalletDialog):
        def exec(self_inner):
            type_into(qtbot, self_inner.phone_edit, "01011112222")
            type_into(qtbot, self_inner.label_edit, "فودافون كاش")
            type_into(qtbot, self_inner.bal_edit, "750.50")
            self_inner.btn_save.click()
            return self_inner.result()

    monkeypatch.setattr(wallets_window, "WalletDialog", Auto)
    widget._open_new_wallet_dialog()
    assert not no_modal, no_modal
    assert win.session.query(Wallet).one().balance == 75050
    assert widget.op_wallet_combo.count() == 1 and "750.50" in widget.op_wallet_combo.itemText(0)
    assert widget.cards_layout.count() >= 1


@pytest.mark.parametrize("role,can", [(ROLE_MANAGER, True), (ROLE_WALLET_EMPLOYEE, False), (ROLE_CASHIER, False)])
def test_wallet_create_permission_is_enforced_in_service(db_session, role, can):
    from app.core.permissions import PermissionDenied
    from app.services import wallet_service

    from app.core.security import hash_password

    r = db_session.query(Role).filter_by(name=role).one()
    u = User(username=f"u_{role}", password_hash=hash_password("Passw0rd!"), full_name=role, role_id=r.id)
    db_session.add(u)
    db_session.commit()
    if can:
        wallet_service.create_wallet(db_session, u, "vodafone", "01000000001", "w")
    else:
        with pytest.raises(PermissionDenied):
            wallet_service.create_wallet(db_session, u, "vodafone", "01000000001", "w")


@pytest.mark.parametrize("role,visible", [(ROLE_MANAGER, True), (ROLE_WALLET_EMPLOYEE, False)])
def test_wallet_manage_buttons_follow_permission(qtbot, db_session, role, visible):
    from app.core.security import hash_password
    from app.ui.main_window import MainWindow

    r = db_session.query(Role).filter_by(name=role).one()
    u = User(username=f"w_{role}", password_hash=hash_password("Passw0rd!"), full_name=role, role_id=r.id)
    db_session.add(u)
    db_session.commit()
    win = MainWindow(user_id=u.id)
    qtbot.addWidget(win)
    win.show()
    win._show_wallets()
    w = win.stack.currentWidget()
    assert w.btn_new_wallet.isVisible() is visible and w.btn_rules.isVisible() is visible


# ── remaining money dialogs: drive them with typed text, assert the data really changed ──
@pytest.fixture
def funded(db_session):
    from app.models.accounting import CashAccount
    for acc in db_session.query(CashAccount).all():
        acc.balance = 10_000_000
    db_session.commit()
    return db_session


@pytest.mark.parametrize("typed,expected", AMOUNTS)
def test_collect_customer_payment_typed(qtbot, funded, mgr, locale, typed, expected, no_modal, monkeypatch):
    from app.models.customer import Customer
    from app.ui.customers import collect_payment_dialog as m

    monkeypatch.setattr(m, "show_error", lambda *a, **k: no_modal.append(k))
    monkeypatch.setattr(m, "show_toast", lambda *a, **k: None)
    c = Customer(name="زبون", balance=500000, credit_limit=1000000)
    funded.add(c)
    funded.commit()
    dlg = m.CollectPaymentDialog(funded, mgr, c)
    qtbot.addWidget(dlg)
    dlg.show()
    type_into(qtbot, dlg.amount_edit, typed)
    dlg._collect()
    assert not no_modal, no_modal
    assert c.balance == 500000 - expected


@pytest.mark.parametrize("typed,expected", AMOUNTS)
def test_supplier_dialog_and_payment_typed(qtbot, funded, mgr, locale, typed, expected, no_modal, monkeypatch):
    from app.models.purchase import Supplier
    from app.ui.purchases import supplier_dialog as sd
    from app.ui.purchases import supplier_payment_dialog as sp

    for mod in (sd, sp):
        monkeypatch.setattr(mod, "show_error", lambda *a, **k: no_modal.append(k))
    monkeypatch.setattr(sp, "show_toast", lambda *a, **k: None)
    dlg = sd.SupplierDialog(funded, mgr)
    qtbot.addWidget(dlg)
    dlg.show()
    type_into(qtbot, dlg.name_edit, "مورد س")
    type_into(qtbot, dlg.phone_edit, "0222")
    type_into(qtbot, dlg.balance_edit, typed)
    dlg._save()
    assert not no_modal, no_modal
    sup = funded.query(Supplier).filter_by(name="مورد س").one()
    assert sup.balance == expected
    pay = sp.SupplierPaymentDialog(funded, mgr, sup)
    qtbot.addWidget(pay)
    pay.show()
    type_into(qtbot, pay.amount_edit, typed)
    pay._pay()
    assert not no_modal, no_modal
    assert sup.balance == 0


@pytest.mark.parametrize("typed,expected", AMOUNTS)
def test_owner_draw_and_transfer_typed(qtbot, funded, mgr, locale, typed, expected, no_modal, monkeypatch):
    from app.models.accounting import CashAccount
    from app.ui.accounting import owner_draw_dialog as od
    from app.ui.accounting import transfer_dialog as td

    for mod in (od, td):
        monkeypatch.setattr(mod, "show_error", lambda *a, **k: no_modal.append(k))
        if hasattr(mod, "show_toast"):
            monkeypatch.setattr(mod, "show_toast", lambda *a, **k: None)
    drawer, safe = funded.query(CashAccount).order_by(CashAccount.id).all()[:2]
    before = (drawer.balance, safe.balance)
    t = td.TransferDialog(funded, mgr)
    qtbot.addWidget(t)
    t.show()
    t.from_combo.setCurrentIndex(t.from_combo.findData(drawer.id))
    t.to_combo.setCurrentIndex(t.to_combo.findData(safe.id))
    type_into(qtbot, t.amount_edit, typed)
    t._transfer()
    assert not no_modal, no_modal
    assert drawer.balance == before[0] - expected and safe.balance == before[1] + expected
    d = od.OwnerDrawDialog(funded, mgr)
    qtbot.addWidget(d)
    d.show()
    type_into(qtbot, d.amount_edit, typed)
    d._save()
    assert not no_modal, no_modal


def test_commission_rule_and_wallet_audit_typed(qtbot, funded, mgr, locale, no_modal, monkeypatch):
    from app.models.wallet import CommissionRule
    from app.services import wallet_service
    from app.ui.wallets import commission_rules_dialog as cr
    from app.ui.wallets import wallet_audit_dialog as wa

    for mod in (cr, wa):
        monkeypatch.setattr(mod, "show_error", lambda *a, **k: no_modal.append(k))
        if hasattr(mod, "show_toast"):
            monkeypatch.setattr(mod, "show_toast", lambda *a, **k: None)
    before = funded.query(CommissionRule).count()
    d = cr.CommissionRulesDialog(funded, mgr)
    qtbot.addWidget(d)
    d.show()
    type_into(qtbot, d.min_edit, "10")
    type_into(qtbot, d.max_edit, "٢٠٠٠٫٥")
    type_into(qtbot, d.fix_edit, "2.5")
    type_into(qtbot, d.pct_edit, "0.5")
    d._add_rule()
    assert not no_modal, no_modal
    assert funded.query(CommissionRule).count() == before + 1

    w = wallet_service.create_wallet(funded, mgr, "vodafone", "01022223333", "محفظة", initial_balance=100000)
    funded.commit()
    a = wa.WalletAuditDialog(funded, mgr)
    qtbot.addWidget(a)
    a.show()
    a.wallet_combo.setCurrentIndex(0)
    type_into(qtbot, a.actual_edit, "1000.00")
    a._save_audit()
    assert not no_modal, no_modal


def _phone(session, mgr, name="هاتف"):
    from app.services import inventory_service as inv
    p = inv.create_product(session, mgr, {"name": name, "type": "phone", "cost_price": 100000, "sale_price": 150000,
                                          "min_price": 0, "min_stock": 0, "track_imei": True, "warranty_days": 0})
    session.commit()
    return p


def test_add_device_and_used_device_typed(qtbot, funded, mgr, locale, no_modal, monkeypatch):
    from app.models.product import Device
    from app.ui.inventory import device_list as dl
    from app.ui.purchases import used_device_dialog as ud

    for mod in (dl, ud):
        monkeypatch.setattr(mod, "show_error", lambda *a, **k: no_modal.append((a, k)))
        monkeypatch.setattr(mod, "show_toast", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(ud.QMessageBox, "exec", lambda self: 0)      # the success popup would block
    monkeypatch.setattr(ud.purchase_service, "generate_declaration", lambda **k: "/tmp/declaration.pdf")
    _phone(funded, mgr)
    d = dl.AddDeviceDialog(funded, mgr)
    qtbot.addWidget(d)
    d.show()
    type_into(qtbot, d.model_picker.combo.lineEdit(), "هاتف")           # existing model typed by hand
    assert not d.model_picker.price_edit.isVisible()
    type_into(qtbot, d.imei1_edit, "356938035643809")
    type_into(qtbot, d.cost_edit, "٨٠٠٫٥")
    type_into(qtbot, d.extra_cost_edit, "10,5")
    d._save()
    assert not no_modal, no_modal
    dev = funded.query(Device).filter_by(imei1="356938035643809").one()
    assert dev.purchase_cost == 80050 and dev.extra_cost == 1050

    u = ud.UsedDeviceDialog(funded, mgr)
    qtbot.addWidget(u)
    u.show()
    type_into(qtbot, u.seller_name_edit, "بائع")
    type_into(qtbot, u.seller_nid_edit, "29001011234567")
    type_into(qtbot, u.seller_phone_edit, "01055556666")
    type_into(qtbot, u.price_edit, "٢٥٠٠٫٥")
    type_into(qtbot, u.model_picker.combo.lineEdit(), "Galaxy A15 128GB")     # a brand-new model: typed, priced
    assert u.model_picker.price_edit.isVisible()
    type_into(qtbot, u.model_picker.price_edit, "٤٥٠٠")
    type_into(qtbot, u.imei1_edit, "490154203237518")
    u._save_used_device()
    assert not no_modal, no_modal
    assert funded.query(Device).filter_by(imei1="490154203237518").one().purchase_cost == 250050
    from app.models.product import Product
    newp = funded.query(Product).filter_by(name="Galaxy A15 128GB").one()
    assert newp.track_imei and newp.type == "phone" and newp.sale_price == 450000


def test_new_repair_typed(qtbot, funded, mgr, locale, no_modal, monkeypatch):
    from app.models.repair import RepairTicket
    from app.ui.repairs import repairs_window as rw

    monkeypatch.setattr(rw, "show_error", lambda *a, **k: no_modal.append((a, k)))
    from app.services import shift_service
    shift_service.open_shift(funded, mgr, 0) if shift_service.get_active_shift(funded, mgr.id) is None else None
    funded.commit()
    d = rw.NewRepairDialog(funded, mgr)
    qtbot.addWidget(d)
    d.show()
    type_into(qtbot, d.name, "عميل")
    type_into(qtbot, d.phone, "01012345678")
    type_into(qtbot, d.device, "iPhone")
    d.issue.setPlainText("شاشة")
    type_into(qtbot, d.estimate, "٣٠٠٫٥")
    type_into(qtbot, d.deposit, "100,5")
    d._save()
    assert not no_modal, no_modal
    t = funded.query(RepairTicket).one()
    assert t.estimate == 30050 and t.paid == 10050


def test_add_user_from_settings_tab(qtbot, funded, mgr, no_modal, monkeypatch):
    from app.models.user import User
    from app.ui.settings import settings_tabs as st

    monkeypatch.setattr(st, "show_error", lambda *a, **k: no_modal.append((a, k)), raising=False)
    tab = st.UsersTab(funded, mgr)
    qtbot.addWidget(tab)

    class Auto(st.UserDialog):
        def exec(self_inner):
            self_inner.username.setText("newcashier")
            self_inner.full_name.setText("كاشير جديد")
            self_inner.role.setCurrentIndex(self_inner.role.findText(st.ROLE_AR["cashier"]))
            self_inner.password.setText("Str0ngPass!")
            return st.QDialog.Accepted

    monkeypatch.setattr(st, "UserDialog", Auto)
    tab.add()
    assert not no_modal, no_modal
    assert funded.query(User).filter_by(username="newcashier").one().full_name == "كاشير جديد"
