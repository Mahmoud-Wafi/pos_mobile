"""Repairs screen: intake, status flow, payments, delivery, customer message, receipt."""
from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QInputDialog,
                               QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from app.core import clock
from app.core.money import format_money, parse_egp_input
from app.core.permissions import PERM_COST_VIEW
from app.i18n import ar
from app.services import repair_service, settings_service
from app.ui.components import DataTable, PageHeader, SearchField, confirm, show_error, show_toast
from app.ui.components.basic import attach_imei_check
from app.ui.design.style import variant

STATUS_AR = {
    "received": ar.REPAIR_ST_RECEIVED, "diagnosing": ar.REPAIR_ST_DIAGNOSING,
    "waiting_parts": ar.REPAIR_ST_WAITING_PARTS, "ready": ar.REPAIR_ST_READY,
    "delivered": ar.REPAIR_ST_DELIVERED, "cancelled": ar.REPAIR_ST_CANCELLED,
}


def _money(text: str) -> int:
    return parse_egp_input(text.strip() or "0")


class NewRepairDialog(QDialog):
    def __init__(self, session, user, parent=None):
        super().__init__(parent)
        self.session, self.user = session, user
        self.ticket = None
        self.setWindowTitle(ar.REPAIR_NEW)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumWidth(460)
        form = QFormLayout(self)
        self.name, self.phone = QLineEdit(), QLineEdit()
        self.device, self.imei = QLineEdit(), QLineEdit()
        attach_imei_check(self.imei, required=False)
        self.issue = QPlainTextEdit()
        self.issue.setFixedHeight(70)
        self.estimate, self.deposit = QLineEdit("0"), QLineEdit("0")
        for label, w in ((ar.REPAIR_F_CUSTOMER, self.name), (ar.REPAIR_F_PHONE, self.phone),
                         (ar.REPAIR_F_DEVICE, self.device), (ar.REPAIR_F_IMEI, self.imei),
                         (ar.REPAIR_F_ISSUE, self.issue), (ar.REPAIR_F_ESTIMATE, self.estimate),
                         (ar.REPAIR_F_DEPOSIT, self.deposit)):
            form.addRow(label, w)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def _save(self) -> None:
        try:
            self.ticket = repair_service.create_ticket(
                self.session, self.user,
                {"customer_name": self.name.text(), "customer_phone": self.phone.text(),
                 "device_desc": self.device.text(), "imei": self.imei.text(),
                 "issue": self.issue.toPlainText(), "estimate": _money(self.estimate.text())},
                deposit=_money(self.deposit.text()))
            self.session.commit()
        except Exception as exc:  # noqa: BLE001 - shown as an Arabic message
            self.session.rollback()
            show_error(self, exc)
            return
        self.accept()


