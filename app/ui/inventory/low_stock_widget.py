"""Low stock alert widget."""
from __future__ import annotations

try:
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
        QTableWidget, QTableWidgetItem, QHeaderView, QLabel,
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor
    HAS_QT = True
except ImportError:
    HAS_QT = False

if HAS_QT:
    from app.services import inventory_service
    from app.core.money import format_money

    HEADERS = ["#", "المنتج", "النوع", "الكمية الحالية", "الحد الأدنى", "الفرق"]

    class LowStockWidget(QWidget):
        def __init__(self, session, user, parent=None):
            super().__init__(parent)
            self.session = session
            self.user = user
            self._build_ui()
            self.load_data()

        def _build_ui(self):
            layout = QVBoxLayout(self)

            bar = QHBoxLayout()
            bar.addWidget(QLabel("المنتجات ذات المخزون المنخفض"))
            self.btn_refresh = QPushButton("تحديث")
            self.btn_refresh.clicked.connect(self.load_data)
            bar.addWidget(self.btn_refresh)
            bar.addStretch()
            layout.addLayout(bar)

            self.table = QTableWidget()
            self.table.setColumnCount(len(HEADERS))
            self.table.setHorizontalHeaderLabels(HEADERS)
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            self.table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.table.setAlternatingRowColors(True)
            layout.addWidget(self.table)

        def load_data(self):
            self.session.expire_all()
            products = inventory_service.low_stock(self.session)
            self.table.setRowCount(len(products))
            for row, p in enumerate(products):
                qty = p.current_quantity()
                diff = qty - p.min_stock
                items = [
                    str(p.id), p.name,
                    {"phone": "هاتف", "accessory": "إكسسوار", "card": "كارت"}.get(p.type, p.type),
                    str(qty), str(p.min_stock), str(diff),
                ]
                for col, text in enumerate(items):
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignCenter)
                    if qty == 0:
                        item.setBackground(QColor("#FFB3B3"))
                    else:
                        item.setBackground(QColor("#FFE0A0"))
                    self.table.setItem(row, col, item)

