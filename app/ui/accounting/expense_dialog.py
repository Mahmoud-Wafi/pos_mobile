"""Dialog for adding operating expenses."""
from __future__ import annotations

from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QMessageBox, QFrame, QInputDialog,
)

from app.core.money import egp_to_piasters, format_money
from app.models.accounting import CashAccount, ExpenseCategory
from app.services import accounting_service


class ExpenseDialog(QDialog):
    def __init__(self, session, user, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self.setWindowTitle("تسجيل مصروف تشغيلي")
        self.resize(480, 440)
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
            QLineEdit, QComboBox {
                background-color: #F8FAFC;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                padding: 10px 12px;
                font-size: 13px;
                color: #0F172A;
            }
            QLineEdit:focus, QComboBox:focus {
                background-color: #FFFFFF;
                border: 2px solid #2563EB;
            }
        """)
        self._build_ui()
        self._load_data()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        # Header
        hdr = QHBoxLayout()
        icon = QLabel("💸")
        icon.setStyleSheet("font-size: 28px;")
        hdr.addWidget(icon)

        t_box = QVBoxLayout()
        t_box.setSpacing(2)
        lbl_t = QLabel("تسجيل مصروف جديد")
        lbl_t.setStyleSheet("font-size: 16px; font-weight: bold; color: #0F172A;")
        lbl_sub = QLabel("يتم خصم المصروف من الخزينة المحددة وتسجيله في حركة النقدية")
        lbl_sub.setStyleSheet("font-size: 12px; color: #64748B; font-weight: normal;")
        t_box.addWidget(lbl_t)
        t_box.addWidget(lbl_sub)
        hdr.addLayout(t_box)
        hdr.addStretch()
        layout.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #E2E8F0;")
        layout.addWidget(sep)

        # Category
        layout.addWidget(QLabel("بند المصروف: *"))
        cat_box = QHBoxLayout()
        self.cat_combo = QComboBox()
        self.cat_combo.setFixedHeight(42)
        cat_box.addWidget(self.cat_combo, 1)

        btn_new_cat = QPushButton("➕ بند جديد")
        btn_new_cat.setFixedHeight(42)
        btn_new_cat.setStyleSheet("background-color: #EFF6FF; color: #2563EB; border: 1px solid #BFDBFE; border-radius: 8px; font-weight: bold; padding: 0 12px;")
        btn_new_cat.clicked.connect(self._create_category_inline)
        cat_box.addWidget(btn_new_cat)
        layout.addLayout(cat_box)

        # Amount
        layout.addWidget(QLabel("مبلغ المصروف (ج.م): *"))
        self.amount_edit = QLineEdit()
        self.amount_edit.setFixedHeight(42)
        self.amount_edit.setPlaceholderText("0.00 ج.م")
        self.amount_edit.setValidator(QDoubleValidator(0.01, 9999999.0, 2))
        layout.addWidget(self.amount_edit)

        # Cash Account
        layout.addWidget(QLabel("الخزينة المسحوب منها المصروف: *"))
        self.acc_combo = QComboBox()
        self.acc_combo.setFixedHeight(42)
        layout.addWidget(self.acc_combo)

        # Note
        layout.addWidget(QLabel("بيان أو ملاحظات المصروف:"))
        self.note_edit = QLineEdit()
        self.note_edit.setFixedHeight(42)
        self.note_edit.setPlaceholderText("فاتورة كهرباء شهر... / فاتورة مياه / ضيافة...")
        layout.addWidget(self.note_edit)

        layout.addStretch()

        # Buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(12)

        btn_cancel = QPushButton("إلغاء")
        btn_cancel.setFixedHeight(42)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #F1F5F9;
                color: #475569;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                font-weight: 600;
                padding: 0 18px;
            }
        """)
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_save = QPushButton("💾 تسجيل وصرف المصروف")
        btn_save.setFixedHeight(42)
        btn_save.setStyleSheet("""
            QPushButton {
                background-color: #DC2626;
                color: white;
                border-radius: 8px;
                font-weight: bold;
                padding: 0 24px;
            }
            QPushButton:hover {
                background-color: #B91C1C;
            }
        """)
        btn_save.clicked.connect(self._save)
        btn_box.addWidget(btn_save)

        layout.addLayout(btn_box)

    def _load_data(self):
        self.cat_combo.clear()
        categories = accounting_service.list_expense_categories(self.session, self.user)
        for c in categories:
            self.cat_combo.addItem(c.name, c.id)

        self.acc_combo.clear()
        accounts = accounting_service.list_accounts(self.session, self.user)
        for a in accounts:
            self.acc_combo.addItem(f"{a.name} ({format_money(a.balance)})", a.id)

    def _create_category_inline(self):
        name, ok = QInputDialog.getText(self, "بند مصروف جديد", "أدخل اسم البند الجديد (مثال: صيانة أجهزة):")
        if ok and name.strip():
            cat = accounting_service.create_expense_category(self.session, self.user, name.strip())
            self.session.commit()
            self._load_data()
            idx = self.cat_combo.findData(cat.id)
            if idx >= 0:
                self.cat_combo.setCurrentIndex(idx)

    def _save(self):
        cat_id = self.cat_combo.currentData()
        if not cat_id:
            QMessageBox.warning(self, "تنبيه", "يرجى اختيار بند المصروف")
            return

        amt_str = self.amount_edit.text().strip()
        if not amt_str:
            QMessageBox.warning(self, "تنبيه", "يرجى كتابة مبلغ المصروف")
            self.amount_edit.setFocus()
            return

        try:
            amt_piasters = egp_to_piasters(amt_str)
            if amt_piasters <= 0:
                raise ValueError()
        except Exception:
            QMessageBox.warning(self, "تنبيه", "صيغة المبلغ غير صحيحة")
            self.amount_edit.setFocus()
            return

        acc_id = self.acc_combo.currentData()
        note = self.note_edit.text().strip()

        try:
            accounting_service.add_expense(
                self.session, self.user,
                category_id=cat_id,
                amount=amt_piasters,
                account_id=acc_id,
                note=note,
            )
            self.session.commit()
            QMessageBox.information(self, "نجاح", f"تم تسجيل وصرف مصروف بقيمة {amt_str} ج.م بنجاح!")
            self.accept()
        except Exception as e:
            self.session.rollback()
            QMessageBox.critical(self, "خطأ", f"تعذر تسجيل المصروف:\n{str(e)}")

