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

from app.core.money import format_money, egp_to_piasters


if HAS_QT:
    class PaymentDialog(QDialog):
        """Split payment dialog supporting Cash, Mobile Wallets, InstaPay, and Credit."""

        def __init__(self, total_piasters: int, customer_name: str, parent=None):
            super().__init__(parent)
            self.total_piasters = total_piasters
            self.customer_name = customer_name
            self.payments_breakdown: list[dict] = []
            self.print_receipt = True

            self.setWindowTitle("نافذة الدفع وتحصيل الفاتورة [F4]")
            self.setMinimumWidth(540)
            self.setStyleSheet("""
                QDialog {
                    background-color: #FFFFFF;
                }
                QLabel {
                    color: #1E293B;
                    font-size: 13px;
                }
                QLineEdit, QComboBox {
                    background-color: #F8FAFC;
                    border: 1px solid #CBD5E1;
                    border-radius: 8px;
                    padding: 8px 12px;
                    font-size: 14px;
                    font-weight: bold;
                    color: #0F172A;
                }
                QLineEdit:focus, QComboBox:focus {
                    background-color: #FFFFFF;
                    border: 2px solid #059669;
                }
            """)
            self._build_ui()

        def _build_ui(self):
            layout = QVBoxLayout(self)
            layout.setContentsMargins(24, 20, 24, 20)
            layout.setSpacing(16)

            # Header
            header = QHBoxLayout()
            title = QLabel("💳 تحصيل قيمة الفاتورة")
            title.setStyleSheet("font-size: 18px; font-weight: bold; color: #0F172A;")
            header.addWidget(title)
            header.addStretch()

            cust_lbl = QLabel(f"العميل: {self.customer_name}")
            cust_lbl.setStyleSheet("color: #64748B; font-weight: 600; font-size: 12px;")
            header.addWidget(cust_lbl)
            layout.addLayout(header)

            # Total Banner
            total_card = QFrame()
            total_card.setStyleSheet("background-color: #F0FDF4; border: 1px solid #BBF7D0; border-radius: 10px; padding: 12px;")
            t_box = QHBoxLayout(total_card)
            t_lbl = QLabel("المبلغ المطلوب تحصيله:")
            t_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #166534;")
            self.val_total = QLabel(format_money(self.total_piasters))
            self.val_total.setStyleSheet("font-size: 20px; font-weight: 800; color: #15803D;")
            t_box.addWidget(t_lbl)
            t_box.addStretch()
            t_box.addWidget(self.val_total)
            layout.addWidget(total_card)

            # Payment inputs grid
            grid = QGridLayout()
            grid.setHorizontalSpacing(16)
            grid.setVerticalSpacing(10)

            # 1. Cash (default gets full amount)
            lbl_cash = QLabel("💵 نقداً (كاش - الدرج):")
            lbl_cash.setStyleSheet("font-weight: bold; color: #059669;")
            self.cash_edit = QLineEdit(str(self.total_piasters / 100))
            self.cash_edit.setValidator(QDoubleValidator(0.0, 9999999.0, 2))
            self.cash_edit.textChanged.connect(self._recalculate)

            # 2. Vodafone / Mobile Wallets
            lbl_wallet = QLabel("📱 محفظة إلكترونية (فودافون/أورنج):")
            lbl_wallet.setStyleSheet("font-weight: bold; color: #0284C7;")
            self.wallet_edit = QLineEdit("0")
            self.wallet_edit.setValidator(QDoubleValidator(0.0, 9999999.0, 2))
            self.wallet_edit.textChanged.connect(self._recalculate)

            # 3. InstaPay / Bank
            lbl_bank = QLabel("🏦 انستاباي / بنك (InstaPay):")
            lbl_bank.setStyleSheet("font-weight: bold; color: #6366F1;")
            self.bank_edit = QLineEdit("0")
            self.bank_edit.setValidator(QDoubleValidator(0.0, 9999999.0, 2))
            self.bank_edit.textChanged.connect(self._recalculate)

            # 4. Credit (آجل)
            lbl_credit = QLabel("⏳ آجل (على الحساب):")
            lbl_credit.setStyleSheet("font-weight: bold; color: #D97706;")
            self.credit_edit = QLineEdit("0")
            self.credit_edit.setValidator(QDoubleValidator(0.0, 9999999.0, 2))
            self.credit_edit.textChanged.connect(self._recalculate)

            grid.addWidget(lbl_cash, 0, 0)
            grid.addWidget(self.cash_edit, 1, 0)

            grid.addWidget(lbl_wallet, 0, 1)
            grid.addWidget(self.wallet_edit, 1, 1)

            grid.addWidget(lbl_bank, 2, 0)
            grid.addWidget(self.bank_edit, 3, 0)

            grid.addWidget(lbl_credit, 2, 1)
            grid.addWidget(self.credit_edit, 3, 1)

            layout.addLayout(grid)

            # Summary Footer (Remaining / Change)
            self.status_card = QFrame()
            self.status_card.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 10px;")
            s_box = QHBoxLayout(self.status_card)
            self.lbl_rem_title = QLabel("المتبقي / الباقي للعميل:")
            self.lbl_rem_title.setStyleSheet("font-weight: bold;")
            self.lbl_rem_val = QLabel("0.00 ج.م")
            self.lbl_rem_val.setStyleSheet("font-weight: bold; font-size: 16px; color: #059669;")
            s_box.addWidget(self.lbl_rem_title)
            s_box.addStretch()
            s_box.addWidget(self.lbl_rem_val)
            layout.addWidget(self.status_card)

            # Options
            self.chk_print = QCheckBox("🖨️ طباعة إيصال الفاتورة بعد الحفظ مباشرة")
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
            self.btn_confirm.setStyleSheet("""
                QPushButton {
                    background-color: #059669;
                    color: #FFFFFF;
                    font-size: 14px;
                    font-weight: bold;
                    border: none;
                    border-radius: 8px;
                    padding: 0 20px;
                }
                QPushButton:hover {
                    background-color: #047857;
                }
            """)
            self.btn_confirm.clicked.connect(self._confirm)

            btn_box.addWidget(btn_cancel)
            btn_box.addWidget(self.btn_confirm)
            layout.addLayout(btn_box)

            self._recalculate()

        def _get_val(self, edit: QLineEdit) -> Decimal:
            try:
                return Decimal(edit.text().strip() or "0")
            except Exception:
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
                self.lbl_rem_val.setText("مطابق 100% ✓")
                self.lbl_rem_val.setStyleSheet("font-weight: bold; font-size: 15px; color: #059669;")
                self.status_card.setStyleSheet("background-color: #F0FDF4; border: 1px solid #BBF7D0; border-radius: 8px; padding: 10px;")
                self.btn_confirm.setEnabled(True)
            elif diff > 0:
                self.lbl_rem_title.setText("الباقي للعميل (فكة):")
                self.lbl_rem_val.setText(f"{diff:,.2f} ج.م")
                self.lbl_rem_val.setStyleSheet("font-weight: bold; font-size: 16px; color: #0284C7;")
                self.status_card.setStyleSheet("background-color: #F0F9FF; border: 1px solid #BAE6FD; border-radius: 8px; padding: 10px;")
                self.btn_confirm.setEnabled(True)
            else:
                deficit = abs(diff)
                self.lbl_rem_title.setText("مبلغ غير مغطى (عجز):")
                self.lbl_rem_val.setText(f"-{deficit:,.2f} ج.م")
                self.lbl_rem_val.setStyleSheet("font-weight: bold; font-size: 16px; color: #DC2626;")
                self.status_card.setStyleSheet("background-color: #FEF2F2; border: 1px solid #FECACA; border-radius: 8px; padding: 10px;")
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

