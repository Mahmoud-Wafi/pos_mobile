"""Modern dialog for adding and editing suppliers."""
from __future__ import annotations

from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTextEdit, QPushButton, QMessageBox, QFrame,
)

from app.ui.components import show_error
from app.core.money import egp_to_piasters, piasters_to_egp
from app.models.purchase import Supplier
from app.services import purchase_service
from app.ui.design.style import set_prop, style_label, variant
from app.ui.design import icons
from app.ui.design.tokens import COLORS


class SupplierDialog(QDialog):
    def __init__(self, session, user, supplier: Optional[Supplier] = None, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self.supplier = supplier
        self.setWindowTitle("تعديل بيانات مورد" if supplier else "إضافة مورد جديد")
        self.resize(500, 480)
        self.setModal(True)

        self._build_ui()
        if self.supplier:
            self._load_supplier_data()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(icons.pixmap("landmark", COLORS["primary"], 28))
        header.addWidget(icon)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        lbl_title = QLabel("بيانات المورد التجاري" if not self.supplier else "تعديل بيانات المورد")
        style_label(lbl_title, size="title", tone="text", bold=True)
        lbl_sub = QLabel("أدخل تفاصيل الاتصال والاسم التجاري للمورد")
        style_label(lbl_sub, size="caption", tone="muted")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)
        header.addLayout(title_box)
        header.addStretch()
        layout.addLayout(header)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        set_prop(sep, "hline", True)
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
        variant(self.btn_cancel, "secondary")
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("حفظ بيانات المورد")
        self.btn_save.setFixedHeight(42)
        variant(self.btn_save, "primary")
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
            show_error(self, message="يرجى كتابة اسم المورد أولاً")
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
            show_error(self, message=f"تعذر حفظ المورد:\n{str(e)}")

