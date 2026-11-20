"""Dialog to create or edit an electronic wallet line."""
from __future__ import annotations
from app.i18n import ar
from app.ui.components.numeric import set_int_validator, set_money_validator

from typing import Optional
from PySide6.QtCore import Qt

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QMessageBox, QFrame, QGridLayout,
)

from app.ui.components import show_error
from app.core.money import egp_to_piasters, format_money, piasters_to_egp
from app.core.money import piasters_to_input
from app.models.wallet import Wallet
from app.services import wallet_service
from app.ui.design.style import set_prop, style_label, variant
from app.ui.design import icons
from app.ui.design.tokens import COLORS


class WalletDialog(QDialog):
    def __init__(self, session, user, wallet: Optional[Wallet] = None, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self.wallet = wallet
        self.setWindowTitle(ar.WALLET_DIALOG_EA5DB5 if wallet else ar.WALLET_DIALOG_160ECF)
        self.resize(520, 500)
        self.setModal(True)

        self._build_ui()
        if self.wallet:
            self._load_data()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        # Header
        hdr = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(icons.pixmap("wallet", COLORS["primary"], 28))
        hdr.addWidget(icon)

        t_box = QVBoxLayout()
        t_box.setSpacing(2)
        lbl_t = QLabel(ar.WALLET_DIALOG_1AFF6E if not self.wallet else ar.WALLET_DIALOG_1B2867)
        style_label(lbl_t, size="title", tone="text", bold=True)
        lbl_sub = QLabel(ar.WALLET_DIALOG_C7DF34)
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

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)

        # Network
        grid.addWidget(QLabel(ar.WALLET_DIALOG_5F02A8), 0, 0)
        self.net_combo = QComboBox()
        self.net_combo.setFixedHeight(42)
        self.net_combo.addItem(ar.WALLET_DIALOG_5C14ED, "vodafone")
        self.net_combo.addItem(ar.WALLET_DIALOG_F80DA6, "orange")
        self.net_combo.addItem(ar.WALLET_DIALOG_2AD49B, "etisalat")
        self.net_combo.addItem(ar.WALLET_DIALOG_FE3213, "we")
        self.net_combo.addItem(ar.WALLET_DIALOG_62B886, "instapay")
        grid.addWidget(self.net_combo, 1, 0)

        # Phone Number
        grid.addWidget(QLabel(ar.WALLET_DIALOG_A5F695), 0, 1)
        self.phone_edit = QLineEdit()
        self.phone_edit.setFixedHeight(42)
        self.phone_edit.setPlaceholderText("010xxxxxxx")
        grid.addWidget(self.phone_edit, 1, 1)

        # Label
        grid.addWidget(QLabel(ar.WALLET_DIALOG_B5DC3A), 2, 0, 1, 2)
        self.label_edit = QLineEdit()
        self.label_edit.setFixedHeight(42)
        self.label_edit.setPlaceholderText(ar.WALLET_DIALOG_5C7F4C)
        grid.addWidget(self.label_edit, 3, 0, 1, 2)

        # Initial Balance (only for new)
        if not self.wallet:
            grid.addWidget(QLabel(ar.WALLET_DIALOG_0A3E06), 4, 0)
            self.bal_edit = QLineEdit("0.00")
            self.bal_edit.setFixedHeight(42)
            set_money_validator(self.bal_edit, 0.0, 9999999.0)
            grid.addWidget(self.bal_edit, 5, 0)
        else:
            self.bal_edit = None

        # Daily Limit
        grid.addWidget(QLabel(ar.WALLET_DIALOG_B32436), 4 if not self.wallet else 4, 1 if not self.wallet else 0)
        self.daily_limit_edit = QLineEdit("30000.00")
        self.daily_limit_edit.setFixedHeight(42)
        set_money_validator(self.daily_limit_edit, 0.0, 9999999.0)
        grid.addWidget(self.daily_limit_edit, 5 if not self.wallet else 5, 1 if not self.wallet else 0)

        # Monthly Limit
        grid.addWidget(QLabel(ar.WALLET_DIALOG_5BB528), 6, 0)
        self.monthly_limit_edit = QLineEdit("100000.00")
        self.monthly_limit_edit.setFixedHeight(42)
        set_money_validator(self.monthly_limit_edit, 0.0, 9999999.0)
        grid.addWidget(self.monthly_limit_edit, 7, 0)

        layout.addLayout(grid)
        layout.addStretch()

        # Buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(12)

        btn_cancel = QPushButton(ar.CANCEL)
        btn_cancel.setFixedHeight(42)
        variant(btn_cancel, "secondary")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        self.btn_save = QPushButton(ar.WALLET_DIALOG_FFA690)
        self.btn_save.setFixedHeight(42)
        variant(self.btn_save, "primary")
        self.btn_save.clicked.connect(self._save)
        btn_box.addWidget(self.btn_save)

        layout.addLayout(btn_box)

    def _load_data(self):
        idx = self.net_combo.findData(self.wallet.network)
        if idx >= 0:
            self.net_combo.setCurrentIndex(idx)
        self.net_combo.setEnabled(False)  # network locked after creation
        self.phone_edit.setText(self.wallet.phone_number)
        self.phone_edit.setEnabled(False)
        self.label_edit.setText(self.wallet.label)
        self.daily_limit_edit.setText(f"{piasters_to_input(self.wallet.daily_limit)}")
        self.monthly_limit_edit.setText(f"{piasters_to_input(self.wallet.monthly_limit)}")

    def _save(self):
        label = self.label_edit.text().strip()
        if not label:
            show_error(self, message=ar.WALLET_DIALOG_655906)
            self.label_edit.setFocus()
            return

        try:
            d_limit = egp_to_piasters(self.daily_limit_edit.text() or 0)
            m_limit = egp_to_piasters(self.monthly_limit_edit.text() or 0)
        except Exception:
            show_error(self, message=ar.WALLET_DIALOG_EA0656)
            return

        try:
            if self.wallet:
                wallet_service.update_wallet(
                    self.session, self.user, self.wallet.id,
                    label=label, daily_limit=d_limit, monthly_limit=m_limit,
                )
            else:
                phone = self.phone_edit.text().strip()
                if not phone:
                    show_error(self, message=ar.WALLET_DIALOG_A69AA1)
                    self.phone_edit.setFocus()
                    return
                network = self.net_combo.currentData()
                init_bal = egp_to_piasters(self.bal_edit.text() or 0) if self.bal_edit else 0
                self.wallet = wallet_service.create_wallet(
                    self.session, self.user,
                    network=network, phone_number=phone, label=label,
                    initial_balance=init_bal, daily_limit=d_limit, monthly_limit=m_limit,
                )
            self.session.commit()
            self.accept()
        except Exception as e:
            self.session.rollback()
            show_error(self, message=f"تعذر حفظ المحفظة:\n{str(e)}")

