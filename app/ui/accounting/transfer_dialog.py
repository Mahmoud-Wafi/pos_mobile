"""Dialog for transferring cash between accounts (e.g. Drawer -> Safe, Safe -> Bank)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QMessageBox, QFrame,
)

from app.core.money import egp_to_piasters, format_money
from app.models.accounting import CashAccount
from app.services import accounting_service


class TransferDialog(QDialog):
    def __init__(self, session, user, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self.setWindowTitle("تحويل نقدية بين الحسابات")
        self.resize(480, 420)
        self.setModal(True)
        self.setStyleSheet("""
            QDialog {
                background-color: #FFFFFF;
            }
            QLabel {
                color: #0F172A;
                font-size: 13px;
                font-weight: 600;
            }
            QLineEdit, QComboBox {
                background-color: #F8FAFC;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                padding: 10px 12px;
                font-size: 13px;
                color: #0F172A;
            }
            QLineEdit:focus, QComboBox:focus {
                background-color: #FFFFFF;
                border: 2px solid #2563EB;
            }
        """)
        self._build_ui()
        self._load_accounts()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        # Header
        hdr = QHBoxLayout()
        icon = QLabel("🔄")
        icon.setStyleSheet("font-size: 28px;")
        hdr.addWidget(icon)

        t_box = QVBoxLayout()
        t_box.setSpacing(2)
        lbl_t = QLabel("تحويل رصيد داخلي")
        lbl_t.setStyleSheet("font-size: 16px; font-weight: bold; color: #0F172A;")
        lbl_sub = QLabel("نقل الأموال بين الدرج والخزنة أو الحساب البنكي بحركة مزدوجة مؤمنة")
        lbl_sub.setStyleSheet("font-size: 12px; color: #64748B; font-weight: normal;")
        t_box.addWidget(lbl_t)
        t_box.addWidget(lbl_sub)
        hdr.addLayout(t_box)
        hdr.addStretch()
        layout.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #E2E8F0;")
        layout.addWidget(sep)

        # From Account
        layout.addWidget(QLabel("من حساب (المرسل): *"))
        self.from_combo = QComboBox()
        self.from_combo.setFixedHeight(42)
        layout.addWidget(self.from_combo)

        # To Account
        layout.addWidget(QLabel("إلى حساب (المستلم): *"))
        self.to_combo = QComboBox()
        self.to_combo.setFixedHeight(42)
        layout.addWidget(self.to_combo)

        # Amount
        layout.addWidget(QLabel("مبلغ التحويل (ج.م): *"))
        self.amount_edit = QLineEdit()
        self.amount_edit.setFixedHeight(42)
        self.amount_edit.setPlaceholderText("0.00 ج.م")
        self.amount_edit.setValidator(QDoubleValidator(0.01, 9999999.0, 2))
        layout.addWidget(self.amount_edit)

        # Notes
        layout.addWidget(QLabel("سبب أو بيان التحويل:"))
        self.note_edit = QLineEdit()
        self.note_edit.setFixedHeight(40)
        self.note_edit.setPlaceholderText("مثال: توريد نقدية المساء من الدرج إلى الخزنة...")
        layout.addWidget(self.note_edit)

        layout.addStretch()

        # Buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(12)

        btn_cancel = QPushButton("إلغاء")
        btn_cancel.setFixedHeight(42)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #F1F5F9;
                color: #475569;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                font-weight: 600;
                padding: 0 18px;
            }
        """)
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_transfer = QPushButton("🔄 تأكيد التحويل")
        btn_transfer.setFixedHeight(42)
        btn_transfer.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: white;
                border-radius: 8px;
                font-weight: bold;
                padding: 0 24px;
            }
            QPushButton:hover {
                background-color: #1D4ED8;
            }
        """)
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
            QMessageBox.warning(self, "تنبيه", "لا يمكن التحويل من وإلى نفس الحساب")
            return

        amt_str = self.amount_edit.text().strip()
        if not amt_str:
            QMessageBox.warning(self, "تنبيه", "يرجى إدخال مبلغ التحويل")
            self.amount_edit.setFocus()
            return

        try:
            amt_piasters = egp_to_piasters(amt_str)
            if amt_piasters <= 0:
                raise ValueError()
        except Exception:
            QMessageBox.warning(self, "تنبيه", "صيغة المبلغ غير صحيحة")
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
            QMessageBox.information(self, "نجاح", f"تم تحويل {amt_str} ج.م بنجاح بين الحسابين!")
            self.accept()
        except Exception as e:
            self.session.rollback()
            QMessageBox.critical(self, "خطأ", f"تعذر إتمام التحويل:\n{str(e)}")

