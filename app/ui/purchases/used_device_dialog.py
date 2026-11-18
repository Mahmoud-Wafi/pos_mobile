"""Dialog for purchasing used phones with seller verification and declaration PDF."""
from __future__ import annotations
from app.i18n import ar

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

from app.ui.components.basic import attach_imei_check
from app.ui.components import show_error
from app.core.money import egp_to_piasters, format_money
from app.models.accounting import CashAccount
from app.models.product import Product
from app.models.purchase import UsedDevicePurchase
from app.services import purchase_service
from app.ui.design.style import set_prop, style_label, variant
from app.ui.design import icons
from app.ui.design.tokens import COLORS


class UsedDeviceDialog(QDialog):
    def __init__(self, session, user, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self.created_purchase: Optional[UsedDevicePurchase] = None
        self.setWindowTitle(ar.USED_DEVICE_DIALOG_FD5AB2)
        self.resize(720, 680)
        self.setModal(True)

        self._build_ui()
        self._load_phone_products()
        self._load_cash_accounts()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # Header
        hdr = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(icons.pixmap("smartphone", COLORS["primary"], 28))
        hdr.addWidget(icon)

        t_box = QVBoxLayout()
        t_box.setSpacing(2)
        lbl_t = QLabel(ar.USED_DEVICE_DIALOG_F43160)
        style_label(lbl_t, size="h2", tone="text", bold=True)
        lbl_sub = QLabel(ar.USED_DEVICE_DIALOG_D85C8C)
        style_label(lbl_sub, size="caption", tone="muted")
        t_box.addWidget(lbl_t)
        t_box.addWidget(lbl_sub)
        hdr.addLayout(t_box)
        hdr.addStretch()
        main_layout.addLayout(hdr)

        # ── Group 1: بيانات البائع ──────────────────────────
        grp_seller = QGroupBox(ar.USED_DEVICE_DIALOG_270D37)
        grid_seller = QGridLayout(grp_seller)
        grid_seller.setHorizontalSpacing(14)
        grid_seller.setVerticalSpacing(8)

        grid_seller.addWidget(QLabel(ar.USED_DEVICE_DIALOG_7ED038), 0, 0)
        self.seller_name_edit = QLineEdit()
        self.seller_name_edit.setMinimumHeight(40)
        self.seller_name_edit.setPlaceholderText(ar.USED_DEVICE_DIALOG_A3EFFF)
        grid_seller.addWidget(self.seller_name_edit, 1, 0)

        grid_seller.addWidget(QLabel(ar.USED_DEVICE_DIALOG_98C35F), 0, 1)
        self.seller_nid_edit = QLineEdit()
        self.seller_nid_edit.setMinimumHeight(40)
        self.seller_nid_edit.setMaxLength(14)
        self.seller_nid_edit.setPlaceholderText(ar.USED_DEVICE_DIALOG_2F39DA)
        grid_seller.addWidget(self.seller_nid_edit, 1, 1)

        grid_seller.addWidget(QLabel(ar.USED_DEVICE_DIALOG_49D14B), 2, 0)
        self.seller_phone_edit = QLineEdit()
        self.seller_phone_edit.setMinimumHeight(40)
        self.seller_phone_edit.setPlaceholderText("010/011/012/015...")
        grid_seller.addWidget(self.seller_phone_edit, 3, 0)

        main_layout.addWidget(grp_seller)

        # ── Group 2: بيانات الجهاز ─────────────────────────
        grp_device = QGroupBox(ar.USED_DEVICE_DIALOG_829114)
        grid_device = QGridLayout(grp_device)
        grid_device.setHorizontalSpacing(14)
        grid_device.setVerticalSpacing(8)

        grid_device.addWidget(QLabel(ar.USED_DEVICE_DIALOG_C5C85E), 0, 0)
        self.phone_combo = QComboBox()
        self.phone_combo.setMinimumHeight(40)
        grid_device.addWidget(self.phone_combo, 1, 0)

        grid_device.addWidget(QLabel(ar.USED_DEVICE_DIALOG_9EBCBF), 0, 1)
        self.price_edit = QLineEdit()
        self.price_edit.setMinimumHeight(40)
        self.price_edit.setPlaceholderText(ar.DAILY_CLOSE_DIALOG_388B15)
        self.price_edit.setValidator(QDoubleValidator(0.01, 9999999.0, 2))
        grid_device.addWidget(self.price_edit, 1, 1)

        grid_device.addWidget(QLabel(ar.USED_DEVICE_DIALOG_4C79B7), 2, 0)
        self.imei1_edit = QLineEdit()
        attach_imei_check(self.imei1_edit, required=True)
        self.imei1_edit.setMinimumHeight(40)
        self.imei1_edit.setPlaceholderText(ar.USED_DEVICE_DIALOG_FC12C4)
        grid_device.addWidget(self.imei1_edit, 3, 0)

        grid_device.addWidget(QLabel(ar.USED_DEVICE_DIALOG_4827E3), 2, 1)
        self.imei2_edit = QLineEdit()
        attach_imei_check(self.imei2_edit, required=False)
        self.imei2_edit.setMinimumHeight(40)
        self.imei2_edit.setPlaceholderText(ar.USED_DEVICE_DIALOG_622A39)
        grid_device.addWidget(self.imei2_edit, 3, 1)

        grid_device.addWidget(QLabel(ar.USED_DEVICE_DIALOG_5D3CD7), 4, 0, 1, 2)
        self.condition_edit = QTextEdit()
        self.condition_edit.setFixedHeight(60)
        self.condition_edit.setPlaceholderText(ar.USED_DEVICE_DIALOG_F348AC)
        grid_device.addWidget(self.condition_edit, 5, 0, 1, 2)

        main_layout.addWidget(grp_device)

        # ── Footer / Actions ───────────────────────────────
        foot_card = QFrame()
        set_prop(foot_card, "card", True)
        foot_layout = QHBoxLayout(foot_card)
        foot_layout.setSpacing(14)

        foot_layout.addWidget(QLabel(ar.USED_DEVICE_DIALOG_9C5309))
        self.acc_combo = QComboBox()
        self.acc_combo.setMinimumHeight(40)
        self.acc_combo.setMinimumWidth(180)
        foot_layout.addWidget(self.acc_combo)

        foot_layout.addStretch()

        btn_cancel = QPushButton(ar.CANCEL)
        btn_cancel.setFixedHeight(42)
        variant(btn_cancel, "secondary")
        btn_cancel.clicked.connect(self.reject)
        foot_layout.addWidget(btn_cancel)

        self.btn_save = QPushButton(ar.USED_DEVICE_DIALOG_E9193A)
        self.btn_save.setFixedHeight(42)
        variant(self.btn_save, "success")
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
            self.phone_combo.addItem(f"{p.name}", p.id)

    def _load_cash_accounts(self):
        self.acc_combo.clear()
        accounts = self.session.query(CashAccount).all()
        for a in accounts:
            self.acc_combo.addItem(f"{a.name} ({format_money(a.balance)})", a.id)

    def _save_used_device(self):
        name = self.seller_name_edit.text().strip()
        if not name:
            show_error(self, message=ar.USED_DEVICE_DIALOG_FCB39A)
            self.seller_name_edit.setFocus()
            return

        nid = self.seller_nid_edit.text().strip()
        if len(nid) != 14 or not nid.isdigit():
            show_error(self, message=ar.USED_DEVICE_DIALOG_DBC731)
            self.seller_nid_edit.setFocus()
            return

        phone = self.seller_phone_edit.text().strip()
        if not phone:
            show_error(self, message=ar.USED_DEVICE_DIALOG_6F9CAB)
            self.seller_phone_edit.setFocus()
            return

        product_id = self.phone_combo.currentData()
        if not product_id:
            show_error(self, message=ar.USED_DEVICE_DIALOG_7E6A89)
            return

        price_text = self.price_edit.text().strip()
        try:
            price_piasters = egp_to_piasters(price_text)
            if price_piasters <= 0:
                raise ValueError()
        except Exception:
            show_error(self, message=ar.USED_DEVICE_DIALOG_D5864A)
            self.price_edit.setFocus()
            return

        imei1 = self.imei1_edit.text().strip()
        if not imei1:
            show_error(self, message=ar.IMEI_INPUT_DIALOG_06FB49)
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
            msg.setWindowTitle(ar.USED_DEVICE_DIALOG_46EF6B)
            msg.setText(
                f"تم حفظ شراء الهاتف المستعمل بنجاح وتم إدراجه في المخزون كجهاز (مستعمل).\n\n"
                f"تم إنشاء إقرار البيع والتنازل في:\n{pdf_path}"
            )
            btn_open_pdf = msg.addButton(ar.USED_DEVICE_DIALOG_BA0281, QMessageBox.ActionRole)
            btn_ok = msg.addButton(ar.CLOSE, QMessageBox.AcceptRole)
            msg.exec()

            if msg.clickedButton() == btn_open_pdf:
                self._open_file(str(pdf_path))

            self.accept()
        except Exception as e:
            self.session.rollback()
            show_error(self, message=f"تعذر تسجيل شراء الجهاز المستعمل:\n{str(e)}")

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

