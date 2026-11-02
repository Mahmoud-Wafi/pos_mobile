"""Device / IMEI list widget."""
from __future__ import annotations

try:
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
        QTableWidgetItem, QHeaderView, QDialog, QFormLayout, QLineEdit,
        QComboBox, QMessageBox, QSpinBox, QLabel,
    )
    from PySide6.QtCore import Qt
    HAS_QT = True
except ImportError:
    HAS_QT = False

if HAS_QT:
    from app.services import inventory_service
    from app.models.product import Product
    from app.core.permissions import PermissionDenied

    HEADERS = ["#", "المنتج", "IMEI 1", "IMEI 2", "الحالة", "الحالة الفيزيائية", "التكلفة"]

    STATUS_AR = {
        "in_stock": "في المخزون",
        "sold": "مباع",
        "returned": "مرتجع",
        "damaged": "تالف",
    }

    class DeviceListWidget(QWidget):
        def __init__(self, session, user, parent=None):
            super().__init__(parent)
            self.session = session
            self.user = user
            self._build_ui()
            self.load_data()

        def _build_ui(self):
            layout = QVBoxLayout(self)

            bar = QHBoxLayout()
            self.btn_add = QPushButton("إضافة جهاز (IMEI) +")
            self.btn_add.clicked.connect(self._add_device)
            self.btn_refresh = QPushButton("تحديث")
            self.btn_refresh.clicked.connect(self.load_data)
            bar.addWidget(self.btn_add)
            bar.addWidget(self.btn_refresh)
            bar.addStretch()
            layout.addLayout(bar)

            self.table = QTableWidget()
            self.table.setColumnCount(len(HEADERS))
            self.table.setHorizontalHeaderLabels(HEADERS)
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            self.table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.table.setSelectionBehavior(QTableWidget.SelectRows)
            self.table.setAlternatingRowColors(True)
            layout.addWidget(self.table)

        def load_data(self):
            from app.models.stock import Device
            self.session.expire_all()
            devices = self.session.query(Device).order_by(Device.id.desc()).limit(200).all()
            self.table.setRowCount(len(devices))
            for row, d in enumerate(devices):
                from app.core.money import format_money
                items = [
                    str(d.id),
                    d.product.name if d.product else "",
                    d.imei1,
                    d.imei2 or "",
                    STATUS_AR.get(d.status, d.status),
                    "جديد" if d.condition == "new" else "مستعمل",
                    format_money(d.total_cost),
                ]
                for col, text in enumerate(items):
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignCenter)
                    self.table.setItem(row, col, item)

        def _add_device(self):
            dlg = AddDeviceDialog(self.session, self.user, parent=self)
            if dlg.exec() == QDialog.Accepted:
                self.load_data()


    class AddDeviceDialog(QDialog):
        def __init__(self, session, user, parent=None):
            super().__init__(parent)
            self.session = session
            self.user = user
            self.setWindowTitle("إضافة جهاز - IMEI")
            self.setMinimumWidth(400)
            self._build_ui()

        def _build_ui(self):
            layout = QFormLayout(self)

            # Product selector (only IMEI-tracked)
            self.product_combo = QComboBox()
            self._load_products()

            self.imei1_edit = QLineEdit(); self.imei1_edit.setPlaceholderText("IMEI 1 (مطلوب)")
            self.imei2_edit = QLineEdit(); self.imei2_edit.setPlaceholderText("IMEI 2 (اختياري)")
            self.condition_combo = QComboBox()
            self.condition_combo.addItems(["جديد", "مستعمل"])
            self.cost_edit = QSpinBox(); self.cost_edit.setRange(0, 999_999_99); self.cost_edit.setSuffix(" قرش")
            self.extra_cost_edit = QSpinBox(); self.extra_cost_edit.setRange(0, 999_999_99); self.extra_cost_edit.setSuffix(" قرش")
            self.notes_edit = QLineEdit()

            layout.addRow("المنتج *", self.product_combo)
            layout.addRow("IMEI 1 *", self.imei1_edit)
            layout.addRow("IMEI 2", self.imei2_edit)
            layout.addRow("الحالة", self.condition_combo)
            layout.addRow("تكلفة الشراء (قرش)", self.cost_edit)
            layout.addRow("تكاليف إضافية (قرش)", self.extra_cost_edit)
            layout.addRow("ملاحظات", self.notes_edit)

            btn_layout = QHBoxLayout()
            btn_save = QPushButton("حفظ")
            btn_save.clicked.connect(self._save)
            btn_cancel = QPushButton("إلغاء")
            btn_cancel.clicked.connect(self.reject)
            btn_layout.addWidget(btn_save)
            btn_layout.addWidget(btn_cancel)
            layout.addRow(btn_layout)

        def _load_products(self):
            self.product_combo.clear()
            products = self.session.query(Product).filter(
                Product.track_imei == True, Product.is_active == True
            ).order_by(Product.name).all()
            self._products = products
            for p in products:
                self.product_combo.addItem(p.name, p.id)

        def _save(self):
            if not self._products:
                QMessageBox.warning(self, "تحذير", "لا توجد منتجات تدعم IMEI. أضف منتجاً أولاً.")
                return
            idx = self.product_combo.currentIndex()
            product = self._products[idx]
            imei1 = self.imei1_edit.text().strip()
            if not imei1:
                QMessageBox.warning(self, "تحذير", "IMEI 1 مطلوب")
                return
            device_data = [{
                "imei1": imei1,
                "imei2": self.imei2_edit.text().strip() or None,
                "condition": "new" if self.condition_combo.currentIndex() == 0 else "used",
                "purchase_cost": self.cost_edit.value(),
                "extra_cost": self.extra_cost_edit.value(),
                "notes": self.notes_edit.text().strip() or None,
            }]
            try:
                inventory_service.add_devices(self.session, self.user, product, device_data)
                self.session.commit()
                self.accept()
            except inventory_service.DuplicateIMEI as e:
                QMessageBox.critical(self, "خطأ", str(e))
            except PermissionDenied as e:
                QMessageBox.critical(self, "خطأ في الصلاحية", str(e))
            except Exception as e:
                self.session.rollback()
                QMessageBox.critical(self, "خطأ", str(e))

