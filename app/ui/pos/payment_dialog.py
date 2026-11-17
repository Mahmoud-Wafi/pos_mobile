"""Split payment modal dialog for POS checkout."""
from __future__ import annotations

from decimal import Decimal

try:
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
        QLineEdit, QComboBox, QCheckBox, QMessageBox, QFrame, QGridLayout,
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QDoubleValidator
    HAS_QT = True
except ImportError:
    HAS_QT = False

from app.core.money import parse_egp_input
from app.core.money import format_money, egp_to_piasters
from app.core.money import piasters_to_input
from app.i18n import ar
from app.ui.design.style import set_prop, style_label, variant


if HAS_QT:
    class PaymentDialog(QDialog):
        """Split payment dialog supporting Cash, Mobile Wallets, InstaPay, and Credit."""

        def __init__(self, total_piasters: int, customer_name: str, parent=None):
            super().__init__(parent)
            self.total_piasters = total_piasters
            self.customer_name = customer_name
            self.payments_breakdown: list[dict] = []
            self.print_receipt = True
            self._cash_touched = False

            self.setWindowTitle("نافذة الدفع وتحصيل الفاتورة [F4]")
            self.setMinimumWidth(540)

            self._build_ui()

        def _build_ui(self):
            layout = QVBoxLayout(self)
            layout.setContentsMargins(24, 20, 24, 20)
            layout.setSpacing(16)

            # Header
            header = QHBoxLayout()
            title = QLabel("تحصيل قيمة الفاتورة")
            style_label(title, size="h2", tone="text", bold=True)
            header.addWidget(title)
            header.addStretch()

            cust_lbl = QLabel(f"العميل: {self.customer_name}")
            style_label(cust_lbl, size="caption", tone="muted", bold=True)
            header.addWidget(cust_lbl)
            layout.addLayout(header)

            # Total Banner
            total_card = QFrame()
            set_prop(total_card, "banner", "success")
            t_box = QHBoxLayout(total_card)
            t_lbl = QLabel("المبلغ المطلوب تحصيله:")
            style_label(t_lbl, size="title", tone="success", bold=True)
            self.val_total = QLabel(format_money(self.total_piasters))
            style_label(self.val_total, size="h2", tone="success", bold=True)
            t_box.addWidget(t_lbl)
            t_box.addStretch()
            t_box.addWidget(self.val_total)
            layout.addWidget(total_card)

            # Payment inputs grid
            grid = QGridLayout()
            grid.setHorizontalSpacing(16)
            grid.setVerticalSpacing(10)

            # 1. Cash (default gets full amount)
            lbl_cash = QLabel("نقداً (كاش - الدرج):")
            style_label(lbl_cash, tone="success", bold=True)
            self.cash_edit = QLineEdit(piasters_to_input(self.total_piasters))
            self.cash_edit.setValidator(QDoubleValidator(0.0, 9999999.0, 2))
            self.cash_edit.textChanged.connect(self._recalculate)
            self.cash_edit.textEdited.connect(lambda _t: setattr(self, "_cash_touched", True))

            # 2. Vodafone / Mobile Wallets
            lbl_wallet = QLabel("محفظة إلكترونية (فودافون/أورنج):")
            style_label(lbl_wallet, tone="info", bold=True)
            self.wallet_edit = QLineEdit("0")
            self.wallet_edit.setValidator(QDoubleValidator(0.0, 9999999.0, 2))
            self.wallet_edit.textChanged.connect(self._recalculate)
            self.wallet_edit.textEdited.connect(self._autofill_cash)

            # 3. InstaPay / Bank
            lbl_bank = QLabel("انستاباي / بنك (InstaPay):")
            style_label(lbl_bank, tone="primary", bold=True)
            self.bank_edit = QLineEdit("0")
            self.bank_edit.setValidator(QDoubleValidator(0.0, 9999999.0, 2))
            self.bank_edit.textChanged.connect(self._recalculate)
            self.bank_edit.textEdited.connect(self._autofill_cash)

            # 4. Credit (آجل)
            lbl_credit = QLabel("آجل (على الحساب):")
            style_label(lbl_credit, tone="warning", bold=True)
            self.credit_edit = QLineEdit("0")
            self.credit_edit.setValidator(QDoubleValidator(0.0, 9999999.0, 2))
            self.credit_edit.textChanged.connect(self._recalculate)
            self.credit_edit.textEdited.connect(self._autofill_cash)

            grid.addWidget(lbl_cash, 0, 0)
            grid.addWidget(self.cash_edit, 1, 0)

            grid.addWidget(lbl_wallet, 0, 1)
            grid.addWidget(self.wallet_edit, 1, 1)

            grid.addWidget(lbl_bank, 2, 0)
            grid.addWidget(self.bank_edit, 3, 0)

            grid.addWidget(lbl_credit, 2, 1)
            grid.addWidget(self.credit_edit, 3, 1)

            layout.addLayout(grid)

            # Quick cash buttons: exact amount + common notes
            quick = QHBoxLayout()
            quick.setSpacing(6)
            btn_exact = QPushButton(ar.QUICK_EXACT)
            btn_exact.setAutoDefault(False)
            btn_exact.clicked.connect(lambda: self._set_cash(self._remainder_piasters_excluding_cash()))
            quick.addWidget(btn_exact)
            for note in (50, 100, 200, 500, 1000):
                b = QPushButton(str(note))
                b.setAutoDefault(False)
                b.clicked.connect(lambda _=False, n=note: self._set_cash(n * 100))
                quick.addWidget(b)
            quick.addStretch()
            layout.addLayout(quick)

            # Summary Footer (Remaining / Change)
            self.status_card = QFrame()
            set_prop(self.status_card, "card", True)
            s_box = QHBoxLayout(self.status_card)
            self.lbl_rem_title = QLabel("المتبقي / الباقي للعميل:")
            style_label(self.lbl_rem_title, bold=True)
            self.lbl_rem_val = QLabel("0.00 ج.م")
            style_label(self.lbl_rem_val, size="title", tone="success", bold=True)
            s_box.addWidget(self.lbl_rem_title)
            s_box.addStretch()
            s_box.addWidget(self.lbl_rem_val)
            layout.addWidget(self.status_card)

            # Options
            self.chk_print = QCheckBox("طباعة إيصال الفاتورة بعد الحفظ مباشرة")
            self.chk_print.setChecked(True)
            layout.addWidget(self.chk_print)

            # Buttons
            btn_box = QHBoxLayout()
            btn_box.setSpacing(12)
            btn_box.addStretch()

            btn_cancel = QPushButton("إلغاء [Esc]")
            btn_cancel.setFixedHeight(44)
            btn_cancel.setMinimumWidth(110)
            btn_cancel.clicked.connect(self.reject)

            self.btn_confirm = QPushButton("تأكيد الدفع وطباعة الفاتورة [Enter]")
            self.btn_confirm.setFixedHeight(44)
            self.btn_confirm.setMinimumWidth(240)
            variant(self.btn_confirm, "success")
            self.btn_confirm.clicked.connect(self._confirm)
            self.btn_confirm.setDefault(True)
            btn_cancel.setAutoDefault(False)
            self.cash_edit.setFocus()
            self.cash_edit.selectAll()

            btn_box.addWidget(btn_cancel)
            btn_box.addWidget(self.btn_confirm)
            layout.addLayout(btn_box)

            self._recalculate()

        def _other_methods_piasters(self) -> int:
            total = Decimal("0")
            for e in (self.wallet_edit, self.bank_edit, self.credit_edit):
                total += self._get_val(e)
            return int(total * 100)

        def _remainder_piasters_excluding_cash(self) -> int:
            return max(0, self.total_piasters - self._other_methods_piasters())

        def _set_cash(self, piasters: int) -> None:
            self._cash_touched = True
            self.cash_edit.setText(piasters_to_input(piasters))
            self.btn_confirm.setFocus()

        def _autofill_cash(self, _text: str = "") -> None:
            """Cash takes whatever the other methods leave, until the cashier types it."""
            if not self._cash_touched:
                self.cash_edit.setText(piasters_to_input(self._remainder_piasters_excluding_cash()))

        def _confirm_if_enabled(self) -> None:
            if self.btn_confirm.isEnabled():
                self._confirm()

        def _get_val(self, edit: QLineEdit) -> Decimal:
            try:
                return Decimal(parse_egp_input(edit.text() or "0")) / Decimal(100)
            except ValueError:
                return Decimal("0")

        def _recalculate(self):
            cash = self._get_val(self.cash_edit)
            wallet = self._get_val(self.wallet_edit)
            bank = self._get_val(self.bank_edit)
            credit = self._get_val(self.credit_edit)

            total_entered = cash + wallet + bank + credit
            total_required = Decimal(self.total_piasters) / Decimal(100)
            diff = total_entered - total_required

            if diff == 0:
                self.lbl_rem_title.setText("المبلغ مدفوع بالكامل:")
                self.lbl_rem_val.setText("مطابق 100% ")
                style_label(self.lbl_rem_val, size="title", tone="success", bold=True)
                set_prop(self.status_card, "banner", "success")
                self.btn_confirm.setEnabled(True)
            elif diff > 0:
                self.lbl_rem_title.setText(ar.CHANGE_DUE + " (فكة):")
                self.lbl_rem_val.setText(f"{diff:,.2f} ج.م")
                style_label(self.lbl_rem_val, size="h2", tone="info", bold=True)
                set_prop(self.status_card, "banner", "info")
                self.btn_confirm.setEnabled(True)
            else:
                deficit = abs(diff)
                self.lbl_rem_title.setText("مبلغ غير مغطى (عجز):")
                self.lbl_rem_val.setText(f"-{deficit:,.2f} ج.م")
                style_label(self.lbl_rem_val, size="title", tone="danger", bold=True)
                set_prop(self.status_card, "banner", "danger")
                self.btn_confirm.setEnabled(False)

        def _confirm(self):
            cash = self._get_val(self.cash_edit)
            wallet = self._get_val(self.wallet_edit)
            bank = self._get_val(self.bank_edit)
            credit = self._get_val(self.credit_edit)

            self.payments_breakdown = []
            if cash > 0:
                self.payments_breakdown.append({"method": "cash", "amount": egp_to_piasters(cash)})
            if wallet > 0:
                self.payments_breakdown.append({"method": "vodafone", "amount": egp_to_piasters(wallet)})
            if bank > 0:
                self.payments_breakdown.append({"method": "instapay", "amount": egp_to_piasters(bank)})
            if credit > 0:
                self.payments_breakdown.append({"method": "credit", "amount": egp_to_piasters(credit)})

            self.print_receipt = self.chk_print.isChecked()
            self.accept()

