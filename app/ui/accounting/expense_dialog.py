"""Dialog for adding operating expenses."""
from __future__ import annotations

from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QMessageBox, QFrame, QInputDialog,
)

from app.ui.components import show_error, show_toast
from app.core.money import egp_to_piasters, format_money
from app.models.accounting import CashAccount, ExpenseCategory
from app.services import accounting_service
from app.ui.design.style import set_prop, style_label, variant
from app.ui.design import icons
from app.ui.design.tokens import COLORS


class ExpenseDialog(QDialog):
    def __init__(self, session, user, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self.setWindowTitle("تسجيل مصروف تشغيلي")
        self.resize(480, 440)
        self.setModal(True)

        self._build_ui()
        self._load_data()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        # Header
        hdr = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(icons.pixmap("banknote", COLORS["primary"], 28))
        hdr.addWidget(icon)

        t_box = QVBoxLayout()
        t_box.setSpacing(2)
        lbl_t = QLabel("تسجيل مصروف جديد")
        style_label(lbl_t, size="title", tone="text", bold=True)
        lbl_sub = QLabel("يتم خصم المصروف من الخزينة المحددة وتسجيله في حركة النقدية")
        style_label(lbl_sub, size="caption", tone="muted")
        t_box.addWidget(lbl_t)
        t_box.addWidget(lbl_sub)
        hdr.addLayout(t_box)
        hdr.addStretch()
        layout.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        set_prop(sep, "hline", True)
        layout.addWidget(sep)

        # Category
        layout.addWidget(QLabel("بند المصروف: *"))
        cat_box = QHBoxLayout()
        self.cat_combo = QComboBox()
        self.cat_combo.setFixedHeight(42)
        cat_box.addWidget(self.cat_combo, 1)

        btn_new_cat = QPushButton("بند جديد")
        btn_new_cat.setFixedHeight(42)
        variant(btn_new_cat, "secondary")
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
        variant(btn_cancel, "secondary")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_save = QPushButton("تسجيل وصرف المصروف")
        btn_save.setFixedHeight(42)
        variant(btn_save, "danger")
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
            show_error(self, message="يرجى اختيار بند المصروف")
            return

        amt_str = self.amount_edit.text().strip()
        if not amt_str:
            show_error(self, message="يرجى كتابة مبلغ المصروف")
            self.amount_edit.setFocus()
            return

        try:
            amt_piasters = egp_to_piasters(amt_str)
            if amt_piasters <= 0:
                raise ValueError()
        except Exception:
            show_error(self, message="صيغة المبلغ غير صحيحة")
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
            show_toast(self, f"تم تسجيل وصرف مصروف بقيمة {amt_str} ج.م بنجاح!")
            self.accept()
        except Exception as e:
            self.session.rollback()
            show_error(self, message=f"تعذر تسجيل المصروف:\n{str(e)}")

