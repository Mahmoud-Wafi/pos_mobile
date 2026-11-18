"""Modal dialog to enter / scan IMEIs for phone items in purchase invoices."""
from __future__ import annotations
from app.i18n import ar

from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QFrame,
)

from app.ui.components.basic import attach_imei_check
from app.ui.design.style import style_label, variant
from app.ui.design import icons
from app.ui.design.tokens import COLORS


from app.ui.components import icon_button, show_error


class IMEIInputDialog(QDialog):
    def __init__(self, product_name: str, required_count: int, existing_imeis: Optional[list[dict]] = None, parent=None):
        super().__init__(parent)
        self.product_name = product_name
        self.required_count = required_count
        self.imeis: list[dict] = list(existing_imeis or [])
        self.setWindowTitle(f"إدخال أرقام السيريال (IMEI) — {product_name}")
        self.resize(580, 500)
        self.setModal(True)

        self._build_ui()
        self._refresh_table()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header Info
        header = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(icons.pixmap("smartphone", COLORS["primary"], 28))
        header.addWidget(icon)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        lbl_title = QLabel(f"تسجيل سيريالات: {self.product_name}")
        style_label(lbl_title, size="title", tone="text", bold=True)
        self.lbl_counter = QLabel(f"المطلوب إدخاله: {self.required_count} جهاز | المسجل حالياً: {len(self.imeis)}")
        style_label(self.lbl_counter, size="caption", tone="primary", bold=True)
        title_box.addWidget(lbl_title)
        title_box.addWidget(self.lbl_counter)
        header.addLayout(title_box)
        header.addStretch()
        layout.addLayout(header)

        # Scan Bar
        scan_box = QHBoxLayout()
        scan_box.setSpacing(8)

        self.imei1_edit = QLineEdit()

        attach_imei_check(self.imei1_edit, required=True)
        self.imei1_edit.setFixedHeight(40)
        self.imei1_edit.setPlaceholderText(ar.IMEI_INPUT_DIALOG_C008E5)
        scan_box.addWidget(self.imei1_edit, 5)

        self.imei2_edit = QLineEdit()

        attach_imei_check(self.imei2_edit, required=False)
        self.imei2_edit.setFixedHeight(40)
        self.imei2_edit.setPlaceholderText(ar.IMEI_INPUT_DIALOG_C853FB)
        scan_box.addWidget(self.imei2_edit, 4)

        self.btn_add = QPushButton(ar.AUTO_ICONS_B9508A)
        self.btn_add.setFixedHeight(40)
        variant(self.btn_add, "primary")
        self.btn_add.clicked.connect(self._add_imei)
        self.imei1_edit.returnPressed.connect(self._add_imei)
        self.imei2_edit.returnPressed.connect(self._add_imei)
        scan_box.addWidget(self.btn_add)

        layout.addLayout(scan_box)

        # Table of Entered IMEIs
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["#", ar.IMEI_INPUT_DIALOG_849984, ar.IMEI_INPUT_DIALOG_55644F, ar.DELETE])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 40)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(3, 70)

        layout.addWidget(self.table)

        # Bottom buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)

        btn_cancel = QPushButton(ar.CANCEL)
        btn_cancel.setFixedHeight(40)
        variant(btn_cancel, "secondary")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_save = QPushButton(ar.IMEI_INPUT_DIALOG_DE5664)
        btn_save.setFixedHeight(40)
        variant(btn_save, "success")
        btn_save.clicked.connect(self._confirm)
        btn_box.addWidget(btn_save)

        layout.addLayout(btn_box)

    def _add_imei(self):
        val1 = self.imei1_edit.text().strip()
        val2 = self.imei2_edit.text().strip() or None

        if not val1:
            show_error(self, message=ar.IMEI_INPUT_DIALOG_06FB49)
            self.imei1_edit.setFocus()
            return

        if len(self.imeis) >= self.required_count:
            show_error(self, message=f"تم بالفعل إدخال كامل العدد المطلوب ({self.required_count} جهاز)")
            return

        # Check in current list
        for item in self.imeis:
            if item["imei1"] == val1 or (item.get("imei2") and item["imei2"] == val1):
                show_error(self, message=f"رقم IMEI '{val1}' مكرر بالقائمة الحالية")
                return
            if val2 and (item["imei1"] == val2 or item.get("imei2") == val2):
                show_error(self, message=f"رقم IMEI 2 '{val2}' مكرر بالقائمة الحالية")
                return

        self.imeis.append({"imei1": val1, "imei2": val2})
        self.imei1_edit.clear()
        self.imei2_edit.clear()
        self.imei1_edit.setFocus()
        self._refresh_table()

    def _refresh_table(self):
        self.table.setRowCount(len(self.imeis))
        for idx, item in enumerate(self.imeis):
            item_num = QTableWidgetItem(str(idx + 1))
            item_num.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(idx, 0, item_num)

            item_1 = QTableWidgetItem(item["imei1"])
            item_1.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(idx, 1, item_1)

            item_2 = QTableWidgetItem(item.get("imei2") or "—")
            item_2.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(idx, 2, item_2)

            btn_del = icon_button("trash-2", ar.DELETE, "danger-soft")
            btn_del.clicked.connect(lambda _, row=idx: self._delete_row(row))
            self.table.setCellWidget(idx, 3, btn_del)

        self.lbl_counter.setText(
            f"المطلوب إدخاله: {self.required_count} جهاز | المسجل حالياً: {len(self.imeis)}"
        )
        if len(self.imeis) == self.required_count:
            style_label(self.lbl_counter, size="caption", tone="success", bold=True)
        else:
            style_label(self.lbl_counter, size="caption", tone="warning", bold=True)

    def _delete_row(self, row: int):
        if 0 <= row < len(self.imeis):
            self.imeis.pop(row)
            self._refresh_table()

    def _confirm(self):
        if len(self.imeis) != self.required_count:
            show_error(self, message=f"العدد المسجل ({len(self.imeis)}) لا يطابق الكمية المطلوبة ({self.required_count} جهاز).\nيرجى إدخال جميع السيريالات أو تعديل كمية الصنف بالفاتورة.")
            return
        self.accept()

