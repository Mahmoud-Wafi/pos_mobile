"""Modern Product List widget with instant search, filters, badges, and clean dialogs."""
from __future__ import annotations
from app.core.permissions import PERM_COST_VIEW, PERM_INVENTORY_ADJUST
from app.i18n import ar
from app.ui.components.numeric import set_int_validator, set_money_validator

import re
from decimal import Decimal
from app.ui.components import show_error, show_toast
from app.ui.design.style import set_prop, style_label, variant
from app.ui.design import icons
from app.ui.design.tokens import COLORS

try:
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
        QTableWidgetItem, QHeaderView, QDialog, QLineEdit,
        QComboBox, QCheckBox, QMessageBox, QLabel, QFrame,
        QGridLayout, QGroupBox,
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFont
    HAS_QT = True
except ImportError:
    HAS_QT = False

if HAS_QT:
    from app.services import inventory_service
    from app.core.money import normalize_number_text, format_money, egp_to_piasters, parse_int_input, piasters_to_egp
    from app.core.permissions import PermissionDenied

    HEADERS = ["#", ar.LOW_STOCK_WIDGET_1AB391, ar.LOW_STOCK_WIDGET_A70B01, ar.PRODUCT_LIST_95520D, ar.PRODUCT_LIST_13E684, ar.PRODUCT_LIST_BF9877, ar.DASH_MIN, ar.PRODUCT_LIST_6D7BD8, ar.USERS_STATUS]

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
            self.search_edit.setPlaceholderText(ar.PRODUCT_LIST_9ECD98)
            self.search_edit.setMinimumWidth(300)
            self.search_edit.setFixedHeight(40)
            self.search_edit.textChanged.connect(self._filter_products)
            bar.addWidget(self.search_edit)

            # Type Filter
            self.filter_type = QComboBox()
            self.filter_type.setFixedHeight(40)
            self.filter_type.addItem(ar.PRODUCT_LIST_B327CE, "all")
            self.filter_type.addItem(ar.PRODUCT_LIST_8D203E, "phone")
            self.filter_type.addItem(ar.PRODUCT_LIST_C6E1CF, "accessory")
            self.filter_type.addItem(ar.PRODUCT_LIST_06C8C6, "card")
            self.filter_type.currentIndexChanged.connect(self._filter_products)
            bar.addWidget(self.filter_type)

            bar.addStretch()

            # Action buttons live on their own row so nothing is clipped on 1366px screens
            bar2 = QHBoxLayout()
            bar2.setSpacing(10)
            self.btn_refresh = QPushButton(ar.REFRESH)
            self.btn_refresh.setFixedHeight(40)
            self.btn_refresh.clicked.connect(self.load_data)
            bar2.addWidget(self.btn_refresh)

            self.btn_import = QPushButton(ar.IMPORT_BUTTON)
            self.btn_import.setMinimumHeight(40)
            self.btn_import.clicked.connect(self._import_excel)
            bar2.addWidget(self.btn_import)
            self.btn_export = QPushButton(ar.EXPORT_BUTTON)
            self.btn_export.setMinimumHeight(40)
            self.btn_export.clicked.connect(self._export_excel)
            bar2.addWidget(self.btn_export)
            self.btn_edit = QPushButton(ar.INV_BTN_EDIT)
            self.btn_edit.setMinimumHeight(40)
            self.btn_edit.clicked.connect(self._edit_product)
            bar2.addWidget(self.btn_edit)
            self.btn_toggle = QPushButton(f"{ar.INV_BTN_DEACTIVATE} / {ar.INV_BTN_ACTIVATE}")
            self.btn_toggle.setMinimumHeight(40)
            self.btn_toggle.clicked.connect(self._toggle_active)
            bar2.addWidget(self.btn_toggle)
            self.btn_delete = QPushButton(ar.INV_BTN_DELETE)
            self.btn_delete.setMinimumHeight(40)
            variant(self.btn_delete, "danger")
            self.btn_delete.clicked.connect(self._delete_product)
            bar2.addWidget(self.btn_delete)
            self.btn_labels = QPushButton(ar.LABEL_PRINT)
            self.btn_labels.setMinimumHeight(40)
            self.btn_labels.clicked.connect(self._print_labels)
            bar2.addWidget(self.btn_labels)
            bar2.addStretch()

            self.btn_add = QPushButton(ar.PRODUCT_LIST_B56A2A)
            self.btn_add.setObjectName("PrimaryBtn")
            self.btn_add.setFixedHeight(40)
            self.btn_add.clicked.connect(self._add_product)
            bar.addWidget(self.btn_add)

            layout.addLayout(bar)
            layout.addLayout(bar2)

            # Table Card
            self.table = QTableWidget()
            self.table.setColumnCount(len(HEADERS))
            self.table.setHorizontalHeaderLabels(HEADERS)
            self.table.verticalHeader().setVisible(False)
            self.table.verticalHeader().setDefaultSectionSize(46)
            self.table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.table.doubleClicked.connect(self._edit_product)
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
            style_label(self.footer_label, size="body", tone="muted", bold=True)
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
                    barcode_match = any(search_text in b.lower() for b in p.all_barcodes())
                    if not (name_match or barcode_match):
                        continue
                filtered.append(p)

            self._populate_table(filtered)

        def _populate_table(self, products):
            self._shown = list(products)
            self.table.setRowCount(len(products))

            total_items = 0
            for row, p in enumerate(products):
                qty = p.current_quantity()
                total_items += qty
                is_out_of_stock = qty == 0
                is_low_stock = qty <= p.min_stock and not is_out_of_stock

                type_ar = {"phone": ar.LOW_STOCK_WIDGET_B0D973, "accessory": ar.LOW_STOCK_WIDGET_99E818, "card": ar.LOW_STOCK_WIDGET_99AFB1}.get(p.type, p.type)

                cols = [
                    (str(p.id), Qt.AlignCenter, None, None),
                    (p.name, Qt.AlignRight | Qt.AlignVCenter, None, True),
                    (type_ar, Qt.AlignCenter, None, None),
                    (p.barcode or "—", Qt.AlignCenter, "#5B6683", None),
                    (format_money(p.sale_price), Qt.AlignCenter, "#0369A1", True),
                    (str(qty), Qt.AlignCenter, None, True),
                    (str(p.min_stock), Qt.AlignCenter, "#5B6683", None),
                    (ar.YES if p.track_imei else ar.NO, Qt.AlignCenter, None, None),
                    (ar.PRODUCT_LIST_8CAAF9 if p.is_active else ar.PRODUCT_LIST_2E7AFF, Qt.AlignCenter, "#0B7A4B" if p.is_active else "#94A3B8", True),
                ]

                for col, (text, align, fg_color, is_bold) in enumerate(cols):
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(align)
                    item.setForeground(QColor(fg_color or "#0E1630"))
                    if is_bold:
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)

                    # Highlight Stock cell
                    if col == 5:
                        if is_out_of_stock:
                            item.setBackground(QColor("#FDECEC"))
                            item.setForeground(QColor("#A91F1F"))
                        elif is_low_stock:
                            item.setBackground(QColor("#FFF4E5"))
                            item.setForeground(QColor("#9A5B00"))
                        else:
                            item.setBackground(QColor("#E3F6EE"))
                            item.setForeground(QColor("#0B7A4B"))

                    self.table.setItem(row, col, item)

            self.footer_label.setText(f"إجمالي الأصناف المعروضة: {len(products)} صنف | مجموع الوحدات: {total_items} قطعة")

        def _current_product(self):
            row = self.table.currentRow()
            shown = getattr(self, "_shown", [])
            if 0 <= row < len(shown):
                return shown[row]
            show_error(self, message=ar.INV_SELECT_ROW)
            return None

        def _edit_product(self, *_):
            p = self._current_product()
            if p is not None and ProductDialog(self.session, self.user, product=p, parent=self).exec():
                show_toast(self, ar.INV_SAVED)
                self.load_data()

        def _toggle_active(self):
            p = self._current_product()
            if p is None:
                return
            try:
                inventory_service.update_product(self.session, self.user, p.id, {"is_active": not p.is_active})
                self.session.commit()
            except Exception as exc:
                self.session.rollback()
                show_error(self, exc)
                return
            self.load_data()

        def _delete_product(self):
            from app.ui.components import confirm
            p = self._current_product()
            if p is None or not confirm(self, ar.INV_BTN_DELETE, ar.INV_CONFIRM_DELETE_PRODUCT,
                                        ar.INV_BTN_DELETE, destructive=True):
                return
            try:
                inventory_service.delete_product(self.session, self.user, p.id)
                self.session.commit()
            except inventory_service.InventoryError as exc:
                self.session.rollback()
                if str(exc) == ar.PRODUCT_HAS_HISTORY and confirm(self, ar.INV_BTN_DEACTIVATE,
                                                                  ar.INV_OFFER_DEACTIVATE, ar.INV_BTN_DEACTIVATE):
                    self._toggle_active_for(p)
                else:
                    show_error(self, exc)
                return
            except Exception as exc:
                self.session.rollback()
                show_error(self, exc)
                return
            show_toast(self, ar.INV_DELETED)
            self.load_data()

        def _toggle_active_for(self, p):
            try:
                inventory_service.update_product(self.session, self.user, p.id, {"is_active": False})
                self.session.commit()
            except Exception as exc:
                self.session.rollback()
                show_error(self, exc)
                return
            self.load_data()

        def _print_labels(self):
            from PySide6.QtWidgets import QFileDialog, QInputDialog
            from app.services import label_service
            row = self.table.currentRow()
            shown = getattr(self, "_shown", [])
            if not 0 <= row < len(shown):
                show_error(self, message=ar.LABEL_NOTHING)
                return
            copies, ok = QInputDialog.getInt(self, ar.LABEL_PRINT, ar.LABEL_COPIES_PROMPT, 1, 1, 500)
            if not ok:
                return
            try:
                specs = label_service.product_specs(self.session, self.user, [(shown[row], copies)])
            except Exception as exc:
                show_error(self, exc)
                return
            from app.ui import hardware
            hardware.output_labels(self, self.session, specs)

        def _import_excel(self):
            from app.ui.inventory.import_wizard import ImportWizard
            if ImportWizard(self.session, self.user, parent=self).exec():
                self.load_data()

        def _export_excel(self):
            from PySide6.QtWidgets import QFileDialog
            from app.services import import_export_service as ie
            from app.ui.components import show_error, show_toast
            dest, _ = QFileDialog.getSaveFileName(self, ar.EXPORT_BUTTON, "products.xlsx", "Excel (*.xlsx);;CSV (*.csv)")
            if dest:
                try:
                    ie.export_products(self.session, self.user, dest)
                    show_toast(self, ar.EXPORT_DONE)
                except Exception as exc:
                    show_error(self, exc)

        def _add_product(self):
            dlg = ProductDialog(self.session, self.user, parent=self)
            if dlg.exec() == QDialog.Accepted:
                self.load_data()


    class ProductDialog(QDialog):
        """Beautiful, professional dialog for adding products."""

        def __init__(self, session, user, product=None, parent=None, allow_opening=True):
            super().__init__(parent)
            self.session = session
            self.user = user
            self.product = product
            self.created_product = None
            self._allow_opening = allow_opening  # False when created from a purchase invoice (the invoice adds the stock)
            self.setWindowTitle(ar.INV_EDIT_PRODUCT if product else ar.PRODUCT_LIST_BD0915)
            self.setMinimumWidth(680)

            self._build_ui()
            self._can_cost = PERM_COST_VIEW in user.permission_codes()
            if not self._can_cost:
                self.cost_edit.setVisible(False)
                self.lbl_cost.setVisible(False)
            if product is not None:
                self._prefill(product)
            else:
                from app.services import inventory_service as _inv
                self.barcode_edit.setText(_inv.generate_barcode(self.session))  # auto code; can be replaced by a scan
            self._update_opening_visibility()

        def _prefill(self, p):
            from app.core.money import piasters_to_input
            from app.services import inventory_service as inv
            self.name_edit.setText(p.name)
            self.barcode_edit.setText(p.barcode or "")
            self.extra_edit.setText("، ".join(b.code for b in p.extra_barcodes))
            self.type_combo.blockSignals(True)
            self.type_combo.setCurrentIndex(max(0, self.type_combo.findData(p.type)))
            self.type_combo.blockSignals(False)
            self.sale_edit.setText(piasters_to_input(p.sale_price))
            self.cost_edit.setText(piasters_to_input(p.cost_price))
            self.min_price_edit.setText(piasters_to_input(p.min_price))
            self.min_stock_edit.setText(str(p.min_stock))
            self.warranty_edit.setText(str(p.warranty_days))
            self.track_imei_check.setChecked(p.track_imei)
            if inv.product_has_history(self.session, p):          # type / IMEI tracking are locked
                self.type_combo.setEnabled(False)
                self.track_imei_check.setEnabled(False)

        def _build_ui(self):
            main_layout = QVBoxLayout(self)
            main_layout.setContentsMargins(28, 24, 28, 24)
            main_layout.setSpacing(18)

            # Header Banner
            header_box = QHBoxLayout()
            icon_lbl = QLabel()
            icon_lbl.setPixmap(icons.pixmap("package", COLORS["primary"], 28))
            header_box.addWidget(icon_lbl)

            header_text = QVBoxLayout()
            header_text.setSpacing(2)
            title = QLabel(ar.PRODUCT_LIST_882542)
            style_label(title, size="h2", tone="text", bold=True)
            subtitle = QLabel(ar.PRODUCT_LIST_7A0F35)
            style_label(subtitle, size="caption", tone="muted")
            header_text.addWidget(title)
            header_text.addWidget(subtitle)
            header_box.addLayout(header_text)
            header_box.addStretch()

            main_layout.addLayout(header_box)

            # ─── Group 1: الأساسيات ───
            grp_basic = QGroupBox(ar.PRODUCT_LIST_D82C13)
            grid_basic = QGridLayout(grp_basic)
            grid_basic.setHorizontalSpacing(14)
            grid_basic.setVerticalSpacing(10)

            # Name (Full width)
            lbl_name = QLabel(ar.PRODUCT_LIST_8658FE)
            style_label(lbl_name, bold=True)
            self.name_edit = QLineEdit()
            self.name_edit.setFixedHeight(40)
            self.name_edit.setPlaceholderText(ar.PRODUCT_LIST_87C0D0)
            grid_basic.addWidget(lbl_name, 0, 0, 1, 2)
            grid_basic.addWidget(self.name_edit, 1, 0, 1, 2)

            # Type & Barcode
            self.barcode_note = QLabel("")
            style_label(self.barcode_note, size="caption", tone="danger")
            self.barcode_note.setVisible(False)
            lbl_extra = QLabel(ar.PRODUCT_EXTRA_BARCODES)
            style_label(lbl_extra, bold=True)
            self.extra_edit = QLineEdit()
            self.extra_edit.setFixedHeight(40)
            self.extra_edit.setPlaceholderText(ar.PRODUCT_EXTRA_BARCODES_HINT)
            lbl_type = QLabel(ar.PRODUCT_LIST_65F25B)
            style_label(lbl_type, bold=True)
            self.type_combo = QComboBox()
            self.type_combo.setFixedHeight(40)
            self.type_combo.addItem(ar.PRODUCT_LIST_837413, "accessory")
            self.type_combo.addItem(ar.PRODUCT_LIST_C052F8, "phone")
            self.type_combo.addItem(ar.PRODUCT_LIST_8E807B, "card")

            lbl_barcode = QLabel(ar.PRODUCT_LIST_0A94A3)
            style_label(lbl_barcode, bold=True)
            self.barcode_edit = QLineEdit()
            self.barcode_edit.setFixedHeight(40)
            self.barcode_edit.setPlaceholderText(ar.PRODUCT_LIST_5B6297)

            grid_basic.addWidget(lbl_type, 2, 0)
            grid_basic.addWidget(lbl_barcode, 2, 1)
            grid_basic.addWidget(self.type_combo, 3, 0)
            grid_basic.addWidget(self.barcode_edit, 3, 1)

            grid_basic.addWidget(self.barcode_note, 4, 0, 1, 2)
            grid_basic.addWidget(lbl_extra, 5, 0, 1, 2)
            grid_basic.addWidget(self.extra_edit, 6, 0, 1, 2)
            self.barcode_edit.editingFinished.connect(self._check_barcode)
            main_layout.addWidget(grp_basic)

            # ─── Group 2: الأسعار والتسعير ───
            grp_price = QGroupBox(ar.PRODUCT_LIST_B3B868)
            grid_price = QGridLayout(grp_price)
            grid_price.setHorizontalSpacing(14)
            grid_price.setVerticalSpacing(10)

            lbl_sale = QLabel(ar.PRODUCT_LIST_43CB56)
            style_label(lbl_sale, tone="info", bold=True)
            self.sale_edit = QLineEdit()
            self.sale_edit.setFixedHeight(40)
            self.sale_edit.setPlaceholderText(ar.DAILY_CLOSE_DIALOG_388B15)
            set_money_validator(self.sale_edit, 0.0, 9999999.0)

            lbl_cost = QLabel(ar.PRODUCT_LIST_30B579)
            style_label(lbl_cost, tone="muted", bold=True)
            self.lbl_cost = lbl_cost
            self.cost_edit = QLineEdit()
            self.cost_edit.setFixedHeight(40)
            self.cost_edit.setPlaceholderText(ar.DAILY_CLOSE_DIALOG_388B15)
            set_money_validator(self.cost_edit, 0.0, 9999999.0)

            lbl_min_price = QLabel(ar.PRODUCT_LIST_B5D903)
            style_label(lbl_min_price, tone="muted", bold=True)
            self.min_price_edit = QLineEdit()
            self.min_price_edit.setFixedHeight(40)
            self.min_price_edit.setPlaceholderText(ar.DAILY_CLOSE_DIALOG_388B15)
            set_money_validator(self.min_price_edit, 0.0, 9999999.0)

            grid_price.addWidget(lbl_sale, 0, 0)
            grid_price.addWidget(lbl_cost, 0, 1)
            grid_price.addWidget(lbl_min_price, 0, 2)

            grid_price.addWidget(self.sale_edit, 1, 0)
            grid_price.addWidget(self.cost_edit, 1, 1)
            grid_price.addWidget(self.min_price_edit, 1, 2)

            main_layout.addWidget(grp_price)

            # ─── Group 3: المخزون والضمان ───
            grp_stock = QGroupBox(ar.PRODUCT_LIST_D2D2B5)
            grid_stock = QGridLayout(grp_stock)
            grid_stock.setHorizontalSpacing(14)
            grid_stock.setVerticalSpacing(10)

            lbl_min_stock = QLabel(ar.PRODUCT_LIST_981D2F)
            style_label(lbl_min_stock, bold=True)
            self.min_stock_edit = QLineEdit("3")
            self.min_stock_edit.setFixedHeight(40)
            set_int_validator(self.min_stock_edit, 0, 9999)

            lbl_warranty = QLabel(ar.PRODUCT_LIST_79E153)
            style_label(lbl_warranty, bold=True)
            self.warranty_edit = QLineEdit("0")
            self.warranty_edit.setFixedHeight(40)
            set_int_validator(self.warranty_edit, 0, 3650)

            grid_stock.addWidget(lbl_min_stock, 0, 0)
            grid_stock.addWidget(lbl_warranty, 0, 1)
            grid_stock.addWidget(self.min_stock_edit, 1, 0)
            grid_stock.addWidget(self.warranty_edit, 1, 1)

            self.lbl_opening = QLabel(ar.PRODUCT_OPENING_QTY)
            style_label(self.lbl_opening, bold=True)
            self.opening_edit = QLineEdit("0")
            self.opening_edit.setFixedHeight(40)
            set_int_validator(self.opening_edit, 0, 999999)
            self.opening_hint = QLabel(ar.PRODUCT_OPENING_IMEI_HINT)
            style_label(self.opening_hint, size="caption", tone="muted")
            self.opening_hint.setWordWrap(True)
            grid_stock.addWidget(self.lbl_opening, 0, 2)
            grid_stock.addWidget(self.opening_edit, 1, 2)
            grid_stock.addWidget(self.opening_hint, 3, 0, 1, 3)

            # IMEI Tracking Card
            imei_card = QFrame()
            set_prop(imei_card, "card", True)
            imei_box = QHBoxLayout(imei_card)
            imei_box.setContentsMargins(8, 8, 8, 8)
            imei_box.setSpacing(10)

            self.track_imei_check = QCheckBox(ar.PRODUCT_LIST_3F80CE)
            style_label(self.track_imei_check, size="body", tone="text", bold=True)
            imei_hint = QLabel(ar.PRODUCT_LIST_55D646)
            style_label(imei_hint, size="caption", tone="muted")

            imei_box.addWidget(self.track_imei_check)
            imei_box.addWidget(imei_hint)
            imei_box.addStretch()

            # Auto-check IMEI when type is phone
            self.type_combo.currentIndexChanged.connect(self._on_type_changed)
            self.track_imei_check.toggled.connect(self._update_opening_visibility)

            grid_stock.addWidget(imei_card, 2, 0, 1, 2)
            main_layout.addWidget(grp_stock)

            # ─── Buttons ───
            btn_layout = QHBoxLayout()
            btn_layout.setSpacing(12)
            btn_layout.addStretch()

            btn_cancel = QPushButton(ar.DEVICE_LIST_69A551)
            btn_cancel.setFixedHeight(44)
            btn_cancel.setMinimumWidth(120)
            variant(btn_cancel, "secondary")
            btn_cancel.clicked.connect(self.reject)

            btn_save = QPushButton(ar.PRODUCT_LIST_374821)
            btn_save.setObjectName("PrimaryBtn")
            btn_save.setFixedHeight(44)
            btn_save.setMinimumWidth(210)
            variant(btn_save, "primary")
            btn_save.clicked.connect(self._save)

            btn_layout.addWidget(btn_cancel)
            btn_layout.addWidget(btn_save)
            main_layout.addLayout(btn_layout)

        def _check_barcode(self):
            """A scanned barcode that already belongs to a product: say so, and offer to open that product."""
            code = inventory_service.normalize_barcode(self.barcode_edit.text())
            self.barcode_edit.setText(code)
            owner = inventory_service.find_product_by_barcode(self.session, code) if code else None
            mine = self.product is not None and owner is not None and owner.id == self.product.id
            if owner is None or mine:
                self.barcode_note.setVisible(False)
                return
            self.barcode_note.setText(f"{ar.PRODUCT_BARCODE_OWNER}: {owner.name}")
            self.barcode_note.setVisible(True)
            if self.product is None:
                from app.ui.components import confirm
                if confirm(self, ar.INV_EDIT_PRODUCT, f"{ar.PRODUCT_BARCODE_OWNER}: {owner.name}\n{ar.PRODUCT_BARCODE_OPEN}",
                           ar.INV_BTN_EDIT):
                    self.product = owner
                    self.setWindowTitle(ar.INV_EDIT_PRODUCT)
                    self._prefill(owner)
                    self._update_opening_visibility()
                    self.barcode_note.setVisible(False)

        def _update_opening_visibility(self):
            """Opening stock only for new, non-IMEI products and only for people who may adjust stock."""
            can = (PERM_INVENTORY_ADJUST in self.user.permission_codes() and self.product is None
                   and self._allow_opening)
            imei = self.track_imei_check.isChecked()
            for w in (self.lbl_opening, self.opening_edit):
                w.setVisible(can and not imei)
            self.opening_hint.setVisible(self.product is None and imei and self._allow_opening)

        def _on_type_changed(self):
            is_phone = self.type_combo.currentData() == "phone"
            self.track_imei_check.setChecked(is_phone)
            if is_phone and self.warranty_edit.text() in ("0", ""):
                self.warranty_edit.setText("365")

        def _save(self):
            name = self.name_edit.text().strip()
            if not name:
                show_error(self, message=ar.PRODUCT_LIST_D5CBED)
                self.name_edit.setFocus()
                return

            sale_str = self.sale_edit.text().strip() or "0"
            try:
                sale_egp = Decimal(normalize_number_text(sale_str))
            except Exception:
                show_error(self, message=ar.PRODUCT_LIST_B3DA0C)
                self.sale_edit.setFocus()
                return

            cost_str = self.cost_edit.text().strip() or "0"
            try:
                cost_egp = Decimal(normalize_number_text(cost_str))
            except Exception:
                cost_egp = Decimal("0")

            min_p_str = self.min_price_edit.text().strip() or str(sale_egp)
            try:
                min_p_egp = Decimal(normalize_number_text(min_p_str))
            except Exception:
                min_p_egp = sale_egp

            min_stock = parse_int_input(self.min_stock_edit.text().strip(), 0)
            warranty_days = parse_int_input(self.warranty_edit.text().strip(), 0)

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
                "extra_barcodes": [c for c in re.split(r"[\s,،;]+", self.extra_edit.text()) if c],
            }

            try:
                if self.product is not None:
                    if not self._can_cost:
                        data.pop("cost_price")
                    inventory_service.update_product(self.session, self.user, self.product.id, data)
                else:
                    created = inventory_service.create_product(self.session, self.user, data)
                    self.created_product = created
                    opening = parse_int_input(self.opening_edit.text(), 0) if (self.opening_edit.isVisible() and self._allow_opening) else 0
                    if opening > 0 and not created.track_imei:
                        inventory_service.adjust_stock(self.session, self.user, created, opening, ar.PRODUCT_OPENING_REASON)
                self.session.commit()
                self.accept()
            except PermissionDenied as e:
                show_error(self, e)
            except Exception as e:
                self.session.rollback()
                show_error(self, e)
