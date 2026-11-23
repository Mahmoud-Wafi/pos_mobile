"""Touch-friendly product catalogue for the POS: category chips + a responsive grid of product cards."""
from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from app.core.money import format_money
from app.i18n import ar
from app.models.product import Product
from app.ui.design import icons
from app.ui.design.style import set_prop
from app.ui.design.tokens import COLORS as C

CARD_MIN_WIDTH = 176
MAX_CARDS = 80
_TYPE_ICON = {"phone": "smartphone", "accessory": "package", "card": "receipt"}
_TYPES = [("all", ar.POS_CATEGORY_ALL), ("phone", ar.POS_CAT_PHONES), ("accessory", ar.POS_CAT_ACCESSORIES),
          ("card", ar.POS_CAT_CARDS)]


class ProductCard(QFrame):
    clicked = Signal()

    def __init__(self, product: Product, parent=None):
        super().__init__(parent)
        self.product_id = product.id
        set_prop(self, "prodcard", True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(150)
        self.setFocusPolicy(Qt.StrongFocus)                      # Tab / Enter / Space work like a button
        self.setAccessibleName(product.name)
        qty = product.current_quantity()
        self._sellable = qty > 0 or product.track_imei          # out-of-stock accessories cannot be sold
        set_prop(self, "soldout", not self._sellable)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(8)
        chip = QLabel()
        chip.setAlignment(Qt.AlignCenter)
        chip.setPixmap(icons.pixmap(_TYPE_ICON.get(product.type, "package"), C["primary"], 28))
        chip.setProperty("tile", True)
        name = QLabel(product.name)
        name.setWordWrap(True)
        name.setProperty("prod_name", True)
        price = QLabel(format_money(product.sale_price))
        price.setProperty("prod_price", True)
        if qty <= 0:
            text, pill = ar.POS_OUT_OF_STOCK, "danger"
        elif product.min_stock and qty <= product.min_stock:
            text, pill = ar.POS_LOW_STOCK.format(n=qty), "warning"
        else:
            text, pill = ar.POS_IN_STOCK.format(n=qty), "success"
        stock = QLabel(text)
        stock.setProperty("pill", pill)
        foot = QHBoxLayout()
        foot.addWidget(price)
        foot.addStretch()
        foot.addWidget(stock)
        lay.addWidget(chip)
        lay.addWidget(name, 1)
        lay.addLayout(foot)
        for w in (chip, name, price, stock):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setToolTip(product.name)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton and self.rect().contains(ev.position().toPoint()) and self._sellable:
            self.clicked.emit()
        super().mouseReleaseEvent(ev)

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space) and self._sellable:
            self.clicked.emit()
        else:
            super().keyPressEvent(ev)


class ProductGrid(QWidget):
    product_picked = Signal(object)

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self._type = "all"
        self._text = ""
        self._products: list[Product] = []
        self._cards: list[ProductCard] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        chips = QHBoxLayout()
        chips.setSpacing(8)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for key, label in _TYPES:
            b = QPushButton(label)
            b.setCheckable(True)
            b.setChecked(key == "all")
            b.setProperty("no_icon", True)
            set_prop(b, "chip", True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self._set_type(k))
            self._group.addButton(b)
            chips.addWidget(b)
        chips.addStretch()
        root.addLayout(chips)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        set_prop(self._scroll, "transparent", True)
        self._body = QWidget()
        set_prop(self._body, "transparent", True)
        self._grid = QGridLayout(self._body)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(12)
        self._scroll.setWidget(self._body)
        root.addWidget(self._scroll, 1)
        self.reload()

    # ── data ─────────────────────────────────────────────────────────────
    def reload(self) -> None:
        from app.services import inventory_service
        self._products = inventory_service.get_all_products(self.session)
        self._rebuild()

    def set_filter_text(self, text: str) -> None:
        self._text = (text or "").strip().lower()
        self._rebuild()

    def _set_type(self, key: str) -> None:
        self._type = key
        self._rebuild()

    def visible_products(self) -> list[Product]:
        out = []
        for p in self._products:
            if self._type != "all" and p.type != self._type:
                continue
            if self._text and self._text not in p.name.lower() and not any(self._text in b.lower() for b in p.all_barcodes()):
                continue
            out.append(p)
        return out[:MAX_CARDS]

    # ── layout ───────────────────────────────────────────────────────────
    def _columns(self) -> int:
        return max(1, (self.width() + 12) // (CARD_MIN_WIDTH + 12))

    def _rebuild(self) -> None:
        for c in self._cards:
            self._grid.removeWidget(c)
            c.hide()
            c.setParent(None)          # gone at once, not at the next event-loop pass
            c.deleteLater()
        self._cards = []
        cols = self._columns()
        for i, p in enumerate(self.visible_products()):
            card = ProductCard(p)
            card.clicked.connect(lambda _=False, prod=p: self.product_picked.emit(prod))
            self._grid.addWidget(card, i // cols, i % cols)
            self._cards.append(card)
        for c in range(cols):
            self._grid.setColumnStretch(c, 1)
        self._cols = cols
        self._grid.setRowStretch(len(self._cards) // cols + 1, 1)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._relayout()

    def showEvent(self, ev):
        super().showEvent(ev)
        QTimer.singleShot(0, self._relayout)          # the viewport has its real width only after the first layout pass

    def _relayout(self) -> None:
        if getattr(self, "_cols", None) != self._columns():
            self._rebuild()
