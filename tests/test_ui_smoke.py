"""Every screen and dialog can be constructed and shown (offscreen) without errors."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from app.core.permissions import ROLE_CASHIER, ROLE_MANAGER, ROLE_WALLET_EMPLOYEE
from app.models.customer import Customer
from app.models.user import Role, User

SCREENS = ["dashboard", "pos", "invoices", "inventory", "returns", "repairs", "purchases", "wallets",
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


def test_import_wizard_flow(qtbot, db_session, manager, tmp_path):
    from app.models.product import Product
    from app.services import import_export_service as ie
    from app.ui.inventory.import_wizard import ImportWizard

    path = ie.write_template("products", tmp_path / "t.xlsx")
    w = ImportWizard(db_session, manager)
    qtbot.addWidget(w)
    w.load_file(path)
    assert w.steps.currentIndex() == 1 and w.table.rowCount() == 1 and w.btn_confirm.isEnabled()
    assert "✓" in w.table.item(0, 2).text()
    w.confirm()
    assert w.imported == 1 and db_session.query(Product).count() == 1


def test_import_wizard_shows_row_errors(qtbot, db_session, manager, tmp_path):
    from openpyxl import Workbook
    from app.ui.inventory.import_wizard import ImportWizard

    wb = Workbook(); ws = wb.active
    ws.append(["الاسم", "النوع"]); ws.append(["", "اكسسوار"]); ws.append(["جيد", "اكسسوار"])
    wb.save(tmp_path / "e.xlsx")
    w = ImportWizard(db_session, manager)
    qtbot.addWidget(w)
    w.load_file(tmp_path / "e.xlsx")
    assert "✗" in w.table.item(0, 2).text() and "✓" in w.table.item(1, 2).text()
    assert "1" in w.btn_confirm.text()


def _dash_sale(db_session, manager):
    from app.core.money import egp_to_piasters as E
    from app.services import inventory_service, sales_service, shift_service

    p = inventory_service.create_product(db_session, manager, {
        "name": "Cable", "type": "accessory", "cost_price": E("50"), "sale_price": E("100"),
        "min_price": E("80"), "min_stock": 8})
    inventory_service.adjust_stock(db_session, manager, p, 5, "init")
    shift_service.open_shift(db_session, manager, opening_cash=0)
    db_session.commit()
    sale = sales_service.start_sale(db_session, manager)
    sales_service.add_line(db_session, manager, sale, p, quantity=2)
    sales_service.post_sale(db_session, manager, sale, [{"method": "cash", "amount": sale.total}])
    db_session.commit()


def test_dashboard_with_data_shows_chart_top5_and_reorder(qtbot, db_session, manager):
    from app.ui.dashboard.dashboard_widget import DashboardWidget

    _dash_sale(db_session, manager)
    w = DashboardWidget(db_session, manager)
    qtbot.addWidget(w)
    w.show()
    assert w.stack.currentIndex() == 1
    assert w.chart.bar_values[-1] == 200.0 and len(w.chart.bar_values) == 7
    assert w.top_table.rowCount() == 1 and not w.chart_empty.isVisible() and w.chart.isVisible()
    assert w.kpi_profit.isVisible() and "200" in w.kpi_sales.value_lbl.text()
    assert w.low_table.rowCount() == 1 and w.btn_reorder.isVisible()      # 3 left, min 8
    fired = []
    w.open_purchases_requested.connect(lambda: fired.append(1))
    w.btn_reorder.click()
    assert fired == [1]


def test_dashboard_empty_states_and_profit_hidden_for_cashier(qtbot, db_session):
    from app.core.permissions import ROLE_CASHIER, ROLE_WALLET_EMPLOYEE
    from app.models.user import Role, User
    from app.ui.dashboard.dashboard_widget import DashboardWidget

    cashier = db_session.query(User).join(Role).filter(Role.name == ROLE_CASHIER).first()
    if cashier is None:
        from app.core.security import hash_password
        r = db_session.query(Role).filter_by(name=ROLE_CASHIER).first()
        cashier = User(username="dc", password_hash=hash_password("Passw0rd!"), full_name="dc", role_id=r.id)
        db_session.add(cashier); db_session.commit()
    w = DashboardWidget(db_session, cashier)
    qtbot.addWidget(w)
    w.show()
    assert w.chart_empty.isVisible() and not w.chart.isVisible()
    assert not w.kpi_profit.isVisible()                                    # no profit permission
    wallet_user = db_session.query(User).join(Role).filter(Role.name == ROLE_WALLET_EMPLOYEE).first()
    if wallet_user is None:
        from app.core.security import hash_password
        r = db_session.query(Role).filter_by(name=ROLE_WALLET_EMPLOYEE).first()
        wallet_user = User(username="dw", password_hash=hash_password("Passw0rd!"), full_name="dw", role_id=r.id)
        db_session.add(wallet_user); db_session.commit()
    w2 = DashboardWidget(db_session, wallet_user)
    qtbot.addWidget(w2)
    w2.show()
    assert not w2.kpi_sales.isVisible() and not w2.chart_card.isVisible() and w2.wallet_card.isVisible()


def test_tables_follow_shared_conventions(qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QTableWidget
    from app.ui.components.data_table import DataTable, SortItem

    from PySide6.QtWidgets import QApplication
    from app.ui.design.table_defaults import TableDefaults

    flt = TableDefaults(QApplication.instance())
    QApplication.instance().installEventFilter(flt)
    t = DataTable(["a", "b"], "empty")
    qtbot.addWidget(t)
    t.set_rows([["x", "1,500.00 ج.م"], ["y", "20.00 ج.م"]], keys=[10, 20])
    t.show()
    assert t.verticalHeader().minimumSectionSize() >= 40
    assert t.isSortingEnabled()
    t.sortItems(1, Qt.AscendingOrder)
    assert t.item(0, 1).text().startswith("20")  # numeric, not text, order
    assert t.selected_key() is None
    plain = QTableWidget(1, 1)
    qtbot.addWidget(plain)
    plain.show()
    assert plain.verticalHeader().minimumSectionSize() >= 40
    assert isinstance(t.item(0, 0), SortItem)
    QApplication.instance().removeEventFilter(flt)


def test_imei_field_shows_luhn_state(qtbot):
    from PySide6.QtWidgets import QLineEdit
    from app.ui.components.basic import attach_imei_check

    e = QLineEdit()
    qtbot.addWidget(e)
    attach_imei_check(e)
    e.setText("123")
    e.editingFinished.emit()
    assert e.property("invalid") == "true"
    e.setText("490154203237518")  # valid Luhn
    e.editingFinished.emit()
    assert e.property("invalid") == "false"


def test_warranty_claims_dialog_lists_and_updates(qtbot, db_session):
    from app.core.money import egp_to_piasters as egp
    from app.core.security import hash_password
    from app.models.user import Role, User
    from app.services import inventory_service, sales_service, shift_service, warranty_service
    from app.ui.pos.warranty_claims_dialog import WarrantyClaimsDialog

    s = db_session
    role = s.query(Role).filter_by(name="manager").first()
    mgr = User(username="wm", password_hash=hash_password("Passw0rd!"), full_name="wm", role_id=role.id)
    s.add(mgr)
    s.commit()
    p = inventory_service.create_product(s, mgr, {
        "name": "Cable", "type": "accessory", "cost_price": egp("10"), "sale_price": egp("50"),
        "min_price": egp("20"), "min_stock": 1, "track_imei": False, "warranty_days": 30})
    inventory_service.adjust_stock(s, mgr, p, 3, "init")
    shift_service.open_shift(s, mgr, opening_cash=0)
    sale = sales_service.start_sale(s, mgr)
    sales_service.add_line(s, mgr, sale, p)
    sales_service.post_sale(s, mgr, sale, [{"method": "cash", "amount": sale.total}])
    warranty_service.open_claim(s, mgr, sale.items[0].id, "dead")
    s.commit()
    dlg = WarrantyClaimsDialog(s, mgr)
    qtbot.addWidget(dlg)
    assert dlg.table.rowCount() == 1


def test_inventory_lists_have_label_buttons(qtbot, db_session):
    from app.core.security import hash_password
    from app.models.user import Role, User
    from app.ui.inventory.device_list import DeviceListWidget
    from app.ui.inventory.product_list import ProductListWidget

    role = db_session.query(Role).filter_by(name="manager").first()
    mgr = User(username="lb", password_hash=hash_password("Passw0rd!"), full_name="lb", role_id=role.id)
    db_session.add(mgr)
    db_session.commit()
    for cls in (ProductListWidget, DeviceListWidget):
        w = cls(db_session, mgr)
        qtbot.addWidget(w)
        assert w.btn_labels.text()


def test_repairs_screen_flow(qtbot, db_session):
    from app.core.money import egp_to_piasters as egp
    from app.core.security import hash_password
    from app.models.user import Role, User
    from app.services import repair_service, shift_service
    from app.ui.repairs.repairs_window import NewRepairDialog, RepairsWidget

    s = db_session
    role = s.query(Role).filter_by(name="cashier").first()
    cashier = User(username="rc", password_hash=hash_password("Passw0rd!"), full_name="rc", role_id=role.id)
    s.add(cashier)
    s.commit()
    shift_service.open_shift(s, cashier, opening_cash=0)
    w = RepairsWidget(s, cashier)
    qtbot.addWidget(w)
    assert w.table.rowCount() == 0
    dlg = NewRepairDialog(s, cashier)
    qtbot.addWidget(dlg)
    dlg.name.setText("Ali")
    dlg.device.setText("Redmi")
    dlg.issue.setPlainText("no power")
    dlg.deposit.setText("50")
    dlg._save()
    assert dlg.ticket is not None and dlg.ticket.paid == egp("50")
    w.reload()
    assert w.table.rowCount() == 1
    w.table.setCurrentCell(0, 0)
    assert w._selected() is not None


def _mgr(session, name="im"):
    from app.core.security import hash_password
    from app.models.user import Role, User
    role = session.query(Role).filter_by(name="manager").first()
    u = User(username=name, password_hash=hash_password("Passw0rd!"), full_name=name, role_id=role.id)
    session.add(u)
    session.commit()
    return u


def test_product_edit_dialog_saves_changes(qtbot, db_session):
    from app.core.money import egp_to_piasters as egp
    from app.services import inventory_service as inv
    from app.ui.inventory.product_list import ProductDialog, ProductListWidget

    s, mgr = db_session, _mgr(db_session)
    p = inv.create_product(s, mgr, {"name": "Cable", "type": "accessory", "cost_price": egp("10"),
                                    "sale_price": egp("50"), "min_price": egp("20"), "min_stock": 1,
                                    "track_imei": False, "warranty_days": 0})
    s.commit()
    dlg = ProductDialog(s, mgr, product=p)
    qtbot.addWidget(dlg)
    assert dlg.name_edit.text() == "Cable" and dlg.sale_edit.text() in ("50", "50.00")
    dlg.name_edit.setText("Cable 2m")
    dlg.sale_edit.setText("65")
    dlg._save()
    assert p.name == "Cable 2m" and p.sale_price == egp("65")
    w = ProductListWidget(s, mgr)
    qtbot.addWidget(w)
    assert w.btn_edit.text() and w.btn_delete.text() and w.btn_toggle.text()


def test_cashier_does_not_see_cost_in_product_dialog(qtbot, db_session):
    from app.core.security import hash_password
    from app.models.user import Role, User
    from app.ui.inventory.product_list import ProductDialog

    s = db_session
    role = s.query(Role).filter_by(name="cashier").first()
    cashier = User(username="cc", password_hash=hash_password("Passw0rd!"), full_name="cc", role_id=role.id)
    s.add(cashier)
    s.commit()
    dlg = ProductDialog(s, cashier)
    qtbot.addWidget(dlg)
    assert dlg.cost_edit.isHidden()


def test_device_edit_dialog_and_actions(qtbot, db_session, monkeypatch):
    from app.core.money import egp_to_piasters as egp
    from app.services import inventory_service as inv
    from app.ui.inventory import device_list
    from app.ui.inventory.device_list import DeviceEditDialog, DeviceListWidget

    s, mgr = db_session, _mgr(db_session, "dm")
    phone = inv.create_product(s, mgr, {"name": "Phone", "type": "phone", "cost_price": egp("100"),
                                        "sale_price": egp("200"), "min_price": egp("150"), "min_stock": 0,
                                        "track_imei": True, "warranty_days": 365})
    d1, d2 = inv.add_devices(s, mgr, phone, [{"imei1": "490154203237518"}, {"imei1": "352001111222333"}])
    s.commit()
    dlg = DeviceEditDialog(s, mgr, d1)
    qtbot.addWidget(dlg)
    dlg.notes.setText("box included")
    dlg.condition.setCurrentIndex(dlg.condition.findData("used"))
    dlg._save()
    assert d1.notes == "box included" and d1.condition == "used"

    w = DeviceListWidget(s, mgr)
    qtbot.addWidget(w)
    monkeypatch.setattr("app.ui.components.confirm", lambda *a, **k: True)
    w.table.setCurrentCell(0, 0)
    target = w._shown[0]
    w._delete_device()
    assert s.get(type(target), target.id) is None
