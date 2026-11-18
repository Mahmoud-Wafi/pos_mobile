"""Dialog to create or edit customer profiles and credit limits."""
from __future__ import annotations
from app.i18n import ar

from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QFrame, QTextEdit,
)

from app.ui.components import show_error
from app.core.money import egp_to_piasters, format_money
from app.core.money import piasters_to_input
from app.models.customer import Customer
from app.services import customer_service
from app.ui.design.style import set_prop, style_label, variant
from app.ui.design import icons
from app.ui.design.tokens import COLORS


class CustomerDialog(QDialog):
    def __init__(self, session, user, customer: Optional[Customer] = None, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self.customer = customer
        self.setWindowTitle(ar.CUSTOMER_DIALOG_4672E5 if customer else ar.CUSTOMER_DIALOG_2E94C6)
        self.resize(480, 460)
        self.setModal(True)

        self._build_ui()
        if self.customer:
            self._load_data()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        # Header
        hdr = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(icons.pixmap("user", COLORS["primary"], 28))
        hdr.addWidget(icon)

        t_box = QVBoxLayout()
        t_box.setSpacing(2)
        lbl_t = QLabel(ar.CUSTOMER_DIALOG_F8798B if not self.customer else ar.CUSTOMER_DIALOG_502992)
        style_label(lbl_t, size="title", tone="text", bold=True)
        lbl_sub = QLabel(ar.CUSTOMER_DIALOG_5E6FF5)
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

        # Name
        layout.addWidget(QLabel(ar.CUSTOMER_DIALOG_36E964))
        self.name_edit = QLineEdit()
        self.name_edit.setFixedHeight(42)
        self.name_edit.setPlaceholderText(ar.CUSTOMER_DIALOG_C73AA0)
        layout.addWidget(self.name_edit)

        # Phone
        layout.addWidget(QLabel(ar.CUSTOMER_DIALOG_251531))
        self.phone_edit = QLineEdit()
        self.phone_edit.setFixedHeight(42)
        self.phone_edit.setPlaceholderText("010/011/012/015...")
        layout.addWidget(self.phone_edit)

        # Credit Limit
        layout.addWidget(QLabel(ar.CUSTOMER_DIALOG_C7A4B0))
        self.credit_edit = QLineEdit("0.00")
        self.credit_edit.setFixedHeight(42)
        self.credit_edit.setValidator(QDoubleValidator(0.0, 9999999.0, 2))
        layout.addWidget(self.credit_edit)

        # Notes
        layout.addWidget(QLabel(ar.CUSTOMER_DIALOG_93F16C))
        self.notes_edit = QTextEdit()
        self.notes_edit.setFixedHeight(70)
        self.notes_edit.setPlaceholderText(ar.CUSTOMER_DIALOG_491235)
        layout.addWidget(self.notes_edit)

        layout.addStretch()

        # Buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(12)

        btn_cancel = QPushButton(ar.CANCEL)
        btn_cancel.setFixedHeight(42)
        variant(btn_cancel, "secondary")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_save = QPushButton(ar.CUSTOMER_DIALOG_E8ABC9)
        btn_save.setFixedHeight(42)
        variant(btn_save, "primary")
        btn_save.clicked.connect(self._save)
        btn_box.addWidget(btn_save)

        layout.addLayout(btn_box)

    def _load_data(self):
        self.name_edit.setText(self.customer.name or "")
        self.phone_edit.setText(self.customer.phone or "")
        self.credit_edit.setText(f"{piasters_to_input(self.customer.credit_limit)}")
        self.notes_edit.setPlainText(self.customer.notes or "")

    def _save(self):
        name = self.name_edit.text().strip()
        if not name:
            show_error(self, message=ar.CUSTOMER_DIALOG_7B284C)
            self.name_edit.setFocus()
            return

        phone = self.phone_edit.text().strip()
        try:
            limit_piasters = egp_to_piasters(self.credit_edit.text() or 0)
        except Exception:
            show_error(self, message=ar.CUSTOMER_DIALOG_6E1FCE)
            return

        notes = self.notes_edit.toPlainText().strip()

        try:
            if self.customer:
                customer_service.update_customer(
                    self.session, self.user, self.customer.id,
                    name=name, phone=phone, credit_limit=limit_piasters, notes=notes,
                )
            else:
                self.customer = customer_service.create_customer(
                    self.session, self.user,
                    name=name, phone=phone, credit_limit=limit_piasters, notes=notes,
                )
            self.session.commit()
            self.accept()
        except Exception as e:
            self.session.rollback()
            show_error(self, message=f"تعذر حفظ العميل:\n{str(e)}")

