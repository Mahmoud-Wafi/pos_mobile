"""Dialog for adding operating expenses."""
from __future__ import annotations
from app.i18n import ar

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
        self.setWindowTitle(ar.EXPENSE_DIALOG_42AB33)
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
        lbl_t = QLabel(ar.EXPENSE_DIALOG_FD6BCE)
        style_label(lbl_t, size="title", tone="text", bold=True)
        lbl_sub = QLabel(ar.EXPENSE_DIALOG_600748)
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
        layout.addWidget(QLabel(ar.EXPENSE_DIALOG_EE4207))
        cat_box = QHBoxLayout()
        self.cat_combo = QComboBox()
        self.cat_combo.setFixedHeight(42)
        cat_box.addWidget(self.cat_combo, 1)

        btn_new_cat = QPushButton(ar.EXPENSE_DIALOG_40141D)
        btn_new_cat.setFixedHeight(42)
        variant(btn_new_cat, "secondary")
        btn_new_cat.clicked.connect(self._create_category_inline)
        cat_box.addWidget(btn_new_cat)
        layout.addLayout(cat_box)

        # Amount
        layout.addWidget(QLabel(ar.EXPENSE_DIALOG_02F37A))
        self.amount_edit = QLineEdit()
        self.amount_edit.setFixedHeight(42)
        self.amount_edit.setPlaceholderText(ar.DAILY_CLOSE_DIALOG_388B15)
        self.amount_edit.setValidator(QDoubleValidator(0.01, 9999999.0, 2))
        layout.addWidget(self.amount_edit)

        # Cash Account
        layout.addWidget(QLabel(ar.EXPENSE_DIALOG_050A4D))
        self.acc_combo = QComboBox()
        self.acc_combo.setFixedHeight(42)
        layout.addWidget(self.acc_combo)

        # Note
        layout.addWidget(QLabel(ar.EXPENSE_DIALOG_B2E355))
        self.note_edit = QLineEdit()
        self.note_edit.setFixedHeight(42)
        self.note_edit.setPlaceholderText(ar.EXPENSE_DIALOG_2C306E)
        layout.addWidget(self.note_edit)

        layout.addStretch()

        # Buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(12)

        btn_cancel = QPushButton(ar.CANCEL)
        btn_cancel.setFixedHeight(42)
        variant(btn_cancel, "secondary")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_save = QPushButton(ar.EXPENSE_DIALOG_A70661)
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
        name, ok = QInputDialog.getText(self, ar.EXPENSE_DIALOG_87DBAE, ar.EXPENSE_DIALOG_7D3D46)
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
            show_error(self, message=ar.EXPENSE_DIALOG_CBBF13)
            return

        amt_str = self.amount_edit.text().strip()
        if not amt_str:
            show_error(self, message=ar.EXPENSE_DIALOG_D5D9C0)
            self.amount_edit.setFocus()
            return

        try:
            amt_piasters = egp_to_piasters(amt_str)
            if amt_piasters <= 0:
                raise ValueError()
        except Exception:
            show_error(self, message=ar.EXPENSE_DIALOG_51D7FD)
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

