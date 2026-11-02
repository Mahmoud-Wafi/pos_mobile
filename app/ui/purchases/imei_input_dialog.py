"""Modal dialog to enter / scan IMEIs for phone items in purchase invoices."""
from __future__ import annotations

from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QFrame,
)


class IMEIInputDialog(QDialog):
    def __init__(self, product_name: str, required_count: int, existing_imeis: Optional[list[dict]] = None, parent=None):
        super().__init__(parent)
        self.product_name = product_name
        self.required_count = required_count
        self.imeis: list[dict] = list(existing_imeis or [])
        self.setWindowTitle(f"إدخال أرقام السيريال (IMEI) — {product_name}")
        self.resize(580, 500)
        self.setModal(True)
        self.setStyleSheet("""
            QDialog {
                background-color: #FFFFFF;
            }
            QLabel {
                color: #0F172A;
                font-size: 13px;
                font-weight: 600;
            }
            QLineEdit {
                background-color: #F8FAFC;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
                color: #0F172A;
            }
            QLineEdit:focus {
                background-color: #FFFFFF;
                border: 2px solid #2563EB;
            }
        """)
        self._build_ui()
        self._refresh_table()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header Info
        header = QHBoxLayout()
        icon = QLabel("📱")
        icon.setStyleSheet("font-size: 26px;")
        header.addWidget(icon)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        lbl_title = QLabel(f"تسجيل سيريالات: {self.product_name}")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #0F172A;")
        self.lbl_counter = QLabel(f"المطلوب إدخاله: {self.required_count} جهاز | المسجل حالياً: {len(self.imeis)}")
        self.lbl_counter.setStyleSheet("font-size: 12px; color: #2563EB; font-weight: bold;")
        title_box.addWidget(lbl_title)
        title_box.addWidget(self.lbl_counter)
        header.addLayout(title_box)
        header.addStretch()
        layout.addLayout(header)

        # Scan Bar
        scan_box = QHBoxLayout()
        scan_box.setSpacing(8)

        self.imei1_edit = QLineEdit()
        self.imei1_edit.setFixedHeight(40)
        self.imei1_edit.setPlaceholderText("امسح بالباركود أو اكتب IMEI 1 *")
        scan_box.addWidget(self.imei1_edit, 5)

        self.imei2_edit = QLineEdit()
        self.imei2_edit.setFixedHeight(40)
        self.imei2_edit.setPlaceholderText("IMEI 2 (اختياري)")
        scan_box.addWidget(self.imei2_edit, 4)

        self.btn_add = QPushButton("➕ إضافة")
        self.btn_add.setFixedHeight(40)
        self.btn_add.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: white;
                border-radius: 8px;
                font-weight: 600;
                padding: 0 16px;
            }
            QPushButton:hover {
                background-color: #1D4ED8;
            }
        """)
        self.btn_add.clicked.connect(self._add_imei)
        self.imei1_edit.returnPressed.connect(self._add_imei)
        self.imei2_edit.returnPressed.connect(self._add_imei)
        scan_box.addWidget(self.btn_add)

        layout.addLayout(scan_box)

        # Table of Entered IMEIs
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["#", "IMEI 1 (الرئيسي)", "IMEI 2 (الإضافي)", "حذف"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 40)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(3, 70)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
            }
            QHeaderView::section {
                background-color: #F8FAFC;
                color: #475569;
                font-weight: bold;
                padding: 6px;
                border: none;
                border-bottom: 1px solid #E2E8F0;
            }
        """)
        layout.addWidget(self.table)

        # Bottom buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)

        btn_cancel = QPushButton("إلغاء")
        btn_cancel.setFixedHeight(40)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #F1F5F9;
                color: #475569;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                font-weight: 600;
                padding: 0 16px;
            }
        """)
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_save = QPushButton("✅ اعتماد السيريالات")
        btn_save.setFixedHeight(40)
        btn_save.setStyleSheet("""
            QPushButton {
                background-color: #16A34A;
                color: white;
                border-radius: 8px;
                font-weight: bold;
                padding: 0 24px;
            }
            QPushButton:hover {
                background-color: #15803D;
            }
        """)
        btn_save.clicked.connect(self._confirm)
        btn_box.addWidget(btn_save)

        layout.addLayout(btn_box)

    def _add_imei(self):
        val1 = self.imei1_edit.text().strip()
        val2 = self.imei2_edit.text().strip() or None

        if not val1:
            QMessageBox.warning(self, "تنبيه", "يرجى مسح أو إدخال رقم IMEI 1")
            self.imei1_edit.setFocus()
            return

        if len(self.imeis) >= self.required_count:
            QMessageBox.warning(self, "تنبيه", f"تم بالفعل إدخال كامل العدد المطلوب ({self.required_count} جهاز)")
            return

        # Check in current list
        for item in self.imeis:
            if item["imei1"] == val1 or (item.get("imei2") and item["imei2"] == val1):
                QMessageBox.warning(self, "تنبيه", f"رقم IMEI '{val1}' مكرر بالقائمة الحالية")
                return
            if val2 and (item["imei1"] == val2 or item.get("imei2") == val2):
                QMessageBox.warning(self, "تنبيه", f"رقم IMEI 2 '{val2}' مكرر بالقائمة الحالية")
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

            btn_del = QPushButton("❌")
            btn_del.setStyleSheet("border: none; background: transparent; color: #EF4444; font-weight: bold;")
            btn_del.clicked.connect(lambda _, row=idx: self._delete_row(row))
            self.table.setCellWidget(idx, 3, btn_del)

        self.lbl_counter.setText(
            f"المطلوب إدخاله: {self.required_count} جهاز | المسجل حالياً: {len(self.imeis)}"
        )
        if len(self.imeis) == self.required_count:
            self.lbl_counter.setStyleSheet("font-size: 12px; color: #16A34A; font-weight: bold;")
        else:
            self.lbl_counter.setStyleSheet("font-size: 12px; color: #EA580C; font-weight: bold;")

    def _delete_row(self, row: int):
        if 0 <= row < len(self.imeis):
            self.imeis.pop(row)
            self._refresh_table()

    def _confirm(self):
        if len(self.imeis) != self.required_count:
            QMessageBox.warning(
                self,
                "تنبيه",
                f"العدد المسجل ({len(self.imeis)}) لا يطابق الكمية المطلوبة ({self.required_count} جهاز).\nيرجى إدخال جميع السيريالات أو تعديل كمية الصنف بالفاتورة."
            )
            return
        self.accept()

