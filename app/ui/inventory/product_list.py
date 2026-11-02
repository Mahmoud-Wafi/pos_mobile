"""Modern Product List widget with instant search, filters, badges, and clean dialogs."""
from __future__ import annotations

from decimal import Decimal

try:
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
        QTableWidgetItem, QHeaderView, QDialog, QLineEdit,
        QComboBox, QCheckBox, QMessageBox, QLabel, QFrame,
        QGridLayout, QGroupBox,
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFont, QDoubleValidator, QIntValidator
    HAS_QT = True
except ImportError:
    HAS_QT = False

if HAS_QT:
    from app.services import inventory_service
    from app.core.money import format_money, egp_to_piasters, piasters_to_egp
    from app.core.permissions import PermissionDenied

    HEADERS = ["#", "اسم المنتج", "النوع", "الباركود", "سعر البيع", "الكمية بالمخزن", "الحد الأدنى", "تتبع IMEI", "الحالة"]

    class ProductListWidget(QWidget):
        def __init__(self, session, user, parent=None):
            super().__init__(parent)
            self.session = session
            self.user = user
            self._all_products = []
            self._build_ui()
            self.load_data()

        def _build_ui(self):
            layout = QVBoxLayout(self)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.setSpacing(12)

            # Top Control Bar
            bar = QHBoxLayout()
            bar.setSpacing(10)

            # Search Input
            self.search_edit = QLineEdit()
            self.search_edit.setPlaceholderText("🔍 ابحث باسم المنتج أو الباركود...")
            self.search_edit.setMinimumWidth(300)
            self.search_edit.setFixedHeight(40)
            self.search_edit.textChanged.connect(self._filter_products)
            bar.addWidget(self.search_edit)

            # Type Filter
            self.filter_type = QComboBox()
            self.filter_type.setFixedHeight(40)
            self.filter_type.addItem("جميع الأنواع", "all")
            self.filter_type.addItem("📱 هواتف فقط", "phone")
            self.filter_type.addItem("🎧 إكسسوارات فقط", "accessory")
            self.filter_type.addItem("💳 كروت شحن فقط", "card")
            self.filter_type.currentIndexChanged.connect(self._filter_products)
            bar.addWidget(self.filter_type)

            bar.addStretch()

            # Action Buttons
            self.btn_refresh = QPushButton("🔄 تحديث")
            self.btn_refresh.setFixedHeight(40)
            self.btn_refresh.clicked.connect(self.load_data)
            bar.addWidget(self.btn_refresh)

            self.btn_add = QPushButton("➕ إضافة منتج جديد")
            self.btn_add.setObjectName("PrimaryBtn")
            self.btn_add.setFixedHeight(40)
            self.btn_add.clicked.connect(self._add_product)
            bar.addWidget(self.btn_add)

            layout.addLayout(bar)

            # Table Card
            self.table = QTableWidget()
            self.table.setColumnCount(len(HEADERS))
            self.table.setHorizontalHeaderLabels(HEADERS)
            self.table.verticalHeader().setVisible(False)
            self.table.verticalHeader().setDefaultSectionSize(46)
            self.table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.table.setSelectionBehavior(QTableWidget.SelectRows)
            self.table.setAlternatingRowColors(True)
            self.table.setShowGrid(True)

            # Column resize policies
            header = self.table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.Fixed); self.table.setColumnWidth(0, 50)   # ID
            header.setSectionResizeMode(1, QHeaderView.Stretch)                                    # Name (Wide)
            header.setSectionResizeMode(2, QHeaderView.Fixed); self.table.setColumnWidth(2, 120)  # Type
            header.setSectionResizeMode(3, QHeaderView.Fixed); self.table.setColumnWidth(3, 160)  # Barcode
            header.setSectionResizeMode(4, QHeaderView.Fixed); self.table.setColumnWidth(4, 150)  # Price
            header.setSectionResizeMode(5, QHeaderView.Fixed); self.table.setColumnWidth(5, 130)  # Stock
            header.setSectionResizeMode(6, QHeaderView.Fixed); self.table.setColumnWidth(6, 100)  # Min
            header.setSectionResizeMode(7, QHeaderView.Fixed); self.table.setColumnWidth(7, 100)  # IMEI
            header.setSectionResizeMode(8, QHeaderView.Fixed); self.table.setColumnWidth(8, 90)   # Status

            layout.addWidget(self.table)

            # Stats summary footer
            self.footer_label = QLabel()
            self.footer_label.setStyleSheet("color: #64748B; font-weight: 600; font-size: 13px; padding-top: 4px;")
            layout.addWidget(self.footer_label)

        def load_data(self):
            self.session.expire_all()
            self._all_products = inventory_service.get_all_products(self.session, active_only=False)
            self._filter_products()

        def _filter_products(self):
            search_text = self.search_edit.text().strip().lower()
            selected_type = self.filter_type.currentData()

            filtered = []
            for p in self._all_products:
                if selected_type != "all" and p.type != selected_type:
                    continue
                if search_text:
                    name_match = search_text in p.name.lower()
                    barcode_match = p.barcode and search_text in p.barcode.lower()
                    if not (name_match or barcode_match):
                        continue
                filtered.append(p)

            self._populate_table(filtered)

        def _populate_table(self, products):
            self.table.setRowCount(len(products))

            total_items = 0
            for row, p in enumerate(products):
                qty = p.current_quantity()
                total_items += qty
                is_out_of_stock = qty == 0
                is_low_stock = qty <= p.min_stock and not is_out_of_stock

                type_ar = {"phone": "📱 هاتف", "accessory": "🎧 إكسسوار", "card": "💳 كارت"}.get(p.type, p.type)

                cols = [
                    (str(p.id), Qt.AlignCenter, None, None),
                    (p.name, Qt.AlignRight | Qt.AlignVCenter, None, True),
                    (type_ar, Qt.AlignCenter, None, None),
                    (p.barcode or "—", Qt.AlignCenter, "#64748B", None),
                    (format_money(p.sale_price), Qt.AlignCenter, "#0369A1", True),
                    (str(qty), Qt.AlignCenter, None, True),
                    (str(p.min_stock), Qt.AlignCenter, "#64748B", None),
                    ("نعم" if p.track_imei else "لا", Qt.AlignCenter, None, None),
                    ("نشط" if p.is_active else "متوقف", Qt.AlignCenter, "#059669" if p.is_active else "#94A3B8", True),
                ]

                for col, (text, align, fg_color, is_bold) in enumerate(cols):
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(align)
                    item.setForeground(QColor(fg_color or "#0F172A"))
                    if is_bold:
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)

                    # Highlight Stock cell
                    if col == 5:
                        if is_out_of_stock:
                            item.setBackground(QColor("#FEE2E2"))
                            item.setForeground(QColor("#991B1B"))
                        elif is_low_stock:
                            item.setBackground(QColor("#FEF3C7"))
                            item.setForeground(QColor("#92400E"))
                        else:
                            item.setBackground(QColor("#ECFDF5"))
                            item.setForeground(QColor("#065F46"))

                    self.table.setItem(row, col, item)

            self.footer_label.setText(f"إجمالي الأصناف المعروضة: {len(products)} صنف | مجموع الوحدات: {total_items} قطعة")

        def _add_product(self):
            dlg = ProductDialog(self.session, self.user, parent=self)
            if dlg.exec() == QDialog.Accepted:
                self.load_data()


    class ProductDialog(QDialog):
        """Beautiful, professional dialog for adding products."""

        def __init__(self, session, user, parent=None):
            super().__init__(parent)
            self.session = session
            self.user = user
            self.setWindowTitle("إضافة صنف جديد")
            self.setMinimumWidth(680)
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

            # Header Banner
            header_box = QHBoxLayout()
            icon_lbl = QLabel("📦")
            icon_lbl.setStyleSheet("font-size: 32px;")
            header_box.addWidget(icon_lbl)

            header_text = QVBoxLayout()
            header_text.setSpacing(2)
            title = QLabel("إضافة صنف جديد إلى المخزون")
            title.setStyleSheet("font-size: 18px; font-weight: bold; color: #0F172A;")
            subtitle = QLabel("أدخل تفاصيل المنتج بدقة لتنظيم المبيعات وحساب الأرباح والضمان")
            subtitle.setStyleSheet("font-size: 12px; color: #64748B;")
            header_text.addWidget(title)
            header_text.addWidget(subtitle)
            header_box.addLayout(header_text)
            header_box.addStretch()

            main_layout.addLayout(header_box)

            # ─── Group 1: الأساسيات ───
            grp_basic = QGroupBox("📋 1. البيانات الأساسية للصنف")
            grid_basic = QGridLayout(grp_basic)
            grid_basic.setHorizontalSpacing(14)
            grid_basic.setVerticalSpacing(10)

            # Name (Full width)
            lbl_name = QLabel("اسم المنتج / الموديل: *")
            lbl_name.setStyleSheet("font-weight: 600;")
            self.name_edit = QLineEdit()
            self.name_edit.setFixedHeight(40)
            self.name_edit.setPlaceholderText("مثال: سامسونج جالكسي S24 ألترا 256 جيجا أو شاحن سريع 30W")
            grid_basic.addWidget(lbl_name, 0, 0, 1, 2)
            grid_basic.addWidget(self.name_edit, 1, 0, 1, 2)

            # Type & Barcode
            lbl_type = QLabel("نوع الصنف: *")
            lbl_type.setStyleSheet("font-weight: 600;")
            self.type_combo = QComboBox()
            self.type_combo.setFixedHeight(40)
            self.type_combo.addItem("🎧 إكسسوارات وملحقات", "accessory")
            self.type_combo.addItem("📱 هاتف محمول (تتبع IMEI)", "phone")
            self.type_combo.addItem("💳 كروت شحن وباقات", "card")

            lbl_barcode = QLabel("رقم الباركود (Barcode):")
            lbl_barcode.setStyleSheet("font-weight: 600;")
            self.barcode_edit = QLineEdit()
            self.barcode_edit.setFixedHeight(40)
            self.barcode_edit.setPlaceholderText("امسح بالباركود أو اتركه فارغاً")

            grid_basic.addWidget(lbl_type, 2, 0)
            grid_basic.addWidget(lbl_barcode, 2, 1)
            grid_basic.addWidget(self.type_combo, 3, 0)
            grid_basic.addWidget(self.barcode_edit, 3, 1)

            main_layout.addWidget(grp_basic)

            # ─── Group 2: الأسعار والتسعير ───
            grp_price = QGroupBox("💰 2. الأسعار والتكلفة (بالجنيه المصري)")
            grid_price = QGridLayout(grp_price)
            grid_price.setHorizontalSpacing(14)
            grid_price.setVerticalSpacing(10)

            lbl_sale = QLabel("سعر البيع الافتراضي: *")
            lbl_sale.setStyleSheet("font-weight: 600; color: #0284C7;")
            self.sale_edit = QLineEdit()
            self.sale_edit.setFixedHeight(40)
            self.sale_edit.setPlaceholderText("0.00 ج.م")
            self.sale_edit.setValidator(QDoubleValidator(0.0, 9999999.0, 2))

            lbl_cost = QLabel("سعر التكلفة (الشراء):")
            lbl_cost.setStyleSheet("font-weight: 600; color: #475569;")
            self.cost_edit = QLineEdit()
            self.cost_edit.setFixedHeight(40)
            self.cost_edit.setPlaceholderText("0.00 ج.م")
            self.cost_edit.setValidator(QDoubleValidator(0.0, 9999999.0, 2))

            lbl_min_price = QLabel("أقل سعر بيع مسموح به:")
            lbl_min_price.setStyleSheet("font-weight: 600; color: #475569;")
            self.min_price_edit = QLineEdit()
            self.min_price_edit.setFixedHeight(40)
            self.min_price_edit.setPlaceholderText("0.00 ج.م")
            self.min_price_edit.setValidator(QDoubleValidator(0.0, 9999999.0, 2))

            grid_price.addWidget(lbl_sale, 0, 0)
            grid_price.addWidget(lbl_cost, 0, 1)
            grid_price.addWidget(lbl_min_price, 0, 2)

            grid_price.addWidget(self.sale_edit, 1, 0)
            grid_price.addWidget(self.cost_edit, 1, 1)
            grid_price.addWidget(self.min_price_edit, 1, 2)

            main_layout.addWidget(grp_price)

            # ─── Group 3: المخزون والضمان ───
            grp_stock = QGroupBox("📦 3. المخزون وتتبع السيريال والضمان")
            grid_stock = QGridLayout(grp_stock)
            grid_stock.setHorizontalSpacing(14)
            grid_stock.setVerticalSpacing(10)

            lbl_min_stock = QLabel("تنبيه الحد الأدنى للمخزون:")
            lbl_min_stock.setStyleSheet("font-weight: 600;")
            self.min_stock_edit = QLineEdit("3")
            self.min_stock_edit.setFixedHeight(40)
            self.min_stock_edit.setValidator(QIntValidator(0, 9999))

            lbl_warranty = QLabel("فترة الضمان (بالأيام):")
            lbl_warranty.setStyleSheet("font-weight: 600;")
            self.warranty_edit = QLineEdit("0")
            self.warranty_edit.setFixedHeight(40)
            self.warranty_edit.setValidator(QIntValidator(0, 3650))

            grid_stock.addWidget(lbl_min_stock, 0, 0)
            grid_stock.addWidget(lbl_warranty, 0, 1)
            grid_stock.addWidget(self.min_stock_edit, 1, 0)
            grid_stock.addWidget(self.warranty_edit, 1, 1)

            # IMEI Tracking Card
            imei_card = QFrame()
            imei_card.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 10px;")
            imei_box = QHBoxLayout(imei_card)
            imei_box.setContentsMargins(8, 8, 8, 8)
            imei_box.setSpacing(10)

            self.track_imei_check = QCheckBox("تتبع أجهزة هذا الصنف برقم السيريال (IMEI)")
            self.track_imei_check.setStyleSheet("font-weight: bold; font-size: 13px; color: #1E293B;")
            imei_hint = QLabel("(إلزامي للهواتف — سيتطلب إدخال رقم IMEI عند الشراء والبيع والضمان)")
            imei_hint.setStyleSheet("color: #64748B; font-size: 11px;")

            imei_box.addWidget(self.track_imei_check)
            imei_box.addWidget(imei_hint)
            imei_box.addStretch()

            # Auto-check IMEI when type is phone
            self.type_combo.currentIndexChanged.connect(self._on_type_changed)

            grid_stock.addWidget(imei_card, 2, 0, 1, 2)
            main_layout.addWidget(grp_stock)

            # ─── Buttons ───
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

            btn_save = QPushButton("💾  حفظ الصنف في المخزون")
            btn_save.setObjectName("PrimaryBtn")
            btn_save.setFixedHeight(44)
            btn_save.setMinimumWidth(210)
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

        def _on_type_changed(self):
            is_phone = self.type_combo.currentData() == "phone"
            self.track_imei_check.setChecked(is_phone)
            if is_phone and self.warranty_edit.text() in ("0", ""):
                self.warranty_edit.setText("365")

        def _save(self):
            name = self.name_edit.text().strip()
            if not name:
                QMessageBox.warning(self, "تنبيه مطلوب", "يرجى كتابة اسم المنتج أو الموديل")
                self.name_edit.setFocus()
                return

            sale_str = self.sale_edit.text().strip() or "0"
            try:
                sale_egp = Decimal(sale_str)
            except Exception:
                QMessageBox.warning(self, "خطأ في السعر", "يرجى إدخال سعر بيع صحيح")
                self.sale_edit.setFocus()
                return

            cost_str = self.cost_edit.text().strip() or "0"
            try:
                cost_egp = Decimal(cost_str)
            except Exception:
                cost_egp = Decimal("0")

            min_p_str = self.min_price_edit.text().strip() or str(sale_egp)
            try:
                min_p_egp = Decimal(min_p_str)
            except Exception:
                min_p_egp = sale_egp

            min_stock = int(self.min_stock_edit.text().strip() or "0")
            warranty_days = int(self.warranty_edit.text().strip() or "0")

            data = {
                "name": name,
                "barcode": self.barcode_edit.text().strip() or None,
                "type": self.type_combo.currentData(),
                "cost_price": egp_to_piasters(cost_egp),
                "sale_price": egp_to_piasters(sale_egp),
                "min_price": egp_to_piasters(min_p_egp),
                "min_stock": min_stock,
                "warranty_days": warranty_days,
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
