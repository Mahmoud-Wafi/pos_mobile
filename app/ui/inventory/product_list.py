"""Product list widget with add/edit dialogs."""
from __future__ import annotations

try:
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
        QTableWidgetItem, QHeaderView, QDialog, QFormLayout, QLineEdit,
        QComboBox, QCheckBox, QMessageBox, QLabel, QSpinBox,
    )
    from PySide6.QtCore import Qt
    HAS_QT = True
except ImportError:
    HAS_QT = False

if HAS_QT:
    from app.services import inventory_service
    from app.core.money import format_money, piasters_to_egp
    from app.core.permissions import PermissionDenied

    HEADERS = ["#", "الاسم", "النوع", "الباركود", "سعر البيع", "الكمية", "الحد الأدنى", "تتبع IMEI", "نشط"]

    class ProductListWidget(QWidget):
        def __init__(self, session, user, parent=None):
            super().__init__(parent)
            self.session = session
            self.user = user
            self._build_ui()
            self.load_data()

        def _build_ui(self):
            layout = QVBoxLayout(self)

            # Toolbar
            bar = QHBoxLayout()
            self.btn_add = QPushButton("إضافة منتج +")
            self.btn_add.clicked.connect(self._add_product)
            self.btn_refresh = QPushButton("تحديث")
            self.btn_refresh.clicked.connect(self.load_data)
            bar.addWidget(self.btn_add)
            bar.addWidget(self.btn_refresh)
            bar.addStretch()
            layout.addLayout(bar)

            # Table
            self.table = QTableWidget()
            self.table.setColumnCount(len(HEADERS))
            self.table.setHorizontalHeaderLabels(HEADERS)
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            self.table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.table.setSelectionBehavior(QTableWidget.SelectRows)
            self.table.setAlternatingRowColors(True)
            layout.addWidget(self.table)

        def load_data(self):
            self.session.expire_all()
            products = inventory_service.get_all_products(self.session, active_only=False)
            self.table.setRowCount(len(products))
            for row, p in enumerate(products):
                qty = p.current_quantity()
                low = qty <= p.min_stock
                items = [
                    str(p.id),
                    p.name,
                    {"phone": "هاتف", "accessory": "إكسسوار", "card": "كارت"}.get(p.type, p.type),
                    p.barcode or "",
                    format_money(p.sale_price),
                    str(qty),
                    str(p.min_stock),
                    "نعم" if p.track_imei else "لا",
                    "نشط" if p.is_active else "متوقف",
                ]
                for col, text in enumerate(items):
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignCenter)
                    if low and col == 5:
                        from PySide6.QtGui import QColor
                        item.setBackground(QColor("#FFD0D0"))
                    self.table.setItem(row, col, item)

        def _add_product(self):
            dlg = ProductDialog(self.session, self.user, parent=self)
            if dlg.exec() == QDialog.Accepted:
                self.load_data()


    class ProductDialog(QDialog):
        """Add product dialog."""

        def __init__(self, session, user, parent=None):
            super().__init__(parent)
            self.session = session
            self.user = user
            self.setWindowTitle("إضافة منتج جديد")
            self.setMinimumWidth(400)
            self._build_ui()

        def _build_ui(self):
            layout = QFormLayout(self)

            self.name_edit = QLineEdit()
            self.barcode_edit = QLineEdit()
            self.type_combo = QComboBox()
            self.type_combo.addItems(["accessory", "phone", "card"])
            self.type_combo.setItemText(0, "إكسسوار")
            self.type_combo.setItemText(1, "هاتف")
            self.type_combo.setItemText(2, "كارت")
            self.cost_edit = QSpinBox(); self.cost_edit.setRange(0, 999_999_99); self.cost_edit.setSuffix(" قرش")
            self.sale_edit = QSpinBox(); self.sale_edit.setRange(0, 999_999_99); self.sale_edit.setSuffix(" قرش")
            self.min_price_edit = QSpinBox(); self.min_price_edit.setRange(0, 999_999_99); self.min_price_edit.setSuffix(" قرش")
            self.min_stock_edit = QSpinBox(); self.min_stock_edit.setRange(0, 9999)
            self.warranty_edit = QSpinBox(); self.warranty_edit.setRange(0, 3650); self.warranty_edit.setSuffix(" يوم")
            self.track_imei_check = QCheckBox("تتبع بـ IMEI")

            layout.addRow("اسم المنتج *", self.name_edit)
            layout.addRow("باركود", self.barcode_edit)
            layout.addRow("النوع", self.type_combo)
            layout.addRow("سعر التكلفة (قرش)", self.cost_edit)
            layout.addRow("سعر البيع (قرش)", self.sale_edit)
            layout.addRow("أقل سعر (قرش)", self.min_price_edit)
            layout.addRow("الحد الأدنى للمخزون", self.min_stock_edit)
            layout.addRow("أيام الضمان", self.warranty_edit)
            layout.addRow("", self.track_imei_check)

            btn_layout = QHBoxLayout()
            btn_save = QPushButton("حفظ")
            btn_save.clicked.connect(self._save)
            btn_cancel = QPushButton("إلغاء")
            btn_cancel.clicked.connect(self.reject)
            btn_layout.addWidget(btn_save)
            btn_layout.addWidget(btn_cancel)
            layout.addRow(btn_layout)

        def _save(self):
            name = self.name_edit.text().strip()
            if not name:
                QMessageBox.warning(self, "تحذير", "يجب إدخال اسم المنتج")
                return
            type_map = {0: "accessory", 1: "phone", 2: "card"}
            data = {
                "name": name,
                "barcode": self.barcode_edit.text().strip() or None,
                "type": type_map[self.type_combo.currentIndex()],
                "cost_price": self.cost_edit.value(),
                "sale_price": self.sale_edit.value(),
                "min_price": self.min_price_edit.value(),
                "min_stock": self.min_stock_edit.value(),
                "warranty_days": self.warranty_edit.value(),
                "track_imei": self.track_imei_check.isChecked(),
            }
            try:
                inventory_service.create_product(self.session, self.user, data)
                self.session.commit()
                self.accept()
            except PermissionDenied as e:
                QMessageBox.critical(self, "خطأ في الصلاحية", str(e))
            except Exception as e:
                self.session.rollback()
                QMessageBox.critical(self, "خطأ", str(e))

