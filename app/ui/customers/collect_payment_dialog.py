"""Dialog for collecting customer debts and recording payments."""
from __future__ import annotations
from app.i18n import ar
from app.ui.components.numeric import set_int_validator, set_money_validator

from PySide6.QtCore import Qt

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QMessageBox, QFrame,
)

from app.ui.components import show_error, show_toast
from app.core.money import egp_to_piasters, format_money
from app.core.money import piasters_to_input
from app.models.accounting import CashAccount
from app.models.customer import Customer
from app.services import customer_service
from app.ui.design.style import set_prop, style_label, variant
from app.ui.design import icons
from app.ui.design.tokens import COLORS


class CollectPaymentDialog(QDialog):
    def __init__(self, session, user, customer: Customer, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self.customer = customer
        self.setWindowTitle(f"تحصيل دفعة من العميل: {customer.name}")
        self.resize(480, 440)
        self.setModal(True)

        self._build_ui()

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
        lbl_t = QLabel(f"تحصيل دفعة نقدية: {self.customer.name}")
        style_label(lbl_t, size="title", tone="text", bold=True)
        lbl_sub = QLabel(ar.COLLECT_PAYMENT_DIALOG_98B59B)
        style_label(lbl_sub, size="caption", tone="muted")
        t_box.addWidget(lbl_t)
        t_box.addWidget(lbl_sub)
        hdr.addLayout(t_box)
        hdr.addStretch()
        layout.addLayout(hdr)

        # Current Debt Card
        card = QFrame()
        set_prop(card, "banner", "danger")
        c_layout = QHBoxLayout(card)
        c_title = QLabel(ar.COLLECT_PAYMENT_DIALOG_21996B)
        style_label(c_title, tone="danger", bold=True)
        self.lbl_debt = QLabel(format_money(self.customer.balance))
        style_label(self.lbl_debt, size="h2", tone="danger", bold=True)
        c_layout.addWidget(c_title)
        c_layout.addStretch()
        c_layout.addWidget(self.lbl_debt)
        layout.addWidget(card)

        # Amount
        layout.addWidget(QLabel(ar.COLLECT_PAYMENT_DIALOG_0D2766))
        self.amount_edit = QLineEdit()
        self.amount_edit.setFixedHeight(42)
        self.amount_edit.setPlaceholderText(f"أقصى تحصيل: {piasters_to_input(self.customer.balance)} ج.م")
        set_money_validator(self.amount_edit, 0.01, 9999999.0)
        layout.addWidget(self.amount_edit)

        # Method / Cash Account
        layout.addWidget(QLabel(ar.COLLECT_PAYMENT_DIALOG_077DD3))
        self.acc_combo = QComboBox()
        self.acc_combo.setFixedHeight(42)
        accounts = self.session.query(CashAccount).all()
        for a in accounts:
            self.acc_combo.addItem(f"{a.name} ({format_money(a.balance)})", a.id)
        layout.addWidget(self.acc_combo)

        # Notes
        layout.addWidget(QLabel(ar.COLLECT_PAYMENT_DIALOG_63CDD3))
        self.note_edit = QLineEdit()
        self.note_edit.setFixedHeight(40)
        self.note_edit.setPlaceholderText(ar.COLLECT_PAYMENT_DIALOG_270E81)
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

        btn_save = QPushButton(ar.COLLECT_PAYMENT_DIALOG_688032)
        btn_save.setFixedHeight(42)
        variant(btn_save, "success")
        btn_save.clicked.connect(self._collect)
        btn_box.addWidget(btn_save)

        layout.addLayout(btn_box)

    def _collect(self):
        amt_str = self.amount_edit.text().strip()
        if not amt_str:
            show_error(self, message=ar.COLLECT_PAYMENT_DIALOG_AD51F4)
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
            customer_service.collect_payment(
                session=self.session,
                user=self.user,
                customer_id=self.customer.id,
                amount_piasters=amt_piasters,
                method="cash",
                account_id=acc_id,
                notes=note,
            )
            self.session.commit()
            show_toast(self, f"تم تحصيل {amt_str} ج.م من العميل {self.customer.name} بنجاح!\nالمتبقي عليه: {format_money(self.customer.balance)}")
            self.accept()
        except Exception as e:
            self.session.rollback()
            show_error(self, message=f"تعذر تسجيل التحصيل:\n{str(e)}")

