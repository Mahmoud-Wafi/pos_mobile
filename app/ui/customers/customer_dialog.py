"""Dialog to create or edit customer profiles and credit limits."""
from __future__ import annotations

from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QFrame, QTextEdit,
)

from app.core.money import egp_to_piasters, format_money
from app.models.customer import Customer
from app.services import customer_service


class CustomerDialog(QDialog):
    def __init__(self, session, user, customer: Optional[Customer] = None, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self.customer = customer
        self.setWindowTitle("تعديل بيانات عميل" if customer else "إضافة عميل جديد")
        self.resize(480, 460)
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
            QLineEdit, QTextEdit {
                background-color: #F8FAFC;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                padding: 10px 12px;
                font-size: 13px;
                color: #0F172A;
            }
            QLineEdit:focus, QTextEdit:focus {
                background-color: #FFFFFF;
                border: 2px solid #2563EB;
            }
        """)
        self._build_ui()
        if self.customer:
            self._load_data()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        # Header
        hdr = QHBoxLayout()
        icon = QLabel("👤")
        icon.setStyleSheet("font-size: 28px;")
        hdr.addWidget(icon)

        t_box = QVBoxLayout()
        t_box.setSpacing(2)
        lbl_t = QLabel("بيانات العميل وحساب الآجل" if not self.customer else "تعديل بيانات العميل")
        lbl_t.setStyleSheet("font-size: 16px; font-weight: bold; color: #0F172A;")
        lbl_sub = QLabel("تحديد حد الائتمان المسموح به ورقم الهاتف للمتابعة وإصدار الفواتير")
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

        # Name
        layout.addWidget(QLabel("اسم العميل: *"))
        self.name_edit = QLineEdit()
        self.name_edit.setFixedHeight(42)
        self.name_edit.setPlaceholderText("الاسم ثلاثي أو ثنائي...")
        layout.addWidget(self.name_edit)

        # Phone
        layout.addWidget(QLabel("رقم الهاتف:"))
        self.phone_edit = QLineEdit()
        self.phone_edit.setFixedHeight(42)
        self.phone_edit.setPlaceholderText("010/011/012/015...")
        layout.addWidget(self.phone_edit)

        # Credit Limit
        layout.addWidget(QLabel("حد الائتمان الأقصى للآجل (ج.م):"))
        self.credit_edit = QLineEdit("0.00")
        self.credit_edit.setFixedHeight(42)
        self.credit_edit.setValidator(QDoubleValidator(0.0, 9999999.0, 2))
        layout.addWidget(self.credit_edit)

        # Notes
        layout.addWidget(QLabel("ملاحظات إضافية أو العنوان:"))
        self.notes_edit = QTextEdit()
        self.notes_edit.setFixedHeight(70)
        self.notes_edit.setPlaceholderText("العنوان، الوظيفة، أي معلومات إضافية...")
        layout.addWidget(self.notes_edit)

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

        btn_save = QPushButton("💾 حفظ بيانات العميل")
        btn_save.setFixedHeight(42)
        btn_save.setStyleSheet("""
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
        btn_save.clicked.connect(self._save)
        btn_box.addWidget(btn_save)

        layout.addLayout(btn_box)

    def _load_data(self):
        self.name_edit.setText(self.customer.name or "")
        self.phone_edit.setText(self.customer.phone or "")
        self.credit_edit.setText(f"{self.customer.credit_limit / 100:.2f}")
        self.notes_edit.setPlainText(self.customer.notes or "")

    def _save(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "تنبيه", "يرجى كتابة اسم العميل")
            self.name_edit.setFocus()
            return

        phone = self.phone_edit.text().strip()
        try:
            limit_piasters = egp_to_piasters(self.credit_edit.text() or 0)
        except Exception:
            QMessageBox.warning(self, "تنبيه", "صيغة حد الائتمان غير صحيحة")
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
            QMessageBox.critical(self, "خطأ", f"تعذر حفظ العميل:\n{str(e)}")

