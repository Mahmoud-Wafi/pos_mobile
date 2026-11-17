"""Invoice history: search, details, reprint, return and (manager) void."""
from __future__ import annotations

import datetime

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from app.ui.components import confirm, show_error
from app.core import clock
from app.core.money import format_money
from app.core.permissions import PERM_SALES_RETURN, PERM_SALES_VOID, PermissionDenied
from app.i18n import ar
from app.models.customer import Customer
from app.models.user import User
from app.services import sales_service, settings_service


def _cell(text: str) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setTextAlignment(Qt.AlignCenter)
    return it


class InvoiceHistoryWidget(QWidget):
    def __init__(self, session, user, parent=None):
        super().__init__(parent)
        self.session, self.user = session, user
        self.setLayoutDirection(Qt.RightToLeft)
        self._sales: list = []
        perms = set(user.permission_codes())
        self._can_return = PERM_SALES_RETURN in perms
        self._can_void = PERM_SALES_VOID in perms
        self._build()

    # ── UI ──────────────────────────────────────────────────────────────
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)

        f = QHBoxLayout()
        today = QDate.currentDate()
        self.d_from = QDateEdit(today.addDays(-30)); self.d_to = QDateEdit(today)
        for d in (self.d_from, self.d_to):
            d.setCalendarPopup(True)
            d.setDisplayFormat("yyyy-MM-dd")
        self.search = QLineEdit(); self.search.setPlaceholderText(ar.HISTORY_SEARCH_HINT)
        self.status = QComboBox(); self.status.addItem(ar.HISTORY_ALL, None)
        for k in ("posted", "void"):
            self.status.addItem(ar.SALE_STATUS_LABELS[k], k)
        self.customer = QComboBox(); self.cashier = QComboBox()
        for lab, w in ((ar.HISTORY_FROM, self.d_from), (ar.HISTORY_TO, self.d_to)):
            f.addWidget(QLabel(lab)); f.addWidget(w)
        f.addWidget(self.search, 1)
        f.addWidget(self.status); f.addWidget(self.customer); f.addWidget(self.cashier)
        btn = QPushButton(ar.SEARCH if hasattr(ar, "SEARCH") else "بحث")
        btn.setDefault(True); btn.clicked.connect(self.refresh)
        f.addWidget(btn)
        root.addLayout(f)
        self.search.returnPressed.connect(self.refresh)

        split = QSplitter(Qt.Horizontal)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            ar.HISTORY_COL_NO, ar.HISTORY_COL_DATE, ar.HISTORY_CUSTOMER,
            ar.HISTORY_COL_TOTAL, ar.HISTORY_COL_STATUS])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._show_details)
        split.addWidget(self.table)

        side = QWidget(); sl = QVBoxLayout(side)
        self.details = QTextEdit(); self.details.setReadOnly(True)
        sl.addWidget(self.details)
        row = QHBoxLayout()
        self.b_print = QPushButton(ar.HISTORY_REPRINT); self.b_print.clicked.connect(self._reprint)
        self.b_return = QPushButton(ar.HISTORY_RETURN); self.b_return.clicked.connect(self._return)
        self.b_void = QPushButton(ar.HISTORY_VOID); self.b_void.clicked.connect(self._void)
        self.b_return.setVisible(self._can_return)
        self.b_void.setVisible(self._can_void)
        for b in (self.b_print, self.b_return, self.b_void):
            row.addWidget(b)
        sl.addLayout(row)
        split.addWidget(side)
        split.setStretchFactor(0, 3); split.setStretchFactor(1, 2)
        root.addWidget(split, 1)
        self.empty = QLabel(ar.HISTORY_NO_RESULTS); self.empty.setAlignment(Qt.AlignCenter)
        root.addWidget(self.empty)
        self._load_filters()
        self._set_buttons(None)

    def _load_filters(self) -> None:
        self.customer.clear(); self.customer.addItem(f"{ar.HISTORY_CUSTOMER}: {ar.HISTORY_ALL}", None)
        for c in self.session.query(Customer).order_by(Customer.name).all():
            self.customer.addItem(c.name, c.id)
        self.cashier.clear(); self.cashier.addItem(f"{ar.HISTORY_CASHIER}: {ar.HISTORY_ALL}", None)
        if self.user.role.name == "manager":
            for u in self.session.query(User).order_by(User.full_name).all():
                self.cashier.addItem(u.full_name or u.username, u.id)
        else:
            self.cashier.setVisible(False)

    # ── data ────────────────────────────────────────────────────────────
    def refresh(self) -> None:
        def d(w):
            q = w.date(); return datetime.date(q.year(), q.month(), q.day())
        self._sales = sales_service.search_sales(
            self.session, self.user, d(self.d_from), d(self.d_to),
            customer_id=self.customer.currentData(), cashier_id=self.cashier.currentData(),
            status=self.status.currentData(), text=self.search.text())
        self.table.setRowCount(len(self._sales))
        for r, s in enumerate(self._sales):
            vals = [s.invoice_no, clock.fmt_local(s.created_at), s.customer.name if s.customer else "—",
                    format_money(s.total), ar.SALE_STATUS_LABELS.get(s.status, s.status)]
            for c, v in enumerate(vals):
                self.table.setItem(r, c, _cell(v))
        self.empty.setVisible(not self._sales)
        self.details.clear()
        self._set_buttons(None)

    def _current(self):
        rows = self.table.selectionModel().selectedRows()
        row = rows[0].row() if rows else -1
        return self._sales[row] if 0 <= row < len(self._sales) else None

    def _set_buttons(self, sale) -> None:
        posted = sale is not None and sale.status == "posted"
        self.b_print.setEnabled(sale is not None)
        self.b_return.setEnabled(posted)
        self.b_void.setEnabled(posted)

    def _show_details(self) -> None:
        s = self._current()
        self._set_buttons(s)
        if s is None:
            self.details.clear(); return
        lines = [f"<h3>{ar.RECEIPT_TITLE} #{s.invoice_no}</h3>",
                 f"{ar.RECEIPT_DATE}: {clock.fmt_local(s.created_at)}<br>"
                 f"{ar.RECEIPT_CASHIER}: {s.user.full_name if s.user else '—'}<br>"
                 f"{ar.RECEIPT_CUSTOMER}: {s.customer.name if s.customer else '—'}<hr>"]
        for it in s.items:
            imei = f" — IMEI {it.device.imei1}" if it.device else ""
            lines.append(f"{it.product.name}{imei}<br>&nbsp;&nbsp;{it.quantity} × {format_money(it.unit_price)}"
                         f" = {format_money(it.line_total)}<br>")
        lines.append(f"<hr>{ar.RECEIPT_SUBTOTAL}: {format_money(s.subtotal)}<br>"
                     f"{ar.RECEIPT_DISCOUNT}: {format_money(s.discount)}<br>"
                     f"<b>{ar.RECEIPT_NET}: {format_money(s.total)}</b><br>"
                     f"{ar.RECEIPT_PAID}: {format_money(s.paid)}<br>"
                     f"{ar.RECEIPT_REMAINING}: {format_money(s.remaining)}")
        self.details.setHtml("".join(lines))

    # ── actions ─────────────────────────────────────────────────────────
    def _reprint(self) -> None:
        s = self._current()
        if s is None:
            return
        from app.ui.print_dialogs import SaleCompleteDialog
        SaleCompleteDialog(self.session, s, self).exec()

    def _return(self) -> None:
        s = self._current()
        if s is None or s.status != "posted":
            return
        names = [f"{i + 1}. {it.product.name}" + (f" ({it.device.imei1})" if it.device else "")
                 for i, it in enumerate(s.items)]
        chosen, ok = QInputDialog.getItem(self, ar.HISTORY_RETURN, ar.COL_PRODUCT, names, 0, False)
        if not ok:
            return
        item = s.items[names.index(chosen)]
        qty = 1
        if item.quantity > 1:
            qty, ok = QInputDialog.getInt(self, ar.HISTORY_RETURN, ar.CART_QTY, 1, 1, item.quantity)
            if not ok:
                return
        reason, ok = QInputDialog.getText(self, ar.HISTORY_RETURN, ar.HISTORY_VOID_REASON)
        if not (ok and reason.strip()):
            return
        restock = QMessageBox.question(
            self, ar.HISTORY_RETURN, "هل الصنف بحالة جيدة ويصلح لإعادته للمخزن؟") == QMessageBox.Yes
        try:
            sales_service.return_sale_items(
                self.session, self.user, s.id, [{"sale_item_id": item.id, "quantity": qty}],
                reason=reason.strip(), restock=restock, refund_method="cash")
            self.session.commit()
        except (PermissionDenied, sales_service.SaleError, ValueError) as exc:
            self.session.rollback()
            show_error(self, exc)
        self.refresh()

    def _void(self) -> None:
        s = self._current()
        if s is None or s.status != "posted":
            return
        reason, ok = QInputDialog.getText(self, ar.HISTORY_VOID, ar.HISTORY_VOID_REASON)
        if not (ok and reason.strip()):
            return
        if not confirm(self, ar.HISTORY_VOID, ar.HISTORY_VOID_CONFIRM, ar.HISTORY_VOID, destructive=True):
            return
        try:
            sales_service.void_sale(self.session, self.user, s.id, reason.strip())
            self.session.commit()
        except (PermissionDenied, sales_service.SaleError, ValueError) as exc:
            self.session.rollback()
            show_error(self, exc)
        self.refresh()
