"""POS helper dialogs: product chooser, IMEI unit chooser, line editor, held invoices."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QVBoxLayout,
)

from app.core import clock
from app.core.money import format_money, parse_egp_input, piasters_to_input
from app.i18n import ar
from app.services import inventory_service, sales_service
from app.ui.design.style import style_label


def _make_table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QTableWidget.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectRows)
    t.setSelectionMode(QTableWidget.SingleSelection)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    return t


def _cell(text: str, align=Qt.AlignCenter) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setTextAlignment(align)
    return it


class ProductChooserDialog(QDialog):
    """Type-ahead list of products; Enter / double-click picks the highlighted row."""

    def __init__(self, session, text: str = "", parent=None):
        super().__init__(parent)
        self.session = session
        self.chosen = None
        self._rows = []
        self.setWindowTitle(ar.CHOOSE_PRODUCT_TITLE)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumSize(620, 420)
        lay = QVBoxLayout(self)
        self.search = QLineEdit(text)
        self.search.setPlaceholderText(ar.CHOOSE_PRODUCT_HINT)
        self.search.textChanged.connect(self._reload)
        lay.addWidget(self.search)
        self.table = _make_table([ar.COL_PRODUCT, ar.COL_PRICE, ar.COL_STOCK])
        self.table.doubleClicked.connect(self._accept_current)
        self.table.itemActivated.connect(lambda _i: self._accept_current())
        lay.addWidget(self.table)
        self.search.returnPressed.connect(self._accept_current)
        self._reload()
        self.search.setFocus()

    def _reload(self) -> None:
        self._rows = inventory_service.search_products(self.session, self.search.text())
        self.table.setRowCount(len(self._rows))
        for r, p in enumerate(self._rows):
            self.table.setItem(r, 0, _cell(p.name, Qt.AlignRight | Qt.AlignVCenter))
            self.table.setItem(r, 1, _cell(format_money(p.sale_price)))
            self.table.setItem(r, 2, _cell(str(p.current_quantity())))
        if self._rows:
            self.table.selectRow(0)

    def keyPressEvent(self, e):  # arrows in the search box move the selection
        if e.key() in (Qt.Key_Down, Qt.Key_Up) and self._rows:
            row = max(0, self.table.currentRow() + (1 if e.key() == Qt.Key_Down else -1))
            self.table.selectRow(min(row, len(self._rows) - 1))
            return
        super().keyPressEvent(e)

    def _accept_current(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self._rows):
            self.chosen = self._rows[row]
            self.accept()


class DeviceChooserDialog(QDialog):
    """Pick one in-stock unit of an IMEI product (oldest first)."""

    def __init__(self, session, product, exclude_ids: set[int] | None = None, parent=None):
        super().__init__(parent)
        self.chosen = None
        exclude_ids = exclude_ids or set()
        self._rows = [
            d for d in inventory_service.get_devices_for_product(session, product.id, status="in_stock")
            if d.id not in exclude_ids
        ]
        self.setWindowTitle(f"{ar.CHOOSE_DEVICE_TITLE} — {product.name}")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumSize(560, 380)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(ar.CHOOSE_DEVICE_HINT))
        self.table = _make_table([ar.COL_IMEI, ar.COL_IMEI2, ar.COL_CONDITION])
        self.table.setRowCount(len(self._rows))
        for r, d in enumerate(self._rows):
            self.table.setItem(r, 0, _cell(d.imei1))
            self.table.setItem(r, 1, _cell(d.imei2 or "—"))
            self.table.setItem(r, 2, _cell(ar.COND_USED if d.condition == "used" else ar.COND_NEW))
        if self._rows:
            self.table.selectRow(0)
        self.table.doubleClicked.connect(self._accept_current)
        self.table.itemActivated.connect(lambda _i: self._accept_current())
        lay.addWidget(self.table)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._accept_current)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
        self.table.setFocus()

    @property
    def device_count(self) -> int:
        return len(self._rows)

    def _accept_current(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self._rows):
            self.chosen = self._rows[row]
            self.accept()


class LineEditDialog(QDialog):
    """Edit quantity / unit price / line discount of one cart line."""

    def __init__(self, item, can_set_qty: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle(ar.CART_EDIT_LINE)
        self.setLayoutDirection(Qt.RightToLeft)
        form = QFormLayout(self)
        self.qty = QSpinBox()
        self.qty.setRange(1, 100000)
        self.qty.setValue(item.quantity)
        self.qty.setEnabled(can_set_qty)
        self.price = QLineEdit(piasters_to_input(item.unit_price))
        self.discount = QLineEdit(piasters_to_input(item.discount))
        form.addRow(ar.CART_QTY, self.qty)
        form.addRow(ar.CART_UNIT_PRICE, self.price)
        form.addRow(ar.CART_LINE_DISCOUNT, self.discount)
        hint = QLabel(ar.CART_PRICE_APPROVAL)
        style_label(hint, size="caption", tone="muted")
        form.addRow(hint)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._ok)
        btns.rejected.connect(self.reject)
        form.addRow(btns)
        self.values: dict | None = None

    def _ok(self) -> None:
        try:
            self.values = {
                "quantity": self.qty.value(),
                "unit_price": parse_egp_input(self.price.text() or "0"),
                "discount": parse_egp_input(self.discount.text() or "0"),
            }
        except ValueError:
            QMessageBox.warning(self, ar.ERROR if hasattr(ar, "ERROR") else ar.ERROR, ar.SHIFT_INVALID_AMOUNT)
            return
        self.accept()


class HeldInvoicesDialog(QDialog):
    """List held invoices; resume or discard one."""

    def __init__(self, session, user, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self.chosen = None
        self._rows = sales_service.list_held_sales(session)
        self.setWindowTitle(ar.HELD_TITLE)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumSize(640, 380)
        lay = QVBoxLayout(self)
        self.table = _make_table(
            [ar.HISTORY_COL_NO, ar.HISTORY_CUSTOMER, ar.CART_QTY, ar.HISTORY_COL_TOTAL, ar.HISTORY_COL_DATE]
        )
        self._fill()
        self.table.doubleClicked.connect(self._resume)
        lay.addWidget(self.table)
        row = QHBoxLayout()
        b_resume = QPushButton(ar.HELD_RESUME)
        b_resume.setDefault(True)
        b_resume.clicked.connect(self._resume)
        b_discard = QPushButton(ar.HELD_DISCARD)
        b_discard.clicked.connect(self._discard)
        row.addWidget(b_resume)
        row.addWidget(b_discard)
        row.addStretch()
        lay.addLayout(row)

    def _fill(self) -> None:
        self.table.setRowCount(len(self._rows))
        for r, s in enumerate(self._rows):
            self.table.setItem(r, 0, _cell(s.invoice_no))
            self.table.setItem(r, 1, _cell(s.customer.name if s.customer else "—"))
            self.table.setItem(r, 2, _cell(str(len(s.items))))
            self.table.setItem(r, 3, _cell(format_money(s.total)))
            self.table.setItem(r, 4, _cell(clock.fmt_local(s.created_at)))
        if self._rows:
            self.table.selectRow(0)

    def _current(self):
        row = self.table.currentRow()
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def _resume(self) -> None:
        sale = self._current()
        if sale:
            self.chosen = sale
            self.accept()

    def _discard(self) -> None:
        sale = self._current()
        if sale is None:
            return
        for it in list(sale.items):
            sales_service.remove_line(self.session, self.user, sale, it.id)
        self.session.delete(sale)
        self.session.commit()
        self._rows = sales_service.list_held_sales(self.session)
        self._fill()
