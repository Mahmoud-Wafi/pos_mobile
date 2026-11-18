"""Dialog for performing physical vs recorded wallet audit at shift or day close."""
from __future__ import annotations

from typing import Optional
from app.i18n import ar

from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QMessageBox, QFrame,
)

from app.ui.components import show_error, show_toast
from app.core.money import egp_to_piasters, format_money
from app.models.wallet import Wallet
from app.services import wallet_service
from app.ui.design.style import set_prop, style_label, variant
from app.ui.design import icons
from app.ui.design.tokens import COLORS


class WalletAuditDialog(QDialog):
    def __init__(self, session, user, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self.setWindowTitle(ar.WALLET_AUDIT_DIALOG_39F83F)
        self.resize(480, 420)
        self.setModal(True)

        self._build_ui()
        self._load_wallets()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        # Header
        hdr = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(icons.pixmap("scale", COLORS["primary"], 28))
        hdr.addWidget(icon)

        t_box = QVBoxLayout()
        t_box.setSpacing(2)
        lbl_t = QLabel(ar.WALLET_AUDIT_DIALOG_446804)
        style_label(lbl_t, size="title", tone="text", bold=True)
        lbl_sub = QLabel(ar.WALLET_AUDIT_DIALOG_F9068C)
        style_label(lbl_sub, size="caption", tone="muted")
        t_box.addWidget(lbl_t)
        t_box.addWidget(lbl_sub)
        hdr.addLayout(t_box)
        hdr.addStretch()
        layout.addLayout(hdr)

        # Select Wallet
        layout.addWidget(QLabel(ar.WALLET_AUDIT_DIALOG_396FB0))
        self.wallet_combo = QComboBox()
        self.wallet_combo.setFixedHeight(42)
        self.wallet_combo.currentIndexChanged.connect(self._on_wallet_changed)
        layout.addWidget(self.wallet_combo)

        # Current System Balance Card
        card = QFrame()
        set_prop(card, "banner", "info")
        c_layout = QHBoxLayout(card)
        c_title = QLabel(ar.WALLET_AUDIT_DIALOG_FE5280)
        style_label(c_title, tone="primary", bold=True)
        self.lbl_sys_bal = QLabel(ar.DAILY_CLOSE_DIALOG_388B15)
        style_label(self.lbl_sys_bal, size="title", tone="primary", bold=True)
        c_layout.addWidget(c_title)
        c_layout.addStretch()
        c_layout.addWidget(self.lbl_sys_bal)
        layout.addWidget(card)

        # Actual Balance Input
        layout.addWidget(QLabel(ar.WALLET_AUDIT_DIALOG_50E709))
        self.actual_edit = QLineEdit()
        self.actual_edit.setFixedHeight(42)
        self.actual_edit.setPlaceholderText(ar.WALLET_AUDIT_DIALOG_79DE28)
        self.actual_edit.setValidator(QDoubleValidator(0.0, 9999999.0, 2))
        self.actual_edit.textChanged.connect(self._recalc_diff)
        layout.addWidget(self.actual_edit)

        # Diff Card
        self.diff_card = QFrame()
        set_prop(self.diff_card, "card", True)
        d_layout = QHBoxLayout(self.diff_card)
        d_title = QLabel(ar.WALLET_AUDIT_DIALOG_2E3D7C)
        style_label(d_title, bold=True)
        self.lbl_diff = QLabel(ar.DAILY_CLOSE_DIALOG_388B15)
        style_label(self.lbl_diff, size="title", tone="success", bold=True)
        d_layout.addWidget(d_title)
        d_layout.addStretch()
        d_layout.addWidget(self.lbl_diff)
        layout.addWidget(self.diff_card)

        # Note
        layout.addWidget(QLabel(ar.WALLET_AUDIT_DIALOG_33325D))
        self.note_edit = QLineEdit()
        self.note_edit.setFixedHeight(40)
        self.note_edit.setPlaceholderText(ar.WALLET_AUDIT_DIALOG_F24530)
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

        btn_save = QPushButton(ar.STOCKTAKE_WIDGET_54E462)
        btn_save.setFixedHeight(42)
        variant(btn_save, "primary")
        btn_save.clicked.connect(self._save_audit)
        btn_box.addWidget(btn_save)

        layout.addLayout(btn_box)

    def _load_wallets(self):
        self.wallet_combo.clear()
        wallets = wallet_service.list_wallets(self.session, self.user, active_only=True)
        for w in wallets:
            self.wallet_combo.addItem(f"{w.label} - {w.phone_number}", w)

    def _on_wallet_changed(self):
        w: Optional[Wallet] = self.wallet_combo.currentData()
        if w:
            self.lbl_sys_bal.setText(format_money(w.balance))
            self._recalc_diff()

    def _recalc_diff(self):
        w: Optional[Wallet] = self.wallet_combo.currentData()
        if not w:
            return
        actual_str = self.actual_edit.text().strip()
        try:
            actual_piasters = egp_to_piasters(actual_str) if actual_str else w.balance
        except Exception:
            actual_piasters = w.balance

        diff_piasters = actual_piasters - w.balance
        self.lbl_diff.setText(format_money(diff_piasters))
        if diff_piasters < 0:
            style_label(self.lbl_diff, size="title", tone="danger", bold=True)
        elif diff_piasters > 0:
            style_label(self.lbl_diff, size="title", tone="primary", bold=True)
        else:
            style_label(self.lbl_diff, size="title", tone="success", bold=True)

    def _save_audit(self):
        w: Optional[Wallet] = self.wallet_combo.currentData()
        if not w:
            show_error(self, message=ar.WALLET_AUDIT_DIALOG_EDD8BE)
            return

        actual_str = self.actual_edit.text().strip()
        if not actual_str:
            show_error(self, message=ar.WALLET_AUDIT_DIALOG_B882CE)
            self.actual_edit.setFocus()
            return

        try:
            actual_piasters = egp_to_piasters(actual_str)
        except Exception:
            show_error(self, message=ar.WALLET_AUDIT_DIALOG_9536CA)
            return

        note = self.note_edit.text().strip()

        try:
            audit = wallet_service.audit_wallet(
                self.session, self.user,
                wallet_id=w.id,
                actual_balance=actual_piasters,
                note=note,
            )
            self.session.commit()
            show_toast(self, f"تم تدقيق وجرد المحفظة بنجاح.\nفرق الجرد: {format_money(audit.diff)}")
            self.accept()
        except Exception as e:
            self.session.rollback()
            show_error(self, message=f"تعذر تسجيل الجرد:\n{str(e)}")

