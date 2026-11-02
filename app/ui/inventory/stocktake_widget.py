"""Stocktake (physical count) widget."""
from __future__ import annotations

try:
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox,
        QSpinBox, QLineEdit, QFormLayout, QMessageBox, QLabel,
        QTableWidget, QTableWidgetItem, QHeaderView,
    )
    from PySide6.QtCore import Qt
    HAS_QT = True
except ImportError:
    HAS_QT = False

if HAS_QT:
    from app.services import inventory_service
    from app.models.product import Product
    from app.core.permissions import PermissionDenied

    class StocktakeWidget(QWidget):
        def __init__(self, session, user, parent=None):
            super().__init__(parent)
            self.session = session
            self.user = user
            self._build_ui()

        def _build_ui(self):
            layout = QVBoxLayout(self)
            layout.addWidget(QLabel("جرد المخزون — أدخل الكمية الفعلية لكل منتج"))

            form = QFormLayout()
            self.product_combo = QComboBox()
            self._load_products()
            self.actual_qty = QSpinBox()
            self.actual_qty.setRange(0, 99999)
            self.reason_edit = QLineEdit()
            self.reason_edit.setPlaceholderText("سبب الجرد (اختياري)")

            form.addRow("المنتج", self.product_combo)
            form.addRow("الكمية الفعلية", self.actual_qty)
            form.addRow("السبب", self.reason_edit)
            layout.addLayout(form)

            btn = QPushButton("تسجيل الجرد")
            btn.clicked.connect(self._do_stocktake)
            layout.addWidget(btn)

            # History table
            layout.addWidget(QLabel("سجل التسويات:"))
            self.history_table = QTableWidget()
            self.history_table.setColumnCount(4)
            self.history_table.setHorizontalHeaderLabels(["المنتج", "التغيير", "السبب", "التاريخ"])
            self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            self.history_table.setEditTriggers(QTableWidget.NoEditTriggers)
            layout.addWidget(self.history_table)
            self._load_history()

        def _load_products(self):
            self.product_combo.clear()
            self._products = self.session.query(Product).filter(
                Product.track_imei == False, Product.is_active == True
            ).order_by(Product.name).all()
            for p in self._products:
                qty = p.current_quantity()
                self.product_combo.addItem(f"{p.name} (حالي: {qty})", p.id)

        def _do_stocktake(self):
            if not self._products:
                QMessageBox.warning(self, "تحذير", "لا توجد منتجات غير IMEI للجرد")
                return
            product = self._products[self.product_combo.currentIndex()]
            actual = self.actual_qty.value()
            reason = self.reason_edit.text().strip() or "جرد مخزون"
            try:
                mv = inventory_service.stocktake(self.session, self.user, product, actual, reason)
                self.session.commit()
                if mv is None:
                    QMessageBox.information(self, "معلومة", "الكمية لم تتغير — لا يوجد فرق")
                else:
                    QMessageBox.information(self, "نجاح", f"تم تسجيل الجرد. الفرق: {mv.quantity:+d}")
                self._load_products()
                self._load_history()
            except PermissionDenied as e:
                QMessageBox.critical(self, "خطأ في الصلاحية", str(e))
            except Exception as e:
                self.session.rollback()
                QMessageBox.critical(self, "خطأ", str(e))

        def _load_history(self):
            from app.models.stock import StockMovement
            movements = self.session.query(StockMovement).filter(
                StockMovement.type == "adjust"
            ).order_by(StockMovement.created_at.desc()).limit(50).all()
            self.history_table.setRowCount(len(movements))
            for row, mv in enumerate(movements):
                items = [
                    mv.product.name if mv.product else str(mv.product_id),
                    f"{mv.quantity:+d}",
                    mv.note or "",
                    mv.created_at.strftime("%Y-%m-%d %H:%M") if mv.created_at else "",
                ]
                for col, text in enumerate(items):
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignCenter)
                    self.history_table.setItem(row, col, item)

