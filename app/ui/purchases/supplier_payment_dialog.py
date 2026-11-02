"""Dialog for paying suppliers (settling debts)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QMessageBox, QFrame,
)

from app.core.money import egp_to_piasters, format_money, piasters_to_egp
from app.models.accounting import CashAccount
from app.models.purchase import Supplier
from app.services import purchase_service


class SupplierPaymentDialog(QDialog):
    def __init__(self, session, user, supplier: Supplier, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self.supplier = supplier
        self.setWindowTitle(f"سداد دفعة للمورد: {supplier.name}")
        self.resize(480, 440)
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

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()
        icon = QLabel("💳")
        icon.setStyleSheet("font-size: 28px;")
        header.addWidget(icon)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        lbl_title = QLabel(f"سداد دفعة للمورد: {self.supplier.name}")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #0F172A;")
        lbl_sub = QLabel("سيتم خصم المبلغ من خزينة/درج المحل وتخفيض رصيد المورد")
        lbl_sub.setStyleSheet("font-size: 12px; color: #64748B; font-weight: normal;")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)
        header.addLayout(title_box)
        header.addStretch()
        layout.addLayout(header)

        # Current Balance Card
        bal_card = QFrame()
        bal_card.setStyleSheet("background-color: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 8px; padding: 12px;")
        bal_layout = QHBoxLayout(bal_card)
        bal_title = QLabel("الرصيد المستحق الحالي للمورد:")
        bal_title.setStyleSheet("color: #1E3A8A; font-weight: 600; font-size: 13px;")
        self.bal_value = QLabel(format_money(self.supplier.balance))
        self.bal_value.setStyleSheet("color: #1D4ED8; font-weight: bold; font-size: 16px;")
        bal_layout.addWidget(bal_title)
        bal_layout.addStretch()
        bal_layout.addWidget(self.bal_value)
        layout.addWidget(bal_card)

        # Amount
        layout.addWidget(QLabel("مبلغ السداد (ج.م): *"))
        self.amount_edit = QLineEdit()
        self.amount_edit.setFixedHeight(44)
        self.amount_edit.setPlaceholderText("0.00 ج.م")
        self.amount_edit.setValidator(QDoubleValidator(0.01, 9999999.0, 2))
        layout.addWidget(self.amount_edit)

        # Account / Method
        layout.addWidget(QLabel("خزينة الصرف (طريقة الدفع): *"))
        self.account_combo = QComboBox()
        self.account_combo.setFixedHeight(42)
        accounts = self.session.query(CashAccount).all()
        for acc in accounts:
            label = f"{acc.name} ({format_money(acc.balance)})"
            self.account_combo.addItem(label, acc.id)
        layout.addWidget(self.account_combo)

        # Note
        layout.addWidget(QLabel("ملاحظات السداد (رقم الإيصال / الحوالة):"))
        self.note_edit = QLineEdit()
        self.note_edit.setFixedHeight(42)
        self.note_edit.setPlaceholderText("مثال: تحويل بنكي / إيصال استلام نقدية رقم...")
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
                font-size: 13px;
                font-weight: 600;
                padding: 0 20px;
            }
            QPushButton:hover {
                background-color: #E2E8F0;
            }
        """)
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_pay = QPushButton("✅ تأكيد صرف الدفعة")
        btn_pay.setFixedHeight(42)
        btn_pay.setStyleSheet("""
            QPushButton {
                background-color: #16A34A;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
                padding: 0 24px;
            }
            QPushButton:hover {
                background-color: #15803D;
            }
        """)
        btn_pay.clicked.connect(self._pay)
        btn_box.addWidget(btn_pay)

        layout.addLayout(btn_box)

    def _pay(self):
        val_text = self.amount_edit.text().strip()
        if not val_text:
            QMessageBox.warning(self, "تنبيه", "يرجى كتابة مبلغ السداد")
            self.amount_edit.setFocus()
            return

        try:
            amount_piasters = egp_to_piasters(val_text)
            if amount_piasters <= 0:
                QMessageBox.warning(self, "تنبيه", "يجب أن يكون المبلغ أكبر من الصفر")
                return
        except Exception:
            QMessageBox.warning(self, "تنبيه", "صيغة المبلغ غير صحيحة")
            return

        account_id = self.account_combo.currentData()
        note = self.note_edit.text().strip()

        try:
            purchase_service.pay_supplier(
                session=self.session,
                user=self.user,
                supplier_id=self.supplier.id,
                amount=amount_piasters,
                account_id=account_id,
                method="cash",
                note=note,
            )
            self.session.commit()
            QMessageBox.information(self, "نجاح", f"تم تسجيل سداد {val_text} ج.م للمورد {self.supplier.name} بنجاح!")
            self.accept()
        except Exception as e:
            self.session.rollback()
            QMessageBox.critical(self, "خطأ", f"تعذر تنفيذ السداد:\n{str(e)}")

