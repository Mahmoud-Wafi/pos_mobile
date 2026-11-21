"""Phone model field: type any model name; pick an existing one or add a new one on the fly.

The old field was a read-only drop-down, so on a fresh install (no phone products yet) it was an empty box
that ignored the keyboard. This one is editable with auto-complete; a name that does not exist yet reveals a
'sale price' field and the model is created as a phone product (IMEI-tracked) when the form is saved.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QCompleter, QLabel, QLineEdit, QVBoxLayout, QWidget

from app.core.money import parse_egp_input
from app.i18n import ar
from app.models.product import Product
from app.services import inventory_service
from app.ui.components.numeric import set_money_validator
from app.ui.design.style import style_label


class ModelPicker(QWidget):
    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.setInsertPolicy(QComboBox.NoInsert)
        self.combo.setMinimumHeight(40)
        self.combo.lineEdit().setPlaceholderText(ar.MODEL_PICKER_PLACEHOLDER)
        comp = self.combo.completer()
        comp.setFilterMode(Qt.MatchContains)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        comp.setCompletionMode(QCompleter.PopupCompletion)
        lay.addWidget(self.combo)

        self.new_hint = QLabel(ar.MODEL_PICKER_NEW_HINT)
        style_label(self.new_hint, size="caption", tone="info", bold=True)
        self.price_edit = QLineEdit()
        self.price_edit.setFixedHeight(40)
        self.price_edit.setPlaceholderText(ar.MODEL_PICKER_PRICE)
        set_money_validator(self.price_edit, 0.0, 9999999.0)
        lay.addWidget(self.new_hint)
        lay.addWidget(self.price_edit)
        self.new_hint.setVisible(False)
        self.price_edit.setVisible(False)

        self.combo.editTextChanged.connect(self._on_text)
        self.reload()

    # ── data ──
    def reload(self) -> None:
        text = self.combo.currentText()
        self.combo.blockSignals(True)
        self.combo.clear()
        for p in (self.session.query(Product)
                  .filter(Product.track_imei == True, Product.is_active == True)  # noqa: E712
                  .order_by(Product.name.asc()).all()):
            self.combo.addItem(p.name, p.id)
        self.combo.setCurrentIndex(-1)
        self.combo.setEditText(text)
        self.combo.blockSignals(False)
        self._on_text()

    def text(self) -> str:
        return self.combo.currentText().strip()

    def existing(self) -> Product | None:
        name = self.text().casefold()
        if not name:
            return None
        for i in range(self.combo.count()):
            if self.combo.itemText(i).strip().casefold() == name:
                return self.session.get(Product, self.combo.itemData(i))
        return None

    def set_product(self, product: Product) -> None:
        self.combo.setEditText(product.name)

    def _on_text(self, *_args) -> None:
        is_new = bool(self.text()) and self.existing() is None
        self.new_hint.setVisible(is_new)
        self.price_edit.setVisible(is_new)

    def default_cost(self) -> int | None:
        p = self.existing()
        return p.cost_price if p is not None else None

    # ── resolve at save time ──
    def resolve(self, user) -> Product:
        """The chosen product, creating a new IMEI-tracked phone product for a new model name."""
        name = self.text()
        if not name:
            raise ValueError(ar.MODEL_PICKER_REQUIRED)
        found = self.existing()
        if found is not None:
            return found
        try:
            price = parse_egp_input(self.price_edit.text() or "0")
        except ValueError:
            raise ValueError(ar.MODEL_PICKER_PRICE_BAD) from None
        if price <= 0:
            raise ValueError(ar.MODEL_PICKER_PRICE_REQUIRED)
        return inventory_service.create_product(self.session, user, {
            "name": name, "type": "phone", "cost_price": 0, "sale_price": price, "min_price": 0,
            "min_stock": 0, "track_imei": True, "warranty_days": 0})
