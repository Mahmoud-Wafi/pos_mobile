"""Modern Low stock alert widget with warning badges."""
from __future__ import annotations

try:
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
        QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QFrame,
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor
    HAS_QT = True
except ImportError:
    HAS_QT = False

if HAS_QT:
    from app.services import inventory_service
    from app.core.money import format_money

    HEADERS = ["#", "اسم المنتج", "النوع", "الكمية المتبقية", "حد الطلب الأدنى", "مقدار العجز"]

    class LowStockWidget(QWidget):
        def __init__(self, session, user, parent=None):
            super().__init__(parent)
            self.session = session
            self.user = user
            self._build_ui()
            self.load_data()

        def _build_ui(self):
            layout = QVBoxLayout(self)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.setSpacing(12)

            bar = QHBoxLayout()
            title = QLabel("⚠️ الأصناف التي وصلت لحد الطلب أو نفدت من المخزن")
            title.setStyleSheet("font-size: 14px; font-weight: bold; color: #B45309;")
            bar.addWidget(title)
            bar.addStretch()

            self.btn_refresh = QPushButton("🔄 تحديث القائمة")
            self.btn_refresh.clicked.connect(self.load_data)
            bar.addWidget(self.btn_refresh)
            layout.addLayout(bar)

            self.table = QTableWidget()
            self.table.setColumnCount(len(HEADERS))
            self.table.setHorizontalHeaderLabels(HEADERS)
            self.table.verticalHeader().setVisible(False)
            self.table.verticalHeader().setDefaultSectionSize(44)
            self.table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.table.setSelectionBehavior(QTableWidget.SelectRows)
            self.table.setAlternatingRowColors(True)

            header = self.table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.Fixed); self.table.setColumnWidth(0, 50)
            header.setSectionResizeMode(1, QHeaderView.Stretch)
            header.setSectionResizeMode(2, QHeaderView.Fixed); self.table.setColumnWidth(2, 110)
            header.setSectionResizeMode(3, QHeaderView.Fixed); self.table.setColumnWidth(3, 130)
            header.setSectionResizeMode(4, QHeaderView.Fixed); self.table.setColumnWidth(4, 130)
            header.setSectionResizeMode(5, QHeaderView.Fixed); self.table.setColumnWidth(5, 120)

            layout.addWidget(self.table)

        def load_data(self):
            self.session.expire_all()
            products = inventory_service.low_stock(self.session)
            self.table.setRowCount(len(products))

            for row, p in enumerate(products):
                qty = p.current_quantity()
                deficit = p.min_stock - qty
                is_zero = qty == 0

                type_ar = {"phone": "📱 هاتف", "accessory": "🎧 إكسسوار", "card": "💳 كارت"}.get(p.type, p.type)

                cols = [
                    (str(p.id), Qt.AlignCenter, None, None, None),
                    (p.name, Qt.AlignRight | Qt.AlignVCenter, None, True, None),
                    (type_ar, Qt.AlignCenter, "#64748B", False, None),
                    (f"{qty} قطعة" if qty > 0 else "❌ نفد المخزون", Qt.AlignCenter, "#991B1B" if is_zero else "#92400E", True, "#FEE2E2" if is_zero else "#FEF3C7"),
                    (f"{p.min_stock} قطعة", Qt.AlignCenter, "#334155", False, None),
                    (f"-{deficit} قطعة", Qt.AlignCenter, "#DC2626", True, None),
                ]

                for col, (text, align, fg, is_bold, bg) in enumerate(cols):
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(align)
                    item.setForeground(QColor(fg or "#0F172A"))
                    if is_bold:
                        f = item.font(); f.setBold(True); item.setFont(f)
                    if bg:
                        item.setBackground(QColor(bg))
                    self.table.setItem(row, col, item)
