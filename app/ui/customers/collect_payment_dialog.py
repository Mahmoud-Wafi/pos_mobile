"""Dialog for collecting customer debts and recording payments."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QMessageBox, QFrame,
)

from app.core.money import egp_to_piasters, format_money
from app.models.accounting import CashAccount
from app.models.customer import Customer
from app.services import customer_service


class CollectPaymentDialog(QDialog):
    def __init__(self, session, user, customer: Customer, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self.customer = customer
        self.setWindowTitle(f"تحصيل دفعة من العميل: {customer.name}")
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
        layout.setSpacing(14)

        # Header
        hdr = QHBoxLayout()
        icon = QLabel("💵")
        icon.setStyleSheet("font-size: 28px;")
        hdr.addWidget(icon)

        t_box = QVBoxLayout()
        t_box.setSpacing(2)
        lbl_t = QLabel(f"تحصيل دفعة نقدية: {self.customer.name}")
        lbl_t.setStyleSheet("font-size: 16px; font-weight: bold; color: #0F172A;")
        lbl_sub = QLabel("إيداع المبلغ المحصل في الدرج وتخفيض مديونية العميل بالسيستم")
        lbl_sub.setStyleSheet("font-size: 12px; color: #64748B; font-weight: normal;")
        t_box.addWidget(lbl_t)
        t_box.addWidget(lbl_sub)
        hdr.addLayout(t_box)
        hdr.addStretch()
        layout.addLayout(hdr)

        # Current Debt Card
        card = QFrame()
        card.setStyleSheet("background-color: #FEF2F2; border: 1px solid #FECACA; border-radius: 8px; padding: 12px;")
        c_layout = QHBoxLayout(card)
        c_title = QLabel("إجمالي المديونية المستحقة على العميل:")
        c_title.setStyleSheet("color: #991B1B; font-weight: bold;")
        self.lbl_debt = QLabel(format_money(self.customer.balance))
        self.lbl_debt.setStyleSheet("color: #DC2626; font-weight: bold; font-size: 18px;")
        c_layout.addWidget(c_title)
        c_layout.addStretch()
        c_layout.addWidget(self.lbl_debt)
        layout.addWidget(card)

        # Amount
        layout.addWidget(QLabel("المبلغ المحصل الآن (ج.م): *"))
        self.amount_edit = QLineEdit()
        self.amount_edit.setFixedHeight(42)
        self.amount_edit.setPlaceholderText(f"أقصى تحصيل: {self.customer.balance / 100:.2f} ج.م")
        self.amount_edit.setValidator(QDoubleValidator(0.01, 9999999.0, 2))
        layout.addWidget(self.amount_edit)

        # Method / Cash Account
        layout.addWidget(QLabel("الخزينة المودع بها التحصيل: *"))
        self.acc_combo = QComboBox()
        self.acc_combo.setFixedHeight(42)
        accounts = self.session.query(CashAccount).all()
        for a in accounts:
            self.acc_combo.addItem(f"{a.name} ({format_money(a.balance)})", a.id)
        layout.addWidget(self.acc_combo)

        # Notes
        layout.addWidget(QLabel("بيان أو ملاحظات التحصيل:"))
        self.note_edit = QLineEdit()
        self.note_edit.setFixedHeight(40)
        self.note_edit.setPlaceholderText("سداد جزء من فاتورة / دفعة شهرية...")
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

        btn_save = QPushButton("💵 تأكيد التحصيل")
        btn_save.setFixedHeight(42)
        btn_save.setStyleSheet("""
            QPushButton {
                background-color: #16A34A;
                color: white;
                border-radius: 8px;
                font-weight: bold;
                padding: 0 24px;
            }
            QPushButton:hover {
                background-color: #15803D;
            }
        """)
        btn_save.clicked.connect(self._collect)
        btn_box.addWidget(btn_save)

        layout.addLayout(btn_box)

    def _collect(self):
        amt_str = self.amount_edit.text().strip()
        if not amt_str:
            QMessageBox.warning(self, "تنبيه", "يرجى كتابة المبلغ المحصل")
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

        acc_id = self.acc_combo.currentData()
        note = self.note_edit.text().strip()

        try:
            customer_service.collect_payment(
                session=self.session,
                user=self.user,
                customer_id=self.customer.id,
                amount=amt_piasters,
                method="cash",
                account_id=acc_id,
                notes=note,
            )
            self.session.commit()
            QMessageBox.information(
                self,
                "تم التحصيل بنجاح",
                f"تم تحصيل {amt_str} ج.م من العميل {self.customer.name} بنجاح!\nالمتبقي عليه: {format_money(self.customer.balance)}"
            )
            self.accept()
        except Exception as e:
            self.session.rollback()
            QMessageBox.critical(self, "خطأ", f"تعذر تسجيل التحصيل:\n{str(e)}")

