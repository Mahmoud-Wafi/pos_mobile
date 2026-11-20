"""Dialog for paying suppliers (settling debts)."""
from __future__ import annotations
from app.i18n import ar
from app.ui.components.numeric import set_int_validator, set_money_validator

from PySide6.QtCore import Qt

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QMessageBox, QFrame,
)

from app.ui.components import show_error, show_toast
from app.core.money import egp_to_piasters, format_money, piasters_to_egp
from app.models.accounting import CashAccount
from app.models.purchase import Supplier
from app.services import purchase_service
from app.ui.design.style import set_prop, style_label, variant
from app.ui.design import icons
from app.ui.design.tokens import COLORS


class SupplierPaymentDialog(QDialog):
    def __init__(self, session, user, supplier: Supplier, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self.supplier = supplier
        self.setWindowTitle(f"سداد دفعة للمورد: {supplier.name}")
        self.resize(480, 440)
        self.setModal(True)

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(icons.pixmap("wallet", COLORS["primary"], 28))
        header.addWidget(icon)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        lbl_title = QLabel(f"سداد دفعة للمورد: {self.supplier.name}")
        style_label(lbl_title, size="title", tone="text", bold=True)
        lbl_sub = QLabel(ar.SUPPLIER_PAYMENT_DIALOG_859984)
        style_label(lbl_sub, size="caption", tone="muted")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)
        header.addLayout(title_box)
        header.addStretch()
        layout.addLayout(header)

        # Current Balance Card
        bal_card = QFrame()
        set_prop(bal_card, "banner", "info")
        bal_layout = QHBoxLayout(bal_card)
        bal_title = QLabel(ar.SUPPLIER_PAYMENT_DIALOG_7451CB)
        style_label(bal_title, size="body", tone="primary", bold=True)
        self.bal_value = QLabel(format_money(self.supplier.balance))
        style_label(self.bal_value, size="title", tone="primary", bold=True)
        bal_layout.addWidget(bal_title)
        bal_layout.addStretch()
        bal_layout.addWidget(self.bal_value)
        layout.addWidget(bal_card)

        # Amount
        layout.addWidget(QLabel(ar.SUPPLIER_PAYMENT_DIALOG_ED34C2))
        self.amount_edit = QLineEdit()
        self.amount_edit.setFixedHeight(44)
        self.amount_edit.setPlaceholderText(ar.DAILY_CLOSE_DIALOG_388B15)
        set_money_validator(self.amount_edit, 0.01, 9999999.0)
        layout.addWidget(self.amount_edit)

        # Account / Method
        layout.addWidget(QLabel(ar.SUPPLIER_PAYMENT_DIALOG_5FE4FB))
        self.account_combo = QComboBox()
        self.account_combo.setFixedHeight(42)
        accounts = self.session.query(CashAccount).all()
        for acc in accounts:
            label = f"{acc.name} ({format_money(acc.balance)})"
            self.account_combo.addItem(label, acc.id)
        layout.addWidget(self.account_combo)

        # Note
        layout.addWidget(QLabel(ar.SUPPLIER_PAYMENT_DIALOG_0CA0B7))
        self.note_edit = QLineEdit()
        self.note_edit.setFixedHeight(42)
        self.note_edit.setPlaceholderText(ar.SUPPLIER_PAYMENT_DIALOG_87E58F)
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

        btn_pay = QPushButton(ar.SUPPLIER_PAYMENT_DIALOG_6BA03B)
        btn_pay.setFixedHeight(42)
        variant(btn_pay, "success")
        btn_pay.clicked.connect(self._pay)
        btn_box.addWidget(btn_pay)

        layout.addLayout(btn_box)

    def _pay(self):
        val_text = self.amount_edit.text().strip()
        if not val_text:
            show_error(self, message=ar.SUPPLIER_PAYMENT_DIALOG_F14231)
            self.amount_edit.setFocus()
            return

        try:
            amount_piasters = egp_to_piasters(val_text)
            if amount_piasters <= 0:
                show_error(self, message=ar.SUPPLIER_PAYMENT_DIALOG_9B3013)
                return
        except Exception:
            show_error(self, message=ar.EXPENSE_DIALOG_51D7FD)
            return

        account_id = self.account_combo.currentData()
        note = self.note_edit.text().strip()

        try:
            purchase_service.pay_supplier(
                session=self.session,
                user=self.user,
                supplier_id=self.supplier.id,
                amount=amount_piasters,
                account_id=account_id,
                method="cash",
                note=note,
            )
            self.session.commit()
            show_toast(self, f"تم تسجيل سداد {val_text} ج.م للمورد {self.supplier.name} بنجاح!")
            self.accept()
        except Exception as e:
            self.session.rollback()
            show_error(self, message=f"تعذر تنفيذ السداد:\n{str(e)}")

