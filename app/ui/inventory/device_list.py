"""Modern Device / IMEI list widget with search, status badges, and clean dialog."""
from __future__ import annotations

from app.core.money import piasters_to_input

from decimal import Decimal

try:
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
        QTableWidgetItem, QHeaderView, QDialog, QLineEdit,
        QComboBox, QMessageBox, QLabel, QFrame, QGridLayout, QGroupBox,
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QDoubleValidator
    HAS_QT = True
except ImportError:
    HAS_QT = False

if HAS_QT:
    from app.services import inventory_service
    from app.models.product import Product
    from app.core.money import format_money, egp_to_piasters
    from app.core.permissions import PermissionDenied

    HEADERS = ["#", "اسم الجهاز / الموديل", "IMEI 1 (السيريال الأول)", "IMEI 2 (السيريال الثاني)", "الحالة بالمخزن", "الحالة الفنية", "التكلفة الإجمالية"]

    STATUS_CONFIG = {
        "in_stock": ("في المخزون", "#ECFDF5", "#065F46"),
        "sold": ("مباع", "#EFF6FF", "#1E40AF"),
        "returned": ("مرتجع", "#FEF3C7", "#92400E"),
        "damaged": ("تالف", "#FEE2E2", "#991B1B"),
    }

    class DeviceListWidget(QWidget):
        def __init__(self, session, user, parent=None):
            super().__init__(parent)
            self.session = session
            self.user = user
            self._all_devices = []
            self._build_ui()
            self.load_data()

        def _build_ui(self):
            layout = QVBoxLayout(self)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.setSpacing(12)

            bar = QHBoxLayout()
            bar.setSpacing(10)

            self.search_edit = QLineEdit()
            self.search_edit.setPlaceholderText("🔍 ابحث برقم الـ IMEI أو اسم الجهاز...")
            self.search_edit.setMinimumWidth(300)
            self.search_edit.setFixedHeight(40)
            self.search_edit.textChanged.connect(self._filter_devices)
            bar.addWidget(self.search_edit)

            self.filter_status = QComboBox()
            self.filter_status.setFixedHeight(40)
            self.filter_status.addItem("جميع الحالات", "all")
            self.filter_status.addItem("في المخزون فقط", "in_stock")
            self.filter_status.addItem("المباعة فقط", "sold")
            self.filter_status.addItem("المرتجعة فقط", "returned")
            self.filter_status.currentIndexChanged.connect(self._filter_devices)
            bar.addWidget(self.filter_status)

            bar.addStretch()

            self.btn_refresh = QPushButton("🔄 تحديث")
            self.btn_refresh.setFixedHeight(40)
            self.btn_refresh.clicked.connect(self.load_data)
            bar.addWidget(self.btn_refresh)

            self.btn_add = QPushButton("➕ تسجيل جهاز جديد (IMEI)")
            self.btn_add.setObjectName("PrimaryBtn")
            self.btn_add.setFixedHeight(40)
            self.btn_add.clicked.connect(self._add_device)
            bar.addWidget(self.btn_add)

            layout.addLayout(bar)

            # Table
            self.table = QTableWidget()
            self.table.setColumnCount(len(HEADERS))
            self.table.setHorizontalHeaderLabels(HEADERS)
            self.table.verticalHeader().setVisible(False)
            self.table.verticalHeader().setDefaultSectionSize(46)
            self.table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.table.setSelectionBehavior(QTableWidget.SelectRows)
            self.table.setAlternatingRowColors(True)

            header = self.table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.Fixed); self.table.setColumnWidth(0, 50)
            header.setSectionResizeMode(1, QHeaderView.Stretch)
            header.setSectionResizeMode(2, QHeaderView.Fixed); self.table.setColumnWidth(2, 190)
            header.setSectionResizeMode(3, QHeaderView.Fixed); self.table.setColumnWidth(3, 190)
            header.setSectionResizeMode(4, QHeaderView.Fixed); self.table.setColumnWidth(4, 120)
            header.setSectionResizeMode(5, QHeaderView.Fixed); self.table.setColumnWidth(5, 110)
            header.setSectionResizeMode(6, QHeaderView.Fixed); self.table.setColumnWidth(6, 150)

            layout.addWidget(self.table)

            self.footer_label = QLabel()
            self.footer_label.setStyleSheet("color: #64748B; font-weight: 600; font-size: 13px; padding-top: 4px;")
            layout.addWidget(self.footer_label)

        def load_data(self):
            from app.models.stock import Device
            self.session.expire_all()
            self._all_devices = self.session.query(Device).order_by(Device.id.desc()).all()
            self._filter_devices()

        def _filter_devices(self):
            text = self.search_edit.text().strip().lower()
            status_filter = self.filter_status.currentData()

            filtered = []
            for d in self._all_devices:
                if status_filter != "all" and d.status != status_filter:
                    continue
                if text:
                    pname = d.product.name.lower() if d.product else ""
                    i1 = d.imei1.lower()
                    i2 = d.imei2.lower() if d.imei2 else ""
                    if not (text in pname or text in i1 or text in i2):
                        continue
                filtered.append(d)

            self._populate_table(filtered)

        def _populate_table(self, devices):
            self.table.setRowCount(len(devices))
            for row, d in enumerate(devices):
                status_ar, bg_col, fg_col = STATUS_CONFIG.get(d.status, (d.status, "#F1F5F9", "#0F172A"))
                cond_ar = "✨ جديد" if d.condition == "new" else "📦 مستعمل"

                cols = [
                    (str(d.id), Qt.AlignCenter, None, None, None),
                    (d.product.name if d.product else "", Qt.AlignRight | Qt.AlignVCenter, None, True, None),
                    (d.imei1, Qt.AlignCenter, "#0284C7", True, None),
                    (d.imei2 or "—", Qt.AlignCenter, "#64748B", False, None),
                    (status_ar, Qt.AlignCenter, fg_col, True, bg_col),
                    (cond_ar, Qt.AlignCenter, "#334155", False, None),
                    (format_money(d.total_cost), Qt.AlignCenter, "#0F172A", True, None),
                ]

                for col, (val, align, fg, is_bold, bg) in enumerate(cols):
                    item = QTableWidgetItem(val)
                    item.setTextAlignment(align)
                    item.setForeground(QColor(fg or "#0F172A"))
                    if is_bold:
                        f = item.font(); f.setBold(True); item.setFont(f)
                    if bg:
                        item.setBackground(QColor(bg))
                    self.table.setItem(row, col, item)

            self.footer_label.setText(f"إجمالي الأجهزة المسجلة: {len(devices)} جهاز")

        def _add_device(self):
            dlg = AddDeviceDialog(self.session, self.user, parent=self)
            if dlg.exec() == QDialog.Accepted:
                self.load_data()


    class AddDeviceDialog(QDialog):
        """Beautiful modern modal dialog for registering individual phones with IMEI."""

        def __init__(self, session, user, parent=None):
            super().__init__(parent)
            self.session = session
            self.user = user
            self.setWindowTitle("تسجيل جهاز هاتف جديد (IMEI)")
            self.setMinimumWidth(620)
            self.setStyleSheet("""
                QDialog {
                    background-color: #FFFFFF;
                }
                QLabel {
                    color: #1E293B;
                    font-size: 13px;
                }
                QLineEdit, QComboBox {
                    background-color: #F8FAFC;
                    border: 1px solid #CBD5E1;
                    border-radius: 8px;
                    padding: 9px 12px;
                    font-size: 13px;
                    color: #0F172A;
                }
                QLineEdit:focus, QComboBox:focus {
                    background-color: #FFFFFF;
                    border: 2px solid #2563EB;
                }
                QGroupBox {
                    font-weight: bold;
                    font-size: 14px;
                    color: #0F172A;
                    border: 1px solid #E2E8F0;
                    border-radius: 10px;
                    margin-top: 14px;
                    padding-top: 18px;
                    padding-bottom: 14px;
                    padding-left: 14px;
                    padding-right: 14px;
                    background-color: #FFFFFF;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top right;
                    padding: 0 8px;
                    color: #2563EB;
                }
            """)
            self._build_ui()

        def _build_ui(self):
            main_layout = QVBoxLayout(self)
            main_layout.setContentsMargins(28, 24, 28, 24)
            main_layout.setSpacing(18)

            # Header
            header_box = QHBoxLayout()
            icon_lbl = QLabel("📱")
            icon_lbl.setStyleSheet("font-size: 32px;")
            header_box.addWidget(icon_lbl)

            header_text = QVBoxLayout()
            header_text.setSpacing(2)
            title = QLabel("إضافة جهاز هاتف جديد بالسيريال (IMEI)")
            title.setStyleSheet("font-size: 18px; font-weight: bold; color: #0F172A;")
            subtitle = QLabel("امسح بالباركود أو اكتب أرقام IMEI 1 و IMEI 2 لتتبع الجهاز والضمان")
            subtitle.setStyleSheet("font-size: 12px; color: #64748B;")
            header_text.addWidget(title)
            header_text.addWidget(subtitle)
            header_box.addLayout(header_text)
            header_box.addStretch()

            main_layout.addLayout(header_box)

            # ─── Group 1: اختيار الموديل ───
            grp_model = QGroupBox("📋 1. نوع وموديل الهاتف")
            grid_model = QGridLayout(grp_model)
            grid_model.setHorizontalSpacing(14)
            grid_model.setVerticalSpacing(10)

            lbl_prod = QLabel("موديل الهاتف المصرح بالمخزن: *")
            lbl_prod.setStyleSheet("font-weight: 600;")
            self.product_combo = QComboBox()
            self.product_combo.setFixedHeight(40)
            grid_model.addWidget(lbl_prod, 0, 0)
            grid_model.addWidget(self.product_combo, 1, 0)

            main_layout.addWidget(grp_model)

            # ─── Group 2: أرقام السيريال ───
            grp_imei = QGroupBox("🔍 2. أرقام السيريال (IMEI)")
            grid_imei = QGridLayout(grp_imei)
            grid_imei.setHorizontalSpacing(14)
            grid_imei.setVerticalSpacing(10)

            lbl_i1 = QLabel("رقم IMEI 1 (الشريحة الأولى): *")
            lbl_i1.setStyleSheet("font-weight: 600; color: #0284C7;")
            self.imei1_edit = QLineEdit()
            self.imei1_edit.setFixedHeight(40)
            self.imei1_edit.setPlaceholderText("15 رقماً (امسح الباركود على العلبة)")

            lbl_i2 = QLabel("رقم IMEI 2 (الشريحة الثانية - اختياري):")
            lbl_i2.setStyleSheet("font-weight: 600;")
            self.imei2_edit = QLineEdit()
            self.imei2_edit.setFixedHeight(40)
            self.imei2_edit.setPlaceholderText("اختياري إن وجد")

            grid_imei.addWidget(lbl_i1, 0, 0)
            grid_imei.addWidget(lbl_i2, 0, 1)
            grid_imei.addWidget(self.imei1_edit, 1, 0)
            grid_imei.addWidget(self.imei2_edit, 1, 1)

            main_layout.addWidget(grp_imei)

            # ─── Group 3: الحالة والتكلفة ───
            grp_cost = QGroupBox("💰 3. الحالة الفنية وتكلفة الشراء")
            grid_cost = QGridLayout(grp_cost)
            grid_cost.setHorizontalSpacing(14)
            grid_cost.setVerticalSpacing(10)

            lbl_cond = QLabel("حالة الجهاز الفنية:")
            lbl_cond.setStyleSheet("font-weight: 600;")
            self.condition_combo = QComboBox()
            self.condition_combo.setFixedHeight(40)
            self.condition_combo.addItem("✨ جديد بالكرتونة", "new")
            self.condition_combo.addItem("📦 مستعمل بحالة ممتازة", "used")

            lbl_cost = QLabel("سعر الشراء / التكلفة (ج.م):")
            lbl_cost.setStyleSheet("font-weight: 600;")
            self.cost_edit = QLineEdit()
            self.cost_edit.setFixedHeight(40)
            self.cost_edit.setPlaceholderText("0.00 ج.م")
            self.cost_edit.setValidator(QDoubleValidator(0.0, 9999999.0, 2))

            lbl_extra = QLabel("تكاليف إضافية (صيانة/إكسسوار):")
            lbl_extra.setStyleSheet("font-weight: 600;")
            self.extra_cost_edit = QLineEdit("0")
            self.extra_cost_edit.setFixedHeight(40)
            self.extra_cost_edit.setPlaceholderText("0.00 ج.م")
            self.extra_cost_edit.setValidator(QDoubleValidator(0.0, 9999999.0, 2))

            grid_cost.addWidget(lbl_cond, 0, 0)
            grid_cost.addWidget(lbl_cost, 0, 1)
            grid_cost.addWidget(lbl_extra, 0, 2)

            grid_cost.addWidget(self.condition_combo, 1, 0)
            grid_cost.addWidget(self.cost_edit, 1, 1)
            grid_cost.addWidget(self.extra_cost_edit, 1, 2)

            lbl_notes = QLabel("ملاحظات إضافية عن الجهاز:")
            lbl_notes.setStyleSheet("font-weight: 600;")
            self.notes_edit = QLineEdit()
            self.notes_edit.setFixedHeight(40)
            self.notes_edit.setPlaceholderText("مثال: اللون أزرق، بطارية 95%، معه الشاحن الأصلي...")
            grid_cost.addWidget(lbl_notes, 2, 0, 1, 3)
            grid_cost.addWidget(self.notes_edit, 3, 0, 1, 3)

            main_layout.addWidget(grp_cost)

            # Load products after all widgets are initialized
            self._load_products()

            # Action Buttons
            btn_layout = QHBoxLayout()
            btn_layout.setSpacing(12)
            btn_layout.addStretch()

            btn_cancel = QPushButton("إلغاء الأمر")
            btn_cancel.setFixedHeight(44)
            btn_cancel.setMinimumWidth(120)
            btn_cancel.setStyleSheet("""
                QPushButton {
                    background-color: #F1F5F9;
                    color: #475569;
                    border: 1px solid #CBD5E1;
                    border-radius: 8px;
                    font-weight: 600;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #E2E8F0;
                    color: #0F172A;
                }
            """)
            btn_cancel.clicked.connect(self.reject)

            btn_save = QPushButton("💾  تسجيل الجهاز في المخزن")
            btn_save.setObjectName("PrimaryBtn")
            btn_save.setFixedHeight(44)
            btn_save.setMinimumWidth(220)
            btn_save.setStyleSheet("""
                QPushButton#PrimaryBtn {
                    background-color: #2563EB;
                    color: #FFFFFF;
                    border: none;
                    border-radius: 8px;
                    font-weight: bold;
                    font-size: 14px;
                    padding: 0 20px;
                }
                QPushButton#PrimaryBtn:hover {
                    background-color: #1D4ED8;
                }
                QPushButton#PrimaryBtn:pressed {
                    background-color: #1E40AF;
                }
            """)
            btn_save.clicked.connect(self._save)

            btn_layout.addWidget(btn_cancel)
            btn_layout.addWidget(btn_save)
            main_layout.addLayout(btn_layout)

        def _load_products(self):
            self.product_combo.clear()
            products = self.session.query(Product).filter(
                Product.track_imei == True, Product.is_active == True
            ).order_by(Product.name).all()
            self._products = products
            for p in products:
                self.product_combo.addItem(f"📱 {p.name}", p)
            if products:
                # Pre-fill cost price from product default
                self.cost_edit.setText(piasters_to_input(p.cost_price))

        def _save(self):
            if not self._products:
                QMessageBox.warning(self, "تنبيه", "لا توجد هواتف مسجلة. أضف صنف هاتف أولاً.")
                return

            product = self.product_combo.currentData()
            imei1 = self.imei1_edit.text().strip()
            if not imei1:
                QMessageBox.warning(self, "تنبيه مطلوب", "رقم IMEI 1 مطلوب لتسجيل الجهاز")
                self.imei1_edit.setFocus()
                return

            cost_str = self.cost_edit.text().strip() or "0"
            try:
                cost_egp = Decimal(cost_str)
            except Exception:
                cost_egp = Decimal("0")

            extra_str = self.extra_cost_edit.text().strip() or "0"
            try:
                extra_egp = Decimal(extra_str)
            except Exception:
                extra_egp = Decimal("0")

            device_data = [{
                "imei1": imei1,
                "imei2": self.imei2_edit.text().strip() or None,
                "condition": self.condition_combo.currentData(),
                "purchase_cost": egp_to_piasters(cost_egp),
                "extra_cost": egp_to_piasters(extra_egp),
                "notes": self.notes_edit.text().strip() or None,
            }]

            try:
                inventory_service.add_devices(self.session, self.user, product, device_data)
                self.session.commit()
                self.accept()
            except inventory_service.DuplicateIMEI as e:
                QMessageBox.critical(self, "خطأ تكرار السيريال", str(e))
            except PermissionDenied as e:
                QMessageBox.critical(self, "خطأ في الصلاحية", str(e))
            except Exception as e:
                self.session.rollback()
                QMessageBox.critical(self, "خطأ", str(e))