class RepairsWidget(QWidget):
    def __init__(self, session, user, parent=None):
        super().__init__(parent)
        self.session, self.user = session, user
        self._tickets = []
        self.setLayoutDirection(Qt.RightToLeft)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.addWidget(PageHeader(ar.REPAIR_TITLE))

        bar = QHBoxLayout()
        self.search = SearchField(ar.SEARCH)
        self.search.textChanged.connect(self.reload)
        bar.addWidget(self.search, 1)
        self.filter = QComboBox()
        self.filter.addItem(ar.REPAIR_ST_ACTIVE, "active")
        self.filter.addItem("—", None)
        for code, text in STATUS_AR.items():
            self.filter.addItem(text, code)
        self.filter.currentIndexChanged.connect(self.reload)
        bar.addWidget(self.filter)
        self.btn_new = self._btn(ar.REPAIR_NEW, self._new, "primary", bar)
        root.addLayout(bar)

        self.table = DataTable([ar.REPAIR_COL_NO, ar.REPAIR_COL_CUSTOMER, ar.REPAIR_COL_DEVICE,
                                ar.REPAIR_COL_STATUS, ar.REPAIR_COL_PRICE, ar.REPAIR_COL_PAID,
                                ar.REPAIR_COL_DATE], ar.REPAIR_TITLE)
        root.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.btn_status = self._btn(ar.REPAIR_BTN_STATUS, self._change_status, None, actions)
        self.btn_price = self._btn(ar.REPAIR_BTN_PRICE, self._set_price, None, actions)
        self.btn_pay = self._btn(ar.REPAIR_BTN_PAY, self._pay, None, actions)
        self.btn_deliver = self._btn(ar.REPAIR_BTN_DELIVER, self._deliver, "success", actions)
        self.btn_message = self._btn(ar.REPAIR_BTN_MESSAGE, self._message, None, actions)
        self.btn_print = self._btn(ar.REPAIR_BTN_PRINT, self._print, None, actions)
        self.btn_cancel = self._btn(ar.REPAIR_BTN_CANCEL, self._cancel, "danger", actions)
        actions.addStretch()
        root.addLayout(actions)
        self.reload()

    @staticmethod
    def _btn(text, slot, kind, layout) -> QPushButton:
        b = QPushButton(text)
        b.setMinimumHeight(40)
        if kind:
            variant(b, kind)
        b.clicked.connect(slot)
        layout.addWidget(b)
        return b

    # ── data ──
    def reload(self, *_args) -> None:
        self.session.expire_all()
        self._tickets = repair_service.list_tickets(self.session, self.user, self.filter.currentData(),
                                                    self.search.text())
        rows = [[t.ticket_no, t.customer_name, t.device_desc, STATUS_AR[t.status], format_money(t.final_price),
                 format_money(t.paid), clock.fmt_local(t.received_at)] for t in self._tickets]
        self.table.set_rows(rows, keys=[t.id for t in self._tickets])

    def _selected(self):
        key = self.table.selected_key()
        return next((t for t in self._tickets if t.id == key), None)

    def _run(self, fn, ok_text: str = ar.REPAIR_DONE) -> bool:
        try:
            fn()
            self.session.commit()
        except Exception as exc:  # noqa: BLE001 - shown as an Arabic message
            self.session.rollback()
            show_error(self, exc)
            return False
        show_toast(self, ok_text)
        self.reload()
        return True

    # ── actions ──
    def _new(self) -> None:
        dlg = NewRepairDialog(self.session, self.user, self)
        if dlg.exec() == QDialog.Accepted:
            show_toast(self, ar.REPAIR_CREATED)
            self.reload()
            if confirm(self, ar.REPAIR_BTN_PRINT, ar.REPAIR_BTN_PRINT + "؟"):
                self._print(dlg.ticket)

    def _change_status(self) -> None:
        t = self._selected()
        if t is None:
            return
        options = ["received", "diagnosing", "waiting_parts", "ready"]
        choice, ok = QInputDialog.getItem(self, ar.REPAIR_BTN_STATUS, ar.REPAIR_COL_STATUS,
                                          [STATUS_AR[o] for o in options], 0, False)
        if ok:
            code = options[[STATUS_AR[o] for o in options].index(choice)]
            self._run(lambda: repair_service.set_status(self.session, self.user, t.id, code))

    def _set_price(self) -> None:
        t = self._selected()
        if t is None:
            return
        price, ok = QInputDialog.getText(self, ar.REPAIR_BTN_PRICE, ar.REPAIR_F_FINAL, text=str(t.final_price / 100))
        if not ok:
            return
        parts = None
        if PERM_COST_VIEW in self.user.permission_codes():
            text, ok = QInputDialog.getText(self, ar.REPAIR_BTN_PRICE, ar.REPAIR_F_PARTS, text=str(t.parts_cost / 100))
            if not ok:
                return
            parts = text
        try:
            final, cost = _money(price), (_money(parts) if parts is not None else None)
        except ValueError:
            show_error(self, message=ar.REPAIR_BAD_AMOUNT)
            return
        self._run(lambda: repair_service.set_pricing(self.session, self.user, t.id, final, cost))

    def _pay(self) -> None:
        t = self._selected()
        if t is None:
            return
        text, ok = QInputDialog.getText(self, ar.REPAIR_BTN_PAY, ar.REPAIR_F_AMOUNT, text=str(t.balance / 100))
        if not ok:
            return
        try:
            amount = _money(text)
        except ValueError:
            show_error(self, message=ar.REPAIR_BAD_AMOUNT)
            return
        self._run(lambda: repair_service.add_payment(self.session, self.user, t.id, amount))

    def _deliver(self) -> None:
        t = self._selected()
        if t is not None:
            self._run(lambda: repair_service.deliver(self.session, self.user, t.id))

    def _cancel(self) -> None:
        t = self._selected()
        if t is None:
            return
        reason, ok = QInputDialog.getText(self, ar.REPAIR_BTN_CANCEL, ar.REPAIR_REASON_REQUIRED)
        if ok:
            self._run(lambda: repair_service.cancel(self.session, self.user, t.id, reason))

    def _message(self) -> None:
        t = self._selected()
        if t is None:
            return
        shop = settings_service.get(self.session, "shop_name")
        text = repair_service.ready_message(t, shop, format_money(t.balance))
        QGuiApplication.clipboard().setText(text)
        link = repair_service.whatsapp_link(t.customer_phone, text)
        if link:
            QDesktopServices.openUrl(QUrl(link))
            show_toast(self, ar.REPAIR_MSG_COPIED)
        else:
            show_toast(self, ar.REPAIR_NO_PHONE)

    def _print(self, ticket=None) -> None:
        from app.printing.repair_slip import generate_repair_slip_pdf

        t = ticket if ticket is not None and not isinstance(ticket, bool) else self._selected()
        if t is None:
            return
        try:
            cfg = settings_service.get_all(self.session)
            out = Path(tempfile.gettempdir()) / f"{t.ticket_no}.pdf"
            generate_repair_slip_pdf(t, out, cfg.get("shop_name", ""), cfg.get("shop_phone", ""))
        except Exception as exc:  # noqa: BLE001
            show_error(self, exc)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(out)))
