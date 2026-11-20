"""Dialog for transferring cash between accounts (e.g. Drawer -> Safe, Safe -> Bank)."""
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
from app.models.accounting import CashAccount
from app.services import accounting_service
from app.ui.design.style import set_prop, style_label, variant
from app.ui.design import icons
from app.ui.design.tokens import COLORS


class TransferDialog(QDialog):
    def __init__(self, session, user, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self.setWindowTitle(ar.TRANSFER_DIALOG_A45046)
        self.resize(480, 420)
        self.setModal(True)

        self._build_ui()
        self._load_accounts()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        # Header
        hdr = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(icons.pixmap("rotate-ccw", COLORS["primary"], 28))
        hdr.addWidget(icon)

        t_box = QVBoxLayout()
        t_box.setSpacing(2)
        lbl_t = QLabel(ar.TRANSFER_DIALOG_8F62F9)
        style_label(lbl_t, size="title", tone="text", bold=True)
        lbl_sub = QLabel(ar.TRANSFER_DIALOG_744014)
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

        # From Account
        layout.addWidget(QLabel(ar.TRANSFER_DIALOG_E0797A))
        self.from_combo = QComboBox()
        self.from_combo.setFixedHeight(42)
        layout.addWidget(self.from_combo)

        # To Account
        layout.addWidget(QLabel(ar.TRANSFER_DIALOG_15BE4F))
        self.to_combo = QComboBox()
        self.to_combo.setFixedHeight(42)
        layout.addWidget(self.to_combo)

        # Amount
        layout.addWidget(QLabel(ar.TRANSFER_DIALOG_4619D6))
        self.amount_edit = QLineEdit()
        self.amount_edit.setFixedHeight(42)
        self.amount_edit.setPlaceholderText(ar.DAILY_CLOSE_DIALOG_388B15)
        set_money_validator(self.amount_edit, 0.01, 9999999.0)
        layout.addWidget(self.amount_edit)

        # Notes
        layout.addWidget(QLabel(ar.TRANSFER_DIALOG_790957))
        self.note_edit = QLineEdit()
        self.note_edit.setFixedHeight(40)
        self.note_edit.setPlaceholderText(ar.TRANSFER_DIALOG_DAE0D4)
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

        btn_transfer = QPushButton(ar.TRANSFER_DIALOG_5C8600)
        btn_transfer.setFixedHeight(42)
        variant(btn_transfer, "primary")
        btn_transfer.clicked.connect(self._transfer)
        btn_box.addWidget(btn_transfer)

        layout.addLayout(btn_box)

    def _load_accounts(self):
        self.from_combo.clear()
        self.to_combo.clear()
        accounts = accounting_service.list_accounts(self.session, self.user)
        for a in accounts:
            label = f"{a.name} ({format_money(a.balance)})"
            self.from_combo.addItem(label, a.id)
            self.to_combo.addItem(label, a.id)

        if len(accounts) >= 2:
            self.to_combo.setCurrentIndex(1)

    def _transfer(self):
        from_id = self.from_combo.currentData()
        to_id = self.to_combo.currentData()

        if from_id == to_id:
            show_error(self, message=ar.TRANSFER_DIALOG_B2AFB0)
            return

        amt_str = self.amount_edit.text().strip()
        if not amt_str:
            show_error(self, message=ar.TRANSFER_DIALOG_30CF4A)
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

        note = self.note_edit.text().strip()

        try:
            accounting_service.transfer(
                self.session, self.user,
                from_account_id=from_id,
                to_account_id=to_id,
                amount=amt_piasters,
                note=note,
            )
            self.session.commit()
            show_toast(self, f"تم تحويل {amt_str} ج.م بنجاح بين الحسابين!")
            self.accept()
        except Exception as e:
            self.session.rollback()
            show_error(self, message=f"تعذر إتمام التحويل:\n{str(e)}")

