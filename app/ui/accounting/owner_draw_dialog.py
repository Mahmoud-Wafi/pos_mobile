"""Dialog for recording owner draws / profit withdrawals."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QMessageBox, QFrame,
)

from app.ui.components import show_error, show_toast
from app.core.money import egp_to_piasters, format_money
from app.services import accounting_service
from app.ui.design.style import set_prop, style_label, variant
from app.ui.design import icons
from app.ui.design.tokens import COLORS


class OwnerDrawDialog(QDialog):
    def __init__(self, session, user, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self.setWindowTitle("سحب أرباح المالك (Owner Draw)")
        self.resize(480, 400)
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
        icon.setPixmap(icons.pixmap("banknote", COLORS["primary"], 28))
        hdr.addWidget(icon)

        t_box = QVBoxLayout()
        t_box.setSpacing(2)
        lbl_t = QLabel("سحب نقدي للمالك")
        style_label(lbl_t, size="title", tone="text", bold=True)
        lbl_sub = QLabel("مسحوبات شخصية منفصلة تماماً عن مصروفات تشغيل المحل")
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

        # Account
        layout.addWidget(QLabel("الخزينة المسحوب منها: *"))
        self.acc_combo = QComboBox()
        self.acc_combo.setFixedHeight(42)
        layout.addWidget(self.acc_combo)

        # Amount
        layout.addWidget(QLabel("مبلغ السحب (ج.م): *"))
        self.amount_edit = QLineEdit()
        self.amount_edit.setFixedHeight(42)
        self.amount_edit.setPlaceholderText("0.00 ج.م")
        self.amount_edit.setValidator(QDoubleValidator(0.01, 9999999.0, 2))
        layout.addWidget(self.amount_edit)

        # Notes
        layout.addWidget(QLabel("بيان أو ملاحظات السحب:"))
        self.note_edit = QLineEdit()
        self.note_edit.setFixedHeight(40)
        self.note_edit.setPlaceholderText("سحب أرباح شخصية / دفعة تحت حساب الأرباح...")
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

        btn_save = QPushButton("تأكيد سحب المالك")
        btn_save.setFixedHeight(42)
        variant(btn_save, "primary")
        btn_save.clicked.connect(self._save)
        btn_box.addWidget(btn_save)

        layout.addLayout(btn_box)

    def _load_accounts(self):
        self.acc_combo.clear()
        accounts = accounting_service.list_accounts(self.session, self.user)
        for a in accounts:
            self.acc_combo.addItem(f"{a.name} ({format_money(a.balance)})", a.id)

    def _save(self):
        acc_id = self.acc_combo.currentData()
        amt_str = self.amount_edit.text().strip()
        if not amt_str:
            show_error(self, message="يرجى كتابة مبلغ السحب")
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

        note = self.note_edit.text().strip()

        try:
            accounting_service.owner_draw(
                self.session, self.user,
                amount=amt_piasters,
                account_id=acc_id,
                note=note,
            )
            self.session.commit()
            show_toast(self, f"تم تسجيل سحب للمالك بقيمة {amt_str} ج.م بنجاح!")
            self.accept()
        except Exception as e:
            self.session.rollback()
            show_error(self, message=f"تعذر تنفيذ سحب المالك:\n{str(e)}")

