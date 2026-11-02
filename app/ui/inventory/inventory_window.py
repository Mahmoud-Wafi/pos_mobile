"""Inventory module UI — tab container for products, devices, low-stock, stocktake."""
from __future__ import annotations

try:
    from PySide6.QtWidgets import QWidget, QVBoxLayout, QTabWidget
    from PySide6.QtCore import Qt
    HAS_QT = True
except ImportError:
    HAS_QT = False

if HAS_QT:
    from app.ui.inventory.product_list import ProductListWidget
    from app.ui.inventory.device_list import DeviceListWidget
    from app.ui.inventory.low_stock_widget import LowStockWidget
    from app.ui.inventory.stocktake_widget import StocktakeWidget

    class InventoryWindow(QWidget):
        """Main inventory screen with 4 tabs."""

        def __init__(self, session, user, parent=None):
            super().__init__(parent)
            self.session = session
            self.user = user
            self._build_ui()

        def _build_ui(self):
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)

            self.tabs = QTabWidget()
            self.tabs.setLayoutDirection(Qt.RightToLeft)

            self.product_list = ProductListWidget(self.session, self.user)
            self.device_list = DeviceListWidget(self.session, self.user)
            self.low_stock = LowStockWidget(self.session, self.user)
            self.stocktake = StocktakeWidget(self.session, self.user)

            self.tabs.addTab(self.product_list, "المنتجات")
            self.tabs.addTab(self.device_list, "الأجهزة / IMEI")
            self.tabs.addTab(self.low_stock, "مخزون منخفض")
            self.tabs.addTab(self.stocktake, "جرد المخزون")

            layout.addWidget(self.tabs)

        def refresh(self):
            self.product_list.load_data()
            self.device_list.load_data()
            self.low_stock.load_data()

