"""Supplier statement, commission editing, hardware settings, repair delivery and label output (UI level)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from app.models.accounting import CashAccount
from app.models.user import Role, User


@pytest.fixture
def mgr(db_session):
    for acc in db_session.query(CashAccount).all():
        acc.balance = 100_000_000
    db_session.commit()
    return db_session.query(User).join(Role).filter(Role.name == "manager").first()


@pytest.fixture(autouse=True)
def no_modal(monkeypatch):
    errors = []
    import app.ui.components as comp
    monkeypatch.setattr(comp, "show_error", lambda *a, **k: errors.append((a, k)))
    monkeypatch.setattr("app.ui.components.confirm", lambda *a, **k: True)
    for mod in ("app.ui.wallets.commission_rules_dialog", "app.ui.repairs.repairs_window"):
        m = __import__(mod, fromlist=["x"])          # these import confirm/show_error by name
        monkeypatch.setattr(m, "confirm", lambda *a, **k: True)
        monkeypatch.setattr(m, "show_error", lambda *a, **k: errors.append((a, k)))
    return errors


def test_supplier_ledger_dialog_lists_every_installment_and_filters_by_invoice(qtbot, db_session, mgr):
    from app.services import inventory_service as inv, purchase_service as ps
    from app.ui.purchases.supplier_ledger_dialog import SupplierLedgerDialog
    from app.ui.purchases.supplier_payment_dialog import SupplierPaymentDialog

    s = db_session
    p = inv.create_product(s, mgr, {"name": "Cable", "type": "accessory", "cost_price": 1000, "sale_price": 2000,
                                    "min_price": 0, "min_stock": 0, "track_imei": False, "warranty_days": 0})
    sup = ps.create_supplier(s, mgr, "المورد")
    s.commit()
    one = ps.create_purchase(s, mgr, sup.id, "A-1", [{"product_id": p.id, "quantity": 1000, "unit_cost": 1000}], 500_000)
    two = ps.create_purchase(s, mgr, sup.id, "A-2", [{"product_id": p.id, "quantity": 100, "unit_cost": 1000}], 0)
    s.commit()

    pay = SupplierPaymentDialog(s, mgr, sup)
    qtbot.addWidget(pay)
    assert pay.invoice_combo.count() == 3                       # on account + 2 open invoices
    assert pay.invoice_combo.currentData() == one.id            # oldest first
    assert pay.amount_edit.text() == "5000.00"                  # remaining pre-filled
    pay.amount_edit.setText("2000")
    pay._pay()
    assert one.balance == 300_000 and one.paid == 700_000

    dlg = SupplierLedgerDialog(s, mgr, sup)
    qtbot.addWidget(dlg)
    assert dlg.invoices_table.rowCount() == 2
    assert dlg.table.rowCount() == 4                            # A-1, paid at invoice, A-2, payment on A-1
    dlg.invoices_table.setCurrentCell(0, 0)
    dlg._on_invoice_clicked()
    assert dlg.table.rowCount() == 3                            # invoice, paid at invoice, payment
    dlg._show_all()
    assert dlg.table.rowCount() == 4
    assert "المتبقي للمورد" in dlg.lbl_totals.text()


def test_commission_dialog_edit_and_delete(qtbot, db_session, mgr, no_modal):
    from app.models.wallet import CommissionRule
    from app.services import wallet_service as ws
    from app.ui.wallets.commission_rules_dialog import CommissionRulesDialog

    s = db_session
    rule = ws.create_commission_rule(s, mgr, network="vodafone", op_type="cash_in", min_amount=100, max_amount=100000,
                                     fixed_fee=500)
    s.commit()
    dlg = CommissionRulesDialog(s, mgr)
    qtbot.addWidget(dlg)
    dlg.show()
    row = [r.id for r in dlg._rules].index(rule.id)
    assert dlg.table.item(row, 2).text().startswith("إيداع")        # Arabic label, not 'cash_in'
    dlg.table.setCurrentCell(row, 0)
    dlg._start_edit()
    assert dlg.btn_add.text() == "حفظ التعديل"
    dlg.fix_edit.setText("7.5")
    dlg.pct_edit.setText("0.5")
    dlg._save_rule()
    assert not no_modal, no_modal
    s.refresh(rule)
    assert rule.fixed_fee == 750 and rule.percent_bp == 50 and dlg._editing_id is None
    dlg.table.setCurrentCell(row, 0)
    dlg._delete_rule()
    assert s.query(CommissionRule).filter_by(id=rule.id, is_active=True).count() == 0


def test_hardware_tab_saves_and_settings_are_used(qtbot, db_session, mgr, monkeypatch):
    from app.services import settings_service
    from app.ui.settings.settings_window import SettingsWidget
    from app.ui import hardware

    monkeypatch.setattr(hardware, "list_printers", lambda: ["Receipt-80", "Label-Zebra"])
    monkeypatch.setattr("app.ui.settings.hardware_tab.show_toast", lambda *a, **k: None)
    w = SettingsWidget(db_session, mgr)
    qtbot.addWidget(w)
    tab = w.hardware_tab
    assert tab is not None and w.tabs.indexOf(tab) >= 0
    tab.receipt_printer.setCurrentIndex(tab.receipt_printer.findData("Receipt-80"))
    tab.receipt_direct.setChecked(True)
    tab.receipt_width.setCurrentIndex(tab.receipt_width.findData("58"))
    tab.label_printer.setCurrentIndex(tab.label_printer.findData("Label-Zebra"))
    tab.label_w.setText("40")
    tab.label_h.setText("25")
    tab.save()
    cfg = settings_service.get_all(db_session)
    assert (cfg["receipt_printer"], cfg["receipt_direct"], cfg["receipt_width_mm"]) == ("Receipt-80", "1", "58")
    assert (cfg["label_printer"], cfg["label_width_mm"], cfg["label_height_mm"]) == ("Label-Zebra", "40", "25")
    tab.scanner_test.setText("6221031234567")
    tab._scanner_read()
    assert "6221031234567" in tab.scanner_result.text() and "13" in tab.scanner_result.text()


def test_labels_use_configured_size_and_direct_printer(db_session, mgr, monkeypatch, qtbot):
    from app.printing.labels import LabelSpec
    from app.services import settings_service
    from app.ui import hardware

    settings_service.update(db_session, mgr, {"label_printer": "Label-Zebra", "label_direct": "1",
                                              "label_width_mm": "40", "label_height_mm": "25"})
    db_session.commit()
    sent = {}
    monkeypatch.setattr(hardware, "list_printers", lambda: ["Label-Zebra"])
    monkeypatch.setattr(hardware, "print_pdf", lambda path, printer, w, h: sent.update(w=w, h=h) or 1)
    n = hardware.print_labels([LabelSpec("Cable", "123456", "10.00")], settings_service.get_all(db_session))
    assert n == 1 and sent == {"w": 40.0, "h": 25.0}


def test_repair_delivery_from_received_collects_balance_in_one_step(qtbot, db_session, mgr, no_modal, monkeypatch):
    from app.services import repair_service, shift_service
    from app.ui.repairs import repairs_window as rw

    s = db_session
    shift_service.open_shift(s, mgr, 0)
    t = repair_service.create_ticket(s, mgr, {"customer_name": "محمد", "customer_phone": "010", "device_desc": "iPhone 12",
                                              "imei": "", "issue": "شاشة", "estimate": 70000}, deposit=20000)
    repair_service.set_pricing(s, mgr, t.id, 70000, None)
    s.commit()
    monkeypatch.setattr(rw, "show_toast", lambda *a, **k: None)
    w = rw.RepairsWidget(s, mgr)
    qtbot.addWidget(w)
    w.show()
    w.table.setCurrentCell(0, 0)
    assert t.status == "received" and t.balance == 50000
    w._deliver()
    s.refresh(t)
    assert t.status == "delivered" and t.balance == 0 and t.ready_at is not None
