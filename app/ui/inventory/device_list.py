"""Modern Device / IMEI list widget with search, status badges, and clean dialog."""
from __future__ import annotations
from app.i18n import ar
from app.ui.components.numeric import set_int_validator, set_money_validator

from app.ui.components import show_error, show_toast
from app.core.money import normalize_number_text, piasters_to_input

from decimal import Decimal
from app.ui.design.style import style_label, variant
from app.ui.design import icons
from app.ui.design.tokens import COLORS

try:
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
        QTableWidgetItem, QHeaderView, QDialog, QLineEdit,
        QComboBox, QMessageBox, QLabel, QFrame, QGridLayout, QGroupBox,
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor
    HAS_QT = True
except ImportError:
    HAS_QT = False

if HAS_QT:
    from app.services import inventory_service
    from app.models.product import Product
    from app.core.money import format_money, egp_to_piasters
    from app.core.permissions import PermissionDenied

    HEADERS = ["#", ar.DEVICE_LIST_D18270, ar.DEVICE_LIST_9F4371, ar.DEVICE_LIST_3F6549, ar.DEVICE_LIST_E887F5, ar.DEVICE_LIST_E1DCB7, ar.DEVICE_LIST_592F9D]

    STATUS_CONFIG = {
        "in_stock": (ar.DEVICE_LIST_99F6F9, "#ECFDF5", "#065F46"),
        "sold": (ar.DEVICE_LIST_3655DA, "#EFF6FF", "#1E40AF"),
        "returned": (ar.HISTORY_RETURN, "#FEF3C7", "#92400E"),
        "damaged": (ar.DEVICE_LIST_250573, "#FEE2E2", "#991B1B"),
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
            self.search_edit.setPlaceholderText(ar.DEVICE_LIST_1EDD35)
            self.search_edit.setMinimumWidth(300)
            self.search_edit.setFixedHeight(40)
            self.search_edit.textChanged.connect(self._filter_devices)
            bar.addWidget(self.search_edit)

            self.filter_status = QComboBox()
            self.filter_status.setFixedHeight(40)
            self.filter_status.addItem(ar.DEVICE_LIST_A4028D, "all")
            self.filter_status.addItem(ar.DEVICE_LIST_160CF3, "in_stock")
            self.filter_status.addItem(ar.DEVICE_LIST_2C6AC8, "sold")
            self.filter_status.addItem(ar.DEVICE_LIST_422EC2, "returned")
            self.filter_status.currentIndexChanged.connect(self._filter_devices)
            bar.addWidget(self.filter_status)

            bar.addStretch()

            self.btn_import = QPushButton(ar.IMPORT_BUTTON)
            self.btn_import.setMinimumHeight(40)
            self.btn_import.clicked.connect(self._import_excel)
            bar.addWidget(self.btn_import)
            self.btn_export = QPushButton(ar.EXPORT_BUTTON)
            self.btn_export.setMinimumHeight(40)
            self.btn_export.clicked.connect(self._export_excel)
            bar.addWidget(self.btn_export)
            self.btn_edit = QPushButton(ar.INV_BTN_EDIT)
            self.btn_edit.setMinimumHeight(40)
            self.btn_edit.clicked.connect(self._edit_device)
            bar.addWidget(self.btn_edit)
            self.btn_writeoff = QPushButton(ar.INV_BTN_WRITE_OFF)
            self.btn_writeoff.setMinimumHeight(40)
            self.btn_writeoff.clicked.connect(self._write_off)
            bar.addWidget(self.btn_writeoff)
            self.btn_delete = QPushButton(ar.INV_BTN_DELETE)
            self.btn_delete.setMinimumHeight(40)
            variant(self.btn_delete, "danger")
            self.btn_delete.clicked.connect(self._delete_device)
            bar.addWidget(self.btn_delete)
            self.btn_labels = QPushButton(ar.LABEL_PRINT)
            self.btn_labels.setMinimumHeight(40)
            self.btn_labels.clicked.connect(self._print_labels)
            bar.addWidget(self.btn_labels)

            self.btn_refresh = QPushButton(ar.REFRESH)
            self.btn_refresh.setFixedHeight(40)
            self.btn_refresh.clicked.connect(self.load_data)
            bar.addWidget(self.btn_refresh)

            self.btn_add = QPushButton(ar.DEVICE_LIST_CC7227)
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
            from app.core.permissions import PERM_COST_VIEW
            if PERM_COST_VIEW not in self.user.permission_codes():
                self.table.setColumnHidden(6, True)
            self.table.doubleClicked.connect(self._edit_device)

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
            style_label(self.footer_label, size="body", tone="muted", bold=True)
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
            self._shown = list(devices)
            self.table.setRowCount(len(devices))
            for row, d in enumerate(devices):
                status_ar, bg_col, fg_col = STATUS_CONFIG.get(d.status, (d.status, "#F1F5F9", "#0F172A"))
                cond_ar = ar.DEVICE_CONDITION_NEW if d.condition == "new" else ar.DEVICE_CONDITION_USED

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

        def _current_device(self):
            row = self.table.currentRow()
            shown = getattr(self, "_shown", [])
            if 0 <= row < len(shown):
                return shown[row]
            show_error(self, message=ar.INV_SELECT_ROW)
            return None

        def _edit_device(self, *_):
            from app.ui.components import show_toast
            d = self._current_device()
            if d is not None and DeviceEditDialog(self.session, self.user, d, parent=self).exec():
                show_toast(self, ar.INV_SAVED)
                self.load_data()

        def _write_off(self):
            from PySide6.QtWidgets import QInputDialog
            from app.ui.components import show_toast
            d = self._current_device()
            if d is None:
                return
            reason, ok = QInputDialog.getText(self, ar.INV_BTN_WRITE_OFF, ar.DEVICE_REASON_REQUIRED)
            if not ok:
                return
            try:
                inventory_service.write_off_device(self.session, self.user, d.id, reason)
                self.session.commit()
            except Exception as exc:
                self.session.rollback()
                show_error(self, exc)
                return
            show_toast(self, ar.INV_SAVED)
            self.load_data()

        def _delete_device(self):
            from app.ui.components import confirm, show_toast
            d = self._current_device()
            if d is None or not confirm(self, ar.INV_BTN_DELETE, ar.INV_CONFIRM_DELETE_DEVICE,
                                        ar.INV_BTN_DELETE, destructive=True):
                return
            try:
                inventory_service.delete_device(self.session, self.user, d.id)
                self.session.commit()
            except Exception as exc:
                self.session.rollback()
                show_error(self, exc)
                return
            show_toast(self, ar.INV_DELETED)
            self.load_data()

        def _print_labels(self):
            from PySide6.QtWidgets import QFileDialog
            from app.services import label_service
            from app.ui.components import show_error, show_toast
            row = self.table.currentRow()
            shown = getattr(self, "_shown", [])
            if not 0 <= row < len(shown):
                show_error(self, message=ar.LABEL_NOTHING)
                return
            dest, _ = QFileDialog.getSaveFileName(self, ar.LABEL_SAVE_TITLE, "labels.pdf", "PDF (*.pdf)")
            if not dest:
                return
            try:
                label_service.render(label_service.device_specs(self.session, self.user, [shown[row]]), dest)
            except Exception as exc:
                show_error(self, exc)
                return
            show_toast(self, ar.LABEL_SAVED)

        def _import_excel(self):
            from app.ui.inventory.import_wizard import ImportWizard
            if ImportWizard(self.session, self.user, kind="devices", parent=self).exec():
                self.load_data()

        def _export_excel(self):
            from PySide6.QtWidgets import QFileDialog
            from app.services import import_export_service as ie
            from app.ui.components import show_error, show_toast
            dest, _ = QFileDialog.getSaveFileName(self, ar.EXPORT_BUTTON, "devices.xlsx", "Excel (*.xlsx);;CSV (*.csv)")
            if dest:
                try:
                    ie.export_devices(self.session, self.user, dest)
                    show_toast(self, ar.EXPORT_DONE)
                except Exception as exc:
                    show_error(self, exc)

        def _add_device(self):
            dlg = AddDeviceDialog(self.session, self.user, parent=self)
            if dlg.exec() == QDialog.Accepted:
                self.load_data()


    class DeviceEditDialog(QDialog):
        """Edit one device. Sold / written-off devices only allow notes (the service enforces it)."""

        def __init__(self, session, user, device, parent=None):
            super().__init__(parent)
            from PySide6.QtWidgets import QFormLayout, QDialogButtonBox
            from app.core.permissions import PERM_COST_VIEW
            self.session, self.user, self.device = session, user, device
            self._can_cost = PERM_COST_VIEW in user.permission_codes()
            self.setWindowTitle(ar.INV_EDIT_DEVICE)
            self.setLayoutDirection(Qt.RightToLeft)
            self.setMinimumWidth(420)
            form = QFormLayout(self)
            self.imei1, self.imei2 = QLineEdit(device.imei1), QLineEdit(device.imei2 or "")
            from app.ui.components.basic import attach_imei_check
            attach_imei_check(self.imei1)
            attach_imei_check(self.imei2, required=False)
            self.condition = QComboBox()
            self.condition.addItem(ar.DEVICE_CONDITION_NEW, "new")
            self.condition.addItem(ar.DEVICE_CONDITION_USED, "used")
            self.condition.setCurrentIndex(max(0, self.condition.findData(device.condition)))
            self.purchase_cost = QLineEdit(piasters_to_input(device.purchase_cost))
            self.extra_cost = QLineEdit(piasters_to_input(device.extra_cost))
            self.notes = QLineEdit(device.notes or "")
            form.addRow(ar.DEVICE_LIST_9F4371, self.imei1)
            form.addRow(ar.DEVICE_LIST_3F6549, self.imei2)
            form.addRow(ar.DEVICE_LIST_E1DCB7, self.condition)
            if self._can_cost:
                form.addRow(ar.DEVICE_COST_LABEL, self.purchase_cost)
                form.addRow(ar.DEVICE_EXTRA_COST_LABEL, self.extra_cost)
            form.addRow(ar.DEVICE_NOTES_LABEL, self.notes)
            if device.status != "in_stock":
                for w in (self.imei1, self.imei2, self.condition, self.purchase_cost, self.extra_cost):
                    w.setEnabled(False)
            btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            btns.accepted.connect(self._save)
            btns.rejected.connect(self.reject)
            form.addRow(btns)

        def _save(self):
            from app.core.money import parse_egp_input
            data = {"notes": self.notes.text()}
            if self.device.status == "in_stock":
                data.update(imei1=self.imei1.text(), imei2=self.imei2.text(), condition=self.condition.currentData())
                if self._can_cost:
                    try:
                        data.update(purchase_cost=parse_egp_input(self.purchase_cost.text() or "0"),
                                    extra_cost=parse_egp_input(self.extra_cost.text() or "0"))
                    except ValueError:
                        show_error(self, message=ar.INV_NEGATIVE_VALUE)
                        return
            try:
                inventory_service.update_device(self.session, self.user, self.device.id, data)
                self.session.commit()
            except Exception as exc:
                self.session.rollback()
                show_error(self, exc)
                return
            self.accept()


    class AddDeviceDialog(QDialog):
        """Beautiful modern modal dialog for registering individual phones with IMEI."""

        def __init__(self, session, user, parent=None):
            super().__init__(parent)
            self.session = session
            self.user = user
            self.setWindowTitle(ar.DEVICE_LIST_A96D0E)
            self.setMinimumWidth(620)

            self._build_ui()

        def _build_ui(self):
            main_layout = QVBoxLayout(self)
            main_layout.setContentsMargins(28, 24, 28, 24)
            main_layout.setSpacing(18)

            # Header
            header_box = QHBoxLayout()
            icon_lbl = QLabel()
            icon_lbl.setPixmap(icons.pixmap("smartphone", COLORS["primary"], 28))
            header_box.addWidget(icon_lbl)

            header_text = QVBoxLayout()
            header_text.setSpacing(2)
            title = QLabel(ar.DEVICE_LIST_AE5015)
            style_label(title, size="h2", tone="text", bold=True)
            subtitle = QLabel(ar.DEVICE_LIST_C8762A)
            style_label(subtitle, size="caption", tone="muted")
            header_text.addWidget(title)
            header_text.addWidget(subtitle)
            header_box.addLayout(header_text)
            header_box.addStretch()

            main_layout.addLayout(header_box)

            # ─── Group 1: اختيار الموديل ───
            grp_model = QGroupBox(ar.DEVICE_LIST_0FCB3C)
            grid_model = QGridLayout(grp_model)
            grid_model.setHorizontalSpacing(14)
            grid_model.setVerticalSpacing(10)

            lbl_prod = QLabel(ar.DEVICE_LIST_E11BED)
            style_label(lbl_prod, bold=True)
            self.product_combo = QComboBox()
            self.product_combo.setFixedHeight(40)
            grid_model.addWidget(lbl_prod, 0, 0)
            grid_model.addWidget(self.product_combo, 1, 0)

            main_layout.addWidget(grp_model)

            # ─── Group 2: أرقام السيريال ───
            grp_imei = QGroupBox(ar.DEVICE_LIST_F77BFD)
            grid_imei = QGridLayout(grp_imei)
            grid_imei.setHorizontalSpacing(14)
            grid_imei.setVerticalSpacing(10)

            lbl_i1 = QLabel(ar.DEVICE_LIST_2E2947)
            style_label(lbl_i1, tone="info", bold=True)
            self.imei1_edit = QLineEdit()
            self.imei1_edit.setFixedHeight(40)
            self.imei1_edit.setPlaceholderText(ar.DEVICE_LIST_C266B5)

            lbl_i2 = QLabel(ar.DEVICE_LIST_8B7CEA)
            style_label(lbl_i2, bold=True)
            self.imei2_edit = QLineEdit()
            self.imei2_edit.setFixedHeight(40)
            self.imei2_edit.setPlaceholderText(ar.DEVICE_LIST_9FA171)

            grid_imei.addWidget(lbl_i1, 0, 0)
            grid_imei.addWidget(lbl_i2, 0, 1)
            grid_imei.addWidget(self.imei1_edit, 1, 0)
            grid_imei.addWidget(self.imei2_edit, 1, 1)

            main_layout.addWidget(grp_imei)

            # ─── Group 3: الحالة والتكلفة ───
            grp_cost = QGroupBox(ar.DEVICE_LIST_FD5405)
            grid_cost = QGridLayout(grp_cost)
            grid_cost.setHorizontalSpacing(14)
            grid_cost.setVerticalSpacing(10)

            lbl_cond = QLabel(ar.DEVICE_LIST_F66554)
            style_label(lbl_cond, bold=True)
            self.condition_combo = QComboBox()
            self.condition_combo.setFixedHeight(40)
            self.condition_combo.addItem(ar.DEVICE_LIST_2FC602, "new")
            self.condition_combo.addItem(ar.DEVICE_LIST_A3C97D, "used")

            lbl_cost = QLabel(ar.DEVICE_LIST_E1A045)
            style_label(lbl_cost, bold=True)
            self.cost_edit = QLineEdit()
            self.cost_edit.setFixedHeight(40)
            self.cost_edit.setPlaceholderText(ar.DAILY_CLOSE_DIALOG_388B15)
            set_money_validator(self.cost_edit, 0.0, 9999999.0)

            lbl_extra = QLabel(ar.DEVICE_LIST_ADF72C)
            style_label(lbl_extra, bold=True)
            self.extra_cost_edit = QLineEdit("0")
            self.extra_cost_edit.setFixedHeight(40)
            self.extra_cost_edit.setPlaceholderText(ar.DAILY_CLOSE_DIALOG_388B15)
            set_money_validator(self.extra_cost_edit, 0.0, 9999999.0)

            grid_cost.addWidget(lbl_cond, 0, 0)
            grid_cost.addWidget(lbl_cost, 0, 1)
            grid_cost.addWidget(lbl_extra, 0, 2)

            grid_cost.addWidget(self.condition_combo, 1, 0)
            grid_cost.addWidget(self.cost_edit, 1, 1)
            grid_cost.addWidget(self.extra_cost_edit, 1, 2)

            lbl_notes = QLabel(ar.DEVICE_LIST_35BE9F)
            style_label(lbl_notes, bold=True)
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

            btn_cancel = QPushButton(ar.DEVICE_LIST_69A551)
            btn_cancel.setFixedHeight(44)
            btn_cancel.setMinimumWidth(120)
            variant(btn_cancel, "secondary")
            btn_cancel.clicked.connect(self.reject)

            btn_save = QPushButton(ar.DEVICE_LIST_7956E2)
            btn_save.setObjectName("PrimaryBtn")
            btn_save.setFixedHeight(44)
            btn_save.setMinimumWidth(220)
            variant(btn_save, "primary")
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
                self.product_combo.addItem(f"{p.name}", p)
            if products:
                # Pre-fill cost price from product default
                self.cost_edit.setText(piasters_to_input(p.cost_price))

        def _save(self):
            if not self._products:
                show_error(self, message=ar.DEVICE_LIST_9BE0F3)
                return

            product = self.product_combo.currentData()
            imei1 = self.imei1_edit.text().strip()
            if not imei1:
                show_error(self, message=ar.DEVICE_LIST_F5623C)
                self.imei1_edit.setFocus()
                return

            cost_str = self.cost_edit.text().strip() or "0"
            try:
                cost_egp = Decimal(normalize_number_text(cost_str))
            except Exception:
                cost_egp = Decimal("0")

            extra_str = self.extra_cost_edit.text().strip() or "0"
            try:
                extra_egp = Decimal(normalize_number_text(extra_str))
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
                show_error(self, e)
            except PermissionDenied as e:
                show_error(self, e)
            except Exception as e:
                self.session.rollback()
                show_error(self, e)
