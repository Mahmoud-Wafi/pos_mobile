"""Modern dialog for adding and editing suppliers."""
from __future__ import annotations

from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTextEdit, QPushButton, QMessageBox, QFrame,
)

from app.core.money import egp_to_piasters, piasters_to_egp
from app.models.purchase import Supplier
from app.services import purchase_service


class SupplierDialog(QDialog):
    def __init__(self, session, user, supplier: Optional[Supplier] = None, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self.supplier = supplier
        self.setWindowTitle("تعديل بيانات مورد" if supplier else "إضافة مورد جديد")
        self.resize(500, 480)
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
        if self.supplier:
            self._load_supplier_data()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()
        icon = QLabel("🏢")
        icon.setStyleSheet("font-size: 28px;")
        header.addWidget(icon)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        lbl_title = QLabel("بيانات المورد التجاري" if not self.supplier else "تعديل بيانات المورد")
        lbl_title.setStyleSheet("font-size: 17px; font-weight: bold; color: #0F172A;")
        lbl_sub = QLabel("أدخل تفاصيل الاتصال والاسم التجاري للمورد")
        lbl_sub.setStyleSheet("font-size: 12px; color: #64748B; font-weight: normal;")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)
        header.addLayout(title_box)
        header.addStretch()
        layout.addLayout(header)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #E2E8F0;")
        layout.addWidget(sep)

        # Name
        layout.addWidget(QLabel("اسم المورد / الشركة: *"))
        self.name_edit = QLineEdit()
        self.name_edit.setFixedHeight(42)
        self.name_edit.setPlaceholderText("مثال: شركة الأهرام للتوزيع أو العالمية للموبايل")
        layout.addWidget(self.name_edit)

        # Phone
        layout.addWidget(QLabel("رقم الهاتف / الموبايل:"))
        self.phone_edit = QLineEdit()
        self.phone_edit.setFixedHeight(42)
        self.phone_edit.setPlaceholderText("مثال: 01012345678")
        layout.addWidget(self.phone_edit)

        # Initial Balance (only for new supplier)
        if not self.supplier:
            layout.addWidget(QLabel("الرصيد الافتتاحي (لنا / للمورد) بالجنيه:"))
            self.balance_edit = QLineEdit()
            self.balance_edit.setFixedHeight(42)
            self.balance_edit.setPlaceholderText("0.00 ج.م (المبلغ المستحق للمورد إن وجد)")
            self.balance_edit.setValidator(QDoubleValidator(0.0, 9999999.0, 2))
            layout.addWidget(self.balance_edit)

        # Notes
        layout.addWidget(QLabel("ملاحظات إضافية أو العنوان:"))
        self.notes_edit = QTextEdit()
        self.notes_edit.setFixedHeight(80)
        self.notes_edit.setPlaceholderText("العنوان، اسم المندوب، شروط السداد...")
        layout.addWidget(self.notes_edit)

        layout.addStretch()

        # Buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(12)

        self.btn_cancel = QPushButton("إلغاء")
        self.btn_cancel.setFixedHeight(42)
        self.btn_cancel.setStyleSheet("""
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
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("💾 حفظ بيانات المورد")
        self.btn_save.setFixedHeight(42)
        self.btn_save.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
                padding: 0 24px;
            }
            QPushButton:hover {
                background-color: #1D4ED8;
            }
        """)
        self.btn_save.clicked.connect(self._save)
        btn_box.addWidget(self.btn_save)

        layout.addLayout(btn_box)

    def _load_supplier_data(self):
        self.name_edit.setText(self.supplier.name or "")
        self.phone_edit.setText(self.supplier.phone or "")
        self.notes_edit.setPlainText(self.supplier.notes or "")

    def _save(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "تنبيه", "يرجى كتابة اسم المورد أولاً")
            self.name_edit.setFocus()
            return

        phone = self.phone_edit.text().strip()
        notes = self.notes_edit.toPlainText().strip()

        try:
            if self.supplier:
                purchase_service.update_supplier(
                    self.session, self.user, self.supplier.id,
                    name=name, phone=phone, notes=notes,
                )
            else:
                bal_text = getattr(self, "balance_edit", None)
                init_bal = egp_to_piasters(bal_text.text().strip()) if bal_text and bal_text.text().strip() else 0
                self.supplier = purchase_service.create_supplier(
                    self.session, self.user, name=name, phone=phone, notes=notes, initial_balance=init_bal,
                )
            self.session.commit()
            self.accept()
        except Exception as e:
            self.session.rollback()
            QMessageBox.critical(self, "خطأ", f"تعذر حفظ المورد:\n{str(e)}")

