"""Read-only view of one purchase invoice: its products, quantities, costs and IMEIs."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

from app.core import clock
from app.core.money import format_money
from app.i18n import ar
from app.models.stock import Device
from app.ui.components import DataTable
from app.ui.design.style import style_label


class PurchaseDetailDialog(QDialog):
    def __init__(self, session, purchase, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{ar.PURCHASE_DETAIL_TITLE} — {purchase.invoice_number}")
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(760, 460)
        lay = QVBoxLayout(self)
        head = QLabel(f"{ar.SUPPLIER}: {purchase.supplier.name if purchase.supplier else '—'}   |   "
                      f"{clock.fmt_local(purchase.created_at)}   |   {ar.TOTAL}: {format_money(purchase.total)}   |   "
                      f"{ar.PAID}: {format_money(purchase.paid)}")
        style_label(head, tone="muted", bold=True)
        lay.addWidget(head)
        self.table = DataTable(["#", ar.PURCHASE_COL_PRODUCT, ar.RECEIPT_COL_QTY, ar.CART_UNIT_PRICE, ar.TOTAL,
                                ar.PURCHASE_INVOICE_DIALOG_7EF49A], ar.PURCHASE_NO_PRODUCTS)
        rows = []
        for i, it in enumerate(purchase.items, 1):
            imeis = [d.imei1 for d in session.query(Device).filter(
                Device.purchase_id == purchase.id, Device.product_id == it.product_id).all()]
            rows.append([str(i), it.product.name, str(it.quantity), format_money(it.unit_cost),
                         format_money(it.total), "، ".join(imeis) if imeis else "—"])
        self.table.set_rows(rows)
        lay.addWidget(self.table, 1)
        close = QPushButton(ar.CLOSE)
        close.clicked.connect(self.accept)
        lay.addWidget(close)
