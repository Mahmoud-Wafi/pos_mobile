"""Supplier account statement: every invoice and every payment, with a running balance."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from app.core import clock
from app.core.money import format_money
from app.i18n import ar
from app.services import purchase_service
from app.ui.components import DataTable
from app.ui.design.style import style_label, variant

KIND_AR = {
    "opening": ar.SUPPLIER_KIND_OPENING, "invoice": ar.SUPPLIER_KIND_INVOICE,
    "paid_at_invoice": ar.SUPPLIER_KIND_PAID_AT_INVOICE, "payment": ar.SUPPLIER_KIND_PAYMENT,
    "on_account": ar.SUPPLIER_KIND_ON_ACCOUNT,
}


class SupplierLedgerDialog(QDialog):
    def __init__(self, session, user, supplier, parent=None):
        super().__init__(parent)
        self.session, self.user, self.supplier = session, user, supplier
        self._filter_purchase_id = None
        self.setWindowTitle(f"{ar.SUPPLIER_LEDGER_TITLE}: {supplier.name}")
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(980, 640)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(10)

        self.lbl_totals = QLabel("")
        style_label(self.lbl_totals, size="h2", tone="primary", bold=True)
        lay.addWidget(self.lbl_totals)

        sub = QLabel(ar.SUPPLIER_LEDGER_INVOICES)
        style_label(sub, tone="muted", bold=True)
        lay.addWidget(sub)
        self.invoices_table = DataTable(ar.SUPPLIER_LEDGER_INV_COLS, ar.SUPPLIER_LEDGER_TITLE)
        self.invoices_table.setMaximumHeight(190)
        self.invoices_table.cellClicked.connect(self._on_invoice_clicked)
        lay.addWidget(self.invoices_table)

        bar = QHBoxLayout()
        self.lbl_moves = QLabel(ar.SUPPLIER_LEDGER_MOVES)
        style_label(self.lbl_moves, tone="muted", bold=True)
        bar.addWidget(self.lbl_moves)
        bar.addStretch()
        self.btn_all = QPushButton(ar.SUPPLIER_LEDGER_ALL)
        variant(self.btn_all, "secondary")
        self.btn_all.clicked.connect(self._show_all)
        bar.addWidget(self.btn_all)
        lay.addLayout(bar)

        self.table = DataTable(ar.SUPPLIER_LEDGER_COLS, ar.SUPPLIER_LEDGER_TITLE)
        lay.addWidget(self.table, 1)

        close = QPushButton(ar.CLOSE)
        close.setFixedHeight(40)
        close.clicked.connect(self.accept)
        lay.addWidget(close)
        self.reload()

    def reload(self) -> None:
        self.session.expire_all()
        self.data = purchase_service.supplier_ledger(self.session, self.user, self.supplier.id)
        d = self.data
        self.lbl_totals.setText(ar.SUPPLIER_LEDGER_TOTALS.format(
            format_money(d["total_purchases"]), format_money(d["total_paid"]), format_money(d["balance"])))
        self.invoices_table.set_rows(
            [[i["invoice_number"], clock.fmt_local(i["at"]), format_money(i["total"]), format_money(i["paid"]),
              format_money(i["remaining"])] for i in d["invoices"]],
            keys=[i["id"] for i in d["invoices"]])
        self._render_entries()

    def _render_entries(self) -> None:
        rows = []
        for e in self.data["entries"]:
            if self._filter_purchase_id is not None and e["purchase_id"] != self._filter_purchase_id:
                continue
            rows.append([clock.fmt_local(e["at"]) if e["at"] else "—", KIND_AR[e["kind"]], e["ref"] or "—",
                         format_money(e["debit"]) if e["debit"] else "—",
                         format_money(e["credit"]) if e["credit"] else "—",
                         format_money(e["balance"]), e["note"] or "—"])
        self.table.set_rows(rows)

    def _on_invoice_clicked(self, *_args) -> None:
        key = self.invoices_table.selected_key()
        inv = next((i for i in self.data["invoices"] if i["id"] == key), None)
        if inv is None:
            return
        self._filter_purchase_id = inv["id"]
        self.lbl_moves.setText(f"{ar.SUPPLIER_LEDGER_MOVES} — {inv['invoice_number']}")
        self._render_entries()

    def _show_all(self) -> None:
        self._filter_purchase_id = None
        self.lbl_moves.setText(ar.SUPPLIER_LEDGER_MOVES)
        self._render_entries()
