"""Dialog to create or edit an electronic wallet line."""
from __future__ import annotations

from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
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
        self.setWindowTitle("تعديل محفظة" if wallet else "إضافة خط محفظة جديد")
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
        lbl_t = QLabel("بيانات خط المحفظة الإلكترونية" if not self.wallet else "تعديل المحفظة")
        style_label(lbl_t, size="title", tone="text", bold=True)
        lbl_sub = QLabel("ربط الخط بالشبكة وتحديد الحدود اليومية والشهرية لحمايتها من الإيقاف")
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
        grid.addWidget(QLabel("الشبكة / المزود: *"), 0, 0)
        self.net_combo = QComboBox()
        self.net_combo.setFixedHeight(42)
        self.net_combo.addItem("فودافون كاش (Vodafone Cash)", "vodafone")
        self.net_combo.addItem("أورنج موني (Orange Money)", "orange")
        self.net_combo.addItem("اتصالات كاش (Etisalat Cash)", "etisalat")
        self.net_combo.addItem("وي باي (WE Pay)", "we")
        self.net_combo.addItem("إنستاباي (InstaPay)", "instapay")
        grid.addWidget(self.net_combo, 1, 0)

        # Phone Number
        grid.addWidget(QLabel("رقم الخط / الموبايل: *"), 0, 1)
        self.phone_edit = QLineEdit()
        self.phone_edit.setFixedHeight(42)
        self.phone_edit.setPlaceholderText("010xxxxxxx")
        grid.addWidget(self.phone_edit, 1, 1)

        # Label
        grid.addWidget(QLabel("اسم مميز للخط / مسمى المحفظة: *"), 2, 0, 1, 2)
        self.label_edit = QLineEdit()
        self.label_edit.setFixedHeight(42)
        self.label_edit.setPlaceholderText("مثال: فودافون كاش خط البيع 1 أو إنستاباي المحل")
        grid.addWidget(self.label_edit, 3, 0, 1, 2)

        # Initial Balance (only for new)
        if not self.wallet:
            grid.addWidget(QLabel("الرصيد الافتتاحي (ج.م):"), 4, 0)
            self.bal_edit = QLineEdit("0.00")
            self.bal_edit.setFixedHeight(42)
            self.bal_edit.setValidator(QDoubleValidator(0.0, 9999999.0, 2))
            grid.addWidget(self.bal_edit, 5, 0)
        else:
            self.bal_edit = None

        # Daily Limit
        grid.addWidget(QLabel("الحد اليومي (ج.م):"), 4 if not self.wallet else 4, 1 if not self.wallet else 0)
        self.daily_limit_edit = QLineEdit("30000.00")
        self.daily_limit_edit.setFixedHeight(42)
        self.daily_limit_edit.setValidator(QDoubleValidator(0.0, 9999999.0, 2))
        grid.addWidget(self.daily_limit_edit, 5 if not self.wallet else 5, 1 if not self.wallet else 0)

        # Monthly Limit
        grid.addWidget(QLabel("الحد الشهري (ج.م):"), 6, 0)
        self.monthly_limit_edit = QLineEdit("100000.00")
        self.monthly_limit_edit.setFixedHeight(42)
        self.monthly_limit_edit.setValidator(QDoubleValidator(0.0, 9999999.0, 2))
        grid.addWidget(self.monthly_limit_edit, 7, 0)

        layout.addLayout(grid)
        layout.addStretch()

        # Buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(12)

        btn_cancel = QPushButton("إلغاء")
        btn_cancel.setFixedHeight(42)
        variant(btn_cancel, "secondary")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        self.btn_save = QPushButton("حفظ المحفظة")
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
            show_error(self, message="يرجى كتابة اسم أو مسمى المحفظة")
            self.label_edit.setFocus()
            return

        try:
            d_limit = egp_to_piasters(self.daily_limit_edit.text() or 0)
            m_limit = egp_to_piasters(self.monthly_limit_edit.text() or 0)
        except Exception:
            show_error(self, message="صيغة الحدود اليومية أو الشهرية غير صحيحة")
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
                    show_error(self, message="يرجى كتابة رقم الهاتف للخط")
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

