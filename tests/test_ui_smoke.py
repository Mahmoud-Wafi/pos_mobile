"""Every screen and dialog can be constructed and shown (offscreen) without errors."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from app.core.permissions import ROLE_CASHIER, ROLE_MANAGER, ROLE_WALLET_EMPLOYEE
from app.models.customer import Customer
from app.models.user import Role, User

SCREENS = ["dashboard", "pos", "invoices", "inventory", "returns", "purchases", "wallets",
           "accounting", "customers", "reports", "settings"]


@pytest.fixture
def manager(db_session):
    return db_session.query(User).join(Role).filter(Role.name == ROLE_MANAGER).first()


@pytest.mark.parametrize("screen", SCREENS)
def test_every_screen_opens(qtbot, manager, screen):
    from app.ui.main_window import MainWindow

    win = MainWindow(user_id=manager.id)
    qtbot.addWidget(win)
    win.show()
    getattr(win, f"_show_{screen}")()
    assert win.stack.currentWidget() is not None


DIALOGS = [
    ("app.ui.accounting.expense_dialog", "ExpenseDialog", "su"),
    ("app.ui.accounting.owner_draw_dialog", "OwnerDrawDialog", "su"),
    ("app.ui.accounting.transfer_dialog", "TransferDialog", "su"),
    ("app.ui.accounting.daily_close_dialog", "DailyCloseDialog", "su"),
    ("app.ui.customers.customer_dialog", "CustomerDialog", "su"),
    ("app.ui.purchases.supplier_dialog", "SupplierDialog", "su"),
    ("app.ui.purchases.purchase_invoice_dialog", "PurchaseInvoiceDialog", "su"),
    ("app.ui.purchases.used_device_dialog", "UsedDeviceDialog", "su"),
    ("app.ui.wallets.wallet_dialog", "WalletDialog", "su"),
    ("app.ui.wallets.commission_rules_dialog", "CommissionRulesDialog", "su"),
    ("app.ui.wallets.wallet_audit_dialog", "WalletAuditDialog", "su"),
]


@pytest.mark.parametrize("module,cls,sig", DIALOGS)
def test_dialogs_construct(qtbot, db_session, manager, module, cls, sig):
    import importlib

    dlg = getattr(importlib.import_module(module), cls)(db_session, manager)
    qtbot.addWidget(dlg)
    dlg.show()


def test_dialogs_needing_arguments(qtbot, db_session, manager):
    from app.ui.customers.collect_payment_dialog import CollectPaymentDialog
    from app.ui.purchases.imei_input_dialog import IMEIInputDialog
    from app.ui.purchases.supplier_payment_dialog import SupplierPaymentDialog
    from app.models.purchase import Supplier
    from app.ui.pos.payment_dialog import PaymentDialog

    cust = db_session.query(Customer).first()
    sup = Supplier(name="مورد")
    db_session.add(sup); db_session.commit()
    for dlg in (CollectPaymentDialog(db_session, manager, cust), SupplierPaymentDialog(db_session, manager, sup),
                IMEIInputDialog("Phone", 2), PaymentDialog(10000, "x")):
        qtbot.addWidget(dlg)
        dlg.show()


def test_login_and_approval_dialogs(qtbot, db_session, manager):
    from app.ui.approval_dialog import ManagerApprovalDialog
    from app.ui.login_dialog import LoginDialog

    for dlg in (LoginDialog(), ManagerApprovalDialog(db_session, manager, "sales.discount", "why")):
        qtbot.addWidget(dlg)
        dlg.show()


def test_typed_confirmation_enables_button_only_for_phrase(qtbot):
    from app.i18n import ar
    from app.ui.components.dialogs import TypedConfirmDialog

    d = TypedConfirmDialog(None, "t", "m", ar.RESTORE_PHRASE, ar.RESTORE_PHRASE)
    qtbot.addWidget(d)
    assert not d.btn_ok.isEnabled()
    d.input.setText("خطأ")
    assert not d.btn_ok.isEnabled()
    d.input.setText(ar.RESTORE_PHRASE)
    assert d.btn_ok.isEnabled()


def test_restore_flow_requires_typed_phrase_and_calls_service(qtbot, db_session, manager, monkeypatch, tmp_path):
    from pathlib import Path
    from app.ui.settings import settings_window as sw

    tab = sw.BackupSecurityTab(db_session, manager)
    qtbot.addWidget(tab)
    calls = []
    monkeypatch.setattr(sw, "confirm_typed", lambda *a, **k: False)
    monkeypatch.setattr(sw.backup_service, "restore", lambda *a, **k: calls.append(a))
    tab._confirm_restore(Path("shop_x.zip"))
    assert calls == []                                   # declined -> nothing happens
    monkeypatch.setattr(sw, "confirm_typed", lambda *a, **k: True)
    monkeypatch.setattr(tab, "_offer_restart", lambda: calls.append("restart"))
    tab._confirm_restore(Path("shop_x.zip"))
    assert calls[-1] == "restart" and len(calls) == 2
