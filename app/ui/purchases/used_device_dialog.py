"""Dialog for purchasing used phones with seller verification and declaration PDF."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QTextEdit, QMessageBox, QFrame,
    QGridLayout, QGroupBox,
)

from app.core.money import egp_to_piasters, format_money
from app.models.accounting import CashAccount
from app.models.product import Product
from app.models.purchase import UsedDevicePurchase
from app.services import purchase_service


class UsedDeviceDialog(QDialog):
    def __init__(self, session, user, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self.created_purchase: Optional[UsedDevicePurchase] = None
        self.setWindowTitle("شراء جهاز مستعمل — إقرار وتنازل ملكية")
        self.resize(720, 680)
        self.setModal(True)
        self.setStyleSheet("""
            QDialog {
                background-color: #F8FAFC;
            }
            QLabel {
                color: #0F172A;
                font-size: 13px;
                font-weight: 600;
            }
            QLineEdit, QComboBox, QTextEdit {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
                color: #0F172A;
            }
            QLineEdit:focus, QComboBox:focus, QTextEdit:focus {
                border: 2px solid #2563EB;
            }
            QGroupBox {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 10px;
                font-weight: bold;
                font-size: 14px;
                color: #0F172A;
                margin-top: 12px;
                padding-top: 18px;
                padding-bottom: 12px;
                padding-left: 12px;
                padding-right: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top right;
                padding: 0 8px;
                color: #2563EB;
            }
        """)
        self._build_ui()
        self._load_phone_products()
        self._load_cash_accounts()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # Header
        hdr = QHBoxLayout()
        icon = QLabel("📱")
        icon.setStyleSheet("font-size: 28px;")
        hdr.addWidget(icon)

        t_box = QVBoxLayout()
        t_box.setSpacing(2)
        lbl_t = QLabel("شراء هاتف مستعمل من عميل / بائع")
        lbl_t.setStyleSheet("font-size: 18px; font-weight: bold; color: #0F172A;")
        lbl_sub = QLabel("توثيق الهوية والرقم القومي وطباعة إقرار التنازل القانوني ضد السرقة")
        lbl_sub.setStyleSheet("font-size: 12px; color: #64748B; font-weight: normal;")
        t_box.addWidget(lbl_t)
        t_box.addWidget(lbl_sub)
        hdr.addLayout(t_box)
        hdr.addStretch()
        main_layout.addLayout(hdr)

        # ── Group 1: بيانات البائع ──────────────────────────
        grp_seller = QGroupBox("👤 1. بيانات البائع الشخصية والبطاقة القومية")
        grid_seller = QGridLayout(grp_seller)
        grid_seller.setHorizontalSpacing(14)
        grid_seller.setVerticalSpacing(8)

        grid_seller.addWidget(QLabel("اسم البائع الرباعي: *"), 0, 0)
        self.seller_name_edit = QLineEdit()
        self.seller_name_edit.setFixedHeight(38)
        self.seller_name_edit.setPlaceholderText("كما هو مدون ببطاقة الرقم القومي")
        grid_seller.addWidget(self.seller_name_edit, 1, 0)

        grid_seller.addWidget(QLabel("الرقم القومي (14 رقماً): *"), 0, 1)
        self.seller_nid_edit = QLineEdit()
        self.seller_nid_edit.setFixedHeight(38)
        self.seller_nid_edit.setMaxLength(14)
        self.seller_nid_edit.setPlaceholderText("14 رقم قومي صحيح")
        grid_seller.addWidget(self.seller_nid_edit, 1, 1)

        grid_seller.addWidget(QLabel("رقم الهاتف للتواصل: *"), 2, 0)
        self.seller_phone_edit = QLineEdit()
        self.seller_phone_edit.setFixedHeight(38)
        self.seller_phone_edit.setPlaceholderText("010/011/012/015...")
        grid_seller.addWidget(self.seller_phone_edit, 3, 0)

        main_layout.addWidget(grp_seller)

        # ── Group 2: بيانات الجهاز ─────────────────────────
        grp_device = QGroupBox("🔍 2. بيانات الجهاز وسيريالات الـ IMEI")
        grid_device = QGridLayout(grp_device)
        grid_device.setHorizontalSpacing(14)
        grid_device.setVerticalSpacing(8)

        grid_device.addWidget(QLabel("موديل الهاتف: *"), 0, 0)
        self.phone_combo = QComboBox()
        self.phone_combo.setFixedHeight(38)
        grid_device.addWidget(self.phone_combo, 1, 0)

        grid_device.addWidget(QLabel("مبلغ الشراء المتفق عليه (ج.م): *"), 0, 1)
        self.price_edit = QLineEdit()
        self.price_edit.setFixedHeight(38)
        self.price_edit.setPlaceholderText("0.00 ج.م")
        self.price_edit.setValidator(QDoubleValidator(0.01, 9999999.0, 2))
        grid_device.addWidget(self.price_edit, 1, 1)

        grid_device.addWidget(QLabel("رقم السيريال IMEI 1: *"), 2, 0)
        self.imei1_edit = QLineEdit()
        self.imei1_edit.setFixedHeight(38)
        self.imei1_edit.setPlaceholderText("امسح بالباركود أو اكتب 15 رقماً")
        grid_device.addWidget(self.imei1_edit, 3, 0)

        grid_device.addWidget(QLabel("رقم السيريال IMEI 2 (اختياري):"), 2, 1)
        self.imei2_edit = QLineEdit()
        self.imei2_edit.setFixedHeight(38)
        self.imei2_edit.setPlaceholderText("السيريال الثاني إن وجد")
        grid_device.addWidget(self.imei2_edit, 3, 1)

        grid_device.addWidget(QLabel("حالة الجهاز وملاحظات الفحص:"), 4, 0, 1, 2)
        self.condition_edit = QTextEdit()
        self.condition_edit.setFixedHeight(60)
        self.condition_edit.setPlaceholderText("نسبة البطارية، الخدوش، الملحقات المرفقة، الفحص الفني...")
        grid_device.addWidget(self.condition_edit, 5, 0, 1, 2)

        main_layout.addWidget(grp_device)

        # ── Footer / Actions ───────────────────────────────
        foot_card = QFrame()
        foot_card.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 12px;")
        foot_layout = QHBoxLayout(foot_card)
        foot_layout.setSpacing(14)

        foot_layout.addWidget(QLabel("خزينة الصرف:"))
        self.acc_combo = QComboBox()
        self.acc_combo.setFixedHeight(38)
        self.acc_combo.setMinimumWidth(180)
        foot_layout.addWidget(self.acc_combo)

        foot_layout.addStretch()

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
        foot_layout.addWidget(btn_cancel)

        self.btn_save = QPushButton("📝 تسجيل الشراء وطباعة الإقرار (PDF)")
        self.btn_save.setFixedHeight(42)
        self.btn_save.setStyleSheet("""
            QPushButton {
                background-color: #16A34A;
                color: white;
                border-radius: 8px;
                font-weight: bold;
                font-size: 13px;
                padding: 0 24px;
            }
            QPushButton:hover {
                background-color: #15803D;
            }
        """)
        self.btn_save.clicked.connect(self._save_used_device)
        foot_layout.addWidget(self.btn_save)

        main_layout.addWidget(foot_card)

    def _load_phone_products(self):
        self.phone_combo.clear()
        phones = (
            self.session.query(Product)
            .filter(Product.track_imei == True, Product.is_active == True)
            .order_by(Product.name.asc())
            .all()
        )
        for p in phones:
            self.phone_combo.addItem(f"📱 {p.name}", p.id)

    def _load_cash_accounts(self):
        self.acc_combo.clear()
        accounts = self.session.query(CashAccount).all()
        for a in accounts:
            self.acc_combo.addItem(f"{a.name} ({format_money(a.balance)})", a.id)

    def _save_used_device(self):
        name = self.seller_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "تنبيه", "يرجى كتابة اسم البائع الرباعي")
            self.seller_name_edit.setFocus()
            return

        nid = self.seller_nid_edit.text().strip()
        if len(nid) != 14 or not nid.isdigit():
            QMessageBox.warning(self, "تنبيه", "الرقم القومي للبائع يجب أن يتكون من 14 رقماً صحيحاً")
            self.seller_nid_edit.setFocus()
            return

        phone = self.seller_phone_edit.text().strip()
        if not phone:
            QMessageBox.warning(self, "تنبيه", "يرجى كتابة رقم هاتف البائع")
            self.seller_phone_edit.setFocus()
            return

        product_id = self.phone_combo.currentData()
        if not product_id:
            QMessageBox.warning(self, "تنبيه", "يرجى اختيار موديل الهاتف")
            return

        price_text = self.price_edit.text().strip()
        try:
            price_piasters = egp_to_piasters(price_text)
            if price_piasters <= 0:
                raise ValueError()
        except Exception:
            QMessageBox.warning(self, "تنبيه", "مبلغ الشراء غير صحيح")
            self.price_edit.setFocus()
            return

        imei1 = self.imei1_edit.text().strip()
        if not imei1:
            QMessageBox.warning(self, "تنبيه", "يرجى مسح أو إدخال رقم IMEI 1")
            self.imei1_edit.setFocus()
            return

        imei2 = self.imei2_edit.text().strip() or None
        cond_notes = self.condition_edit.toPlainText().strip()
        account_id = self.acc_combo.currentData()

        try:
            used_purchase = purchase_service.record_used_device_purchase(
                session=self.session,
                user=self.user,
                seller_name=name,
                seller_national_id=nid,
                seller_phone=phone,
                product_id=product_id,
                imei1=imei1,
                imei2=imei2,
                price=price_piasters,
                condition_notes=cond_notes,
                account_id=account_id,
            )
            self.session.commit()

            # Generate declaration PDF
            pdf_path = purchase_service.generate_declaration(
                session=self.session,
                user=self.user,
                used_purchase_id=used_purchase.id,
            )
            self.session.commit()
            self.created_purchase = used_purchase

            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle("تم تسجيل الشراء بنجاح")
            msg.setText(
                f"تم حفظ شراء الهاتف المستعمل بنجاح وتم إدراجه في المخزون كجهاز (مستعمل).\n\n"
                f"تم إنشاء إقرار البيع والتنازل في:\n{pdf_path}"
            )
            btn_open_pdf = msg.addButton("📄 فتح الإقرار PDF", QMessageBox.ActionRole)
            btn_ok = msg.addButton("إغلاق", QMessageBox.AcceptRole)
            msg.exec()

            if msg.clickedButton() == btn_open_pdf:
                self._open_file(str(pdf_path))

            self.accept()
        except Exception as e:
            self.session.rollback()
            QMessageBox.critical(self, "خطأ", f"تعذر تسجيل شراء الجهاز المستعمل:\n{str(e)}")

    def _open_file(self, filepath: str):
        try:
            if sys.platform.startswith("linux"):
                subprocess.Popen(["xdg-open", filepath])
            elif sys.platform.startswith("win"):
                os.startfile(filepath)
            elif sys.platform.startswith("darwin"):
                subprocess.Popen(["open", filepath])
        except Exception:
            pass

