"""Modern Purchase Invoice Dialog for entering supplier invoices with IMEI support."""
from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QDoubleValidator, QIntValidator
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QFrame, QGroupBox, QGridLayout,
)

from app.core.money import egp_to_piasters, format_money, piasters_to_egp
from app.models.accounting import CashAccount
from app.models.product import Product
from app.models.purchase import Supplier
from app.services import purchase_service
from app.ui.purchases.imei_input_dialog import IMEIInputDialog
from app.ui.purchases.supplier_dialog import SupplierDialog


class PurchaseInvoiceDialog(QDialog):
    def __init__(self, session, user, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self.items_data: list[dict] = []
        self.setWindowTitle("فاتورة شراء جديدة من مورد")
        self.resize(960, 680)
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
            QLineEdit, QComboBox {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
                color: #0F172A;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 2px solid #2563EB;
            }
            QTableWidget {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
            }
            QHeaderView::section {
                background-color: #F1F5F9;
                color: #334155;
                font-weight: bold;
                padding: 8px;
                border: none;
                border-bottom: 1px solid #E2E8F0;
            }
        """)
        self._build_ui()
        self._load_suppliers()
        self._load_products()
        self._load_cash_accounts()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # ── Header ─────────────────────────────────────────
        hdr = QHBoxLayout()
        icon = QLabel("📥")
        icon.setStyleSheet("font-size: 28px;")
        hdr.addWidget(icon)

        t_box = QVBoxLayout()
        t_box.setSpacing(2)
        lbl_t = QLabel("تسجيل فاتورة مشتريات وتوريد بضاعة")
        lbl_t.setStyleSheet("font-size: 18px; font-weight: bold; color: #0F172A;")
        lbl_sub = QLabel("تحديث المخزون ومتوسط التكلفة وسيريالات الأجهزة ورصيد المورد تلقائياً")
        lbl_sub.setStyleSheet("font-size: 12px; color: #64748B; font-weight: normal;")
        t_box.addWidget(lbl_t)
        t_box.addWidget(lbl_sub)
        hdr.addLayout(t_box)
        hdr.addStretch()
        main_layout.addLayout(hdr)

        # ── Invoice Meta Card ───────────────────────────────
        meta_card = QFrame()
        meta_card.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 12px;")
        meta_grid = QGridLayout(meta_card)
        meta_grid.setHorizontalSpacing(14)
        meta_grid.setVerticalSpacing(8)

        # Supplier
        meta_grid.addWidget(QLabel("المورد التجاري: *"), 0, 0)
        sup_box = QHBoxLayout()
        self.supplier_combo = QComboBox()
        self.supplier_combo.setFixedHeight(38)
        self.supplier_combo.setMinimumWidth(220)
        sup_box.addWidget(self.supplier_combo)

        btn_add_sup = QPushButton("➕ جديد")
        btn_add_sup.setFixedHeight(38)
        btn_add_sup.setStyleSheet("background-color: #EFF6FF; color: #2563EB; border: 1px solid #BFDBFE; border-radius: 6px; font-weight: bold;")
        btn_add_sup.clicked.connect(self._add_new_supplier)
        sup_box.addWidget(btn_add_sup)
        meta_grid.addLayout(sup_box, 1, 0)

        # Invoice Number
        meta_grid.addWidget(QLabel("رقم فاتورة الشراء: *"), 0, 1)
        self.inv_no_edit = QLineEdit()
        self.inv_no_edit.setFixedHeight(38)
        default_inv = f"PUR-{datetime.datetime.now().strftime('%Y%m%d-%H%M')}"
        self.inv_no_edit.setText(default_inv)
        meta_grid.addWidget(self.inv_no_edit, 1, 1)

        # Notes
        meta_grid.addWidget(QLabel("ملاحظات الفاتورة:"), 0, 2)
        self.notes_edit = QLineEdit()
        self.notes_edit.setFixedHeight(38)
        self.notes_edit.setPlaceholderText("شحنة جديدة / رقم إذن التوريد...")
        meta_grid.addWidget(self.notes_edit, 1, 2)

        main_layout.addWidget(meta_card)

        # ── Add Line Item Section ───────────────────────────
        line_card = QFrame()
        line_card.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 12px;")
        line_grid = QGridLayout(line_card)
        line_grid.setHorizontalSpacing(12)
        line_grid.setVerticalSpacing(8)

        # Product Selector
        line_grid.addWidget(QLabel("الصنف:"), 0, 0)
        self.product_combo = QComboBox()
        self.product_combo.setFixedHeight(38)
        self.product_combo.currentIndexChanged.connect(self._on_product_selected)
        line_grid.addWidget(self.product_combo, 1, 0)

        # Quantity
        line_grid.addWidget(QLabel("الكمية:"), 0, 1)
        self.qty_edit = QLineEdit("1")
        self.qty_edit.setFixedHeight(38)
        self.qty_edit.setFixedWidth(80)
        self.qty_edit.setValidator(QIntValidator(1, 99999))
        self.qty_edit.textChanged.connect(self._recalc_line_hint)
        line_grid.addWidget(self.qty_edit, 1, 1)

        # Unit Cost
        line_grid.addWidget(QLabel("سعر التكلفة (ج.م):"), 0, 2)
        self.cost_edit = QLineEdit()
        self.cost_edit.setFixedHeight(38)
        self.cost_edit.setFixedWidth(120)
        self.cost_edit.setValidator(QDoubleValidator(0.0, 9999999.0, 2))
        self.cost_edit.textChanged.connect(self._recalc_line_hint)
        line_grid.addWidget(self.cost_edit, 1, 2)

        # IMEI Action (for phones)
        line_grid.addWidget(QLabel("سيريالات الأجهزة (IMEI):"), 0, 3)
        self.btn_imei = QPushButton("🔢 إدخال السيريالات")
        self.btn_imei.setFixedHeight(38)
        self.btn_imei.setEnabled(False)
        self.btn_imei.setStyleSheet("""
            QPushButton {
                background-color: #F8FAFC;
                color: #64748B;
                border: 1px dashed #CBD5E1;
                border-radius: 8px;
                font-weight: 600;
            }
            QPushButton:enabled {
                background-color: #FEF3C7;
                color: #B45309;
                border: 1px solid #F59E0B;
            }
        """)
        self.btn_imei.clicked.connect(self._open_imei_dialog)
        line_grid.addWidget(self.btn_imei, 1, 3)

        # Add Line Button
        self.btn_add_line = QPushButton("➕ إضافة للفاتورة")
        self.btn_add_line.setFixedHeight(38)
        self.btn_add_line.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: white;
                border-radius: 8px;
                font-weight: bold;
                padding: 0 16px;
            }
            QPushButton:hover {
                background-color: #1D4ED8;
            }
        """)
        self.btn_add_line.clicked.connect(self._add_line_item)
        line_grid.addWidget(self.btn_add_line, 1, 4)

        main_layout.addWidget(line_card)

        # ── Items Table ─────────────────────────────────────
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "#", "اسم المنتج", "الكمية", "سعر الوحدة", "الإجمالي", "السيريالات (IMEI)", "حذف"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed); self.table.setColumnWidth(0, 40)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed); self.table.setColumnWidth(2, 70)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed); self.table.setColumnWidth(3, 110)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed); self.table.setColumnWidth(4, 120)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed); self.table.setColumnWidth(5, 140)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Fixed); self.table.setColumnWidth(6, 60)
        main_layout.addWidget(self.table)

        # ── Totals & Payment Footer ─────────────────────────
        foot_card = QFrame()
        foot_card.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 14px;")
        foot_layout = QHBoxLayout(foot_card)
        foot_layout.setSpacing(16)

        # Total Invoice
        tot_box = QVBoxLayout()
        tot_box.setSpacing(2)
        tot_box.addWidget(QLabel("إجمالي الفاتورة:"))
        self.lbl_total = QLabel("0.00 ج.م")
        self.lbl_total.setStyleSheet("font-size: 18px; font-weight: bold; color: #0F172A;")
        tot_box.addWidget(self.lbl_total)
        foot_layout.addLayout(tot_box)

        # Paid Amount
        paid_box = QVBoxLayout()
        paid_box.setSpacing(2)
        paid_box.addWidget(QLabel("المدفوع نقداً للمورد:"))
        self.paid_edit = QLineEdit("0.00")
        self.paid_edit.setFixedHeight(38)
        self.paid_edit.setFixedWidth(130)
        self.paid_edit.setValidator(QDoubleValidator(0.0, 9999999.0, 2))
        self.paid_edit.textChanged.connect(self._recalc_totals)
        paid_box.addWidget(self.paid_edit)
        foot_layout.addLayout(paid_box)

        # Cash Account
        acc_box = QVBoxLayout()
        acc_box.setSpacing(2)
        acc_box.addWidget(QLabel("الخزينة المسحوب منها:"))
        self.acc_combo = QComboBox()
        self.acc_combo.setFixedHeight(38)
        self.acc_combo.setMinimumWidth(160)
        acc_box.addWidget(self.acc_combo)
        foot_layout.addLayout(acc_box)

        # Remaining to balance
        rem_box = QVBoxLayout()
        rem_box.setSpacing(2)
        rem_box.addWidget(QLabel("المتبقي كدين للمورد:"))
        self.lbl_remaining = QLabel("0.00 ج.م")
        self.lbl_remaining.setStyleSheet("font-size: 16px; font-weight: bold; color: #DC2626;")
        rem_box.addWidget(self.lbl_remaining)
        foot_layout.addLayout(rem_box)

        foot_layout.addStretch()

        # Save Button
        self.btn_save = QPushButton("💾 ترحيل وحفظ الفاتورة")
        self.btn_save.setFixedHeight(44)
        self.btn_save.setStyleSheet("""
            QPushButton {
                background-color: #16A34A;
                color: white;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                padding: 0 28px;
            }
            QPushButton:hover {
                background-color: #15803D;
            }
        """)
        self.btn_save.clicked.connect(self._save_purchase)
        foot_layout.addWidget(self.btn_save)

        main_layout.addWidget(foot_card)

        self._current_pending_imeis: list[dict] = []

    def _load_suppliers(self):
        self.supplier_combo.clear()
        suppliers = purchase_service.list_suppliers(self.session, self.user)
        for s in suppliers:
            bal_str = f" (رصيد: {format_money(s.balance)})" if s.balance else ""
            self.supplier_combo.addItem(f"{s.name}{bal_str}", s.id)

    def _load_products(self):
        self.product_combo.clear()
        products = self.session.query(Product).filter(Product.is_active == True).order_by(Product.name.asc()).all()
        for p in products:
            icon = "📱 " if p.track_imei else "🎧 "
            self.product_combo.addItem(f"{icon}{p.name}", p)

    def _load_cash_accounts(self):
        self.acc_combo.clear()
        accounts = self.session.query(CashAccount).all()
        for a in accounts:
            self.acc_combo.addItem(f"{a.name} ({format_money(a.balance)})", a.id)

    def _add_new_supplier(self):
        dlg = SupplierDialog(self.session, self.user, parent=self)
        if dlg.exec() == QDialog.Accepted and dlg.supplier:
            self._load_suppliers()
            # Select new supplier
            idx = self.supplier_combo.findData(dlg.supplier.id)
            if idx >= 0:
                self.supplier_combo.setCurrentIndex(idx)

    def _on_product_selected(self):
        product: Optional[Product] = self.product_combo.currentData()
        self._current_pending_imeis = []
        if product:
            self.cost_edit.setText(f"{product.cost_price / 100:.2f}")
            if product.track_imei:
                self.btn_imei.setEnabled(True)
                qty = int(self.qty_edit.text() or 1)
                self.btn_imei.setText(f"🔢 إدخال ({qty}) سيريال IMEI")
                self.btn_imei.setStyleSheet("background-color: #FEF3C7; color: #B45309; border: 1px solid #F59E0B; border-radius: 8px; font-weight: bold;")
            else:
                self.btn_imei.setEnabled(False)
                self.btn_imei.setText("غير مطلوب (إكسسوار)")
                self.btn_imei.setStyleSheet("background-color: #F8FAFC; color: #94A3B8; border: 1px dashed #CBD5E1; border-radius: 8px;")

    def _recalc_line_hint(self):
        product: Optional[Product] = self.product_combo.currentData()
        if product and product.track_imei:
            qty = int(self.qty_edit.text() or 1)
            self.btn_imei.setText(f"🔢 إدخال ({qty}) سيريال IMEI")

    def _open_imei_dialog(self):
        product: Optional[Product] = self.product_combo.currentData()
        if not product or not product.track_imei:
            return
        qty = int(self.qty_edit.text() or 1)
        dlg = IMEIInputDialog(product.name, qty, existing_imeis=self._current_pending_imeis, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self._current_pending_imeis = dlg.imeis
            self.btn_imei.setText(f"✅ تم إدخال ({len(self._current_pending_imeis)}) سيريال")
            self.btn_imei.setStyleSheet("background-color: #DCFCE7; color: #15803D; border: 1px solid #86EFAC; border-radius: 8px; font-weight: bold;")

    def _add_line_item(self):
        product: Optional[Product] = self.product_combo.currentData()
        if not product:
            QMessageBox.warning(self, "تنبيه", "يرجى اختيار المنتج أولاً")
            return

        try:
            qty = int(self.qty_edit.text() or 0)
            if qty <= 0:
                raise ValueError()
        except ValueError:
            QMessageBox.warning(self, "تنبيه", "الكمية يجب أن تكون رقماً أكبر من الصفر")
            self.qty_edit.setFocus()
            return

        try:
            cost_piasters = egp_to_piasters(self.cost_edit.text() or 0)
            if cost_piasters < 0:
                raise ValueError()
        except Exception:
            QMessageBox.warning(self, "تنبيه", "سعر التكلفة غير صحيح")
            self.cost_edit.setFocus()
            return

        # Check IMEI requirement for phones
        if product.track_imei:
            if len(self._current_pending_imeis) != qty:
                QMessageBox.warning(
                    self,
                    "تنبيه",
                    f"المنتج '{product.name}' يتطلب إدخال {qty} سيريال IMEI.\nيرجى النقر على زر إدخال السيريالات واستكمالها."
                )
                self._open_imei_dialog()
                return

        item_entry = {
            "product_id": product.id,
            "product_name": product.name,
            "track_imei": product.track_imei,
            "quantity": qty,
            "unit_cost": cost_piasters,
            "total": qty * cost_piasters,
            "imeis": list(self._current_pending_imeis),
        }
        self.items_data.append(item_entry)

        # Reset line inputs
        self._current_pending_imeis = []
        self.qty_edit.setText("1")
        self._on_product_selected()
        self._refresh_table()
        self._recalc_totals()

    def _refresh_table(self):
        self.table.setRowCount(len(self.items_data))
        for idx, it in enumerate(self.items_data):
            # 0: Num
            item_num = QTableWidgetItem(str(idx + 1))
            item_num.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(idx, 0, item_num)

            # 1: Name
            item_name = QTableWidgetItem(it["product_name"])
            self.table.setItem(idx, 1, item_name)

            # 2: Qty
            item_qty = QTableWidgetItem(str(it["quantity"]))
            item_qty.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(idx, 2, item_qty)

            # 3: Unit Cost
            item_cost = QTableWidgetItem(format_money(it["unit_cost"]))
            item_cost.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(idx, 3, item_cost)

            # 4: Total
            item_tot = QTableWidgetItem(format_money(it["total"]))
            item_tot.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(idx, 4, item_tot)

            # 5: IMEIs
            if it["track_imei"]:
                imei_str = f"📱 {len(it['imeis'])} سيريال مسجل"
            else:
                imei_str = "—"
            item_imei = QTableWidgetItem(imei_str)
            item_imei.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(idx, 5, item_imei)

            # 6: Delete
            btn_del = QPushButton("❌")
            btn_del.setStyleSheet("border: none; background: transparent; color: #EF4444; font-weight: bold;")
            btn_del.clicked.connect(lambda _, row=idx: self._delete_line(row))
            self.table.setCellWidget(idx, 6, btn_del)

    def _delete_line(self, row: int):
        if 0 <= row < len(self.items_data):
            self.items_data.pop(row)
            self._refresh_table()
            self._recalc_totals()

    def _recalc_totals(self):
        total_piasters = sum(it["total"] for it in self.items_data)
        self.lbl_total.setText(format_money(total_piasters))

        paid_text = self.paid_edit.text().strip()
        try:
            paid_piasters = egp_to_piasters(paid_text) if paid_text else 0
        except Exception:
            paid_piasters = 0

        rem_piasters = total_piasters - paid_piasters
        self.lbl_remaining.setText(format_money(rem_piasters))
        if rem_piasters > 0:
            self.lbl_remaining.setStyleSheet("font-size: 16px; font-weight: bold; color: #DC2626;")
        else:
            self.lbl_remaining.setStyleSheet("font-size: 16px; font-weight: bold; color: #16A34A;")

    def _save_purchase(self):
        supplier_id = self.supplier_combo.currentData()
        if not supplier_id:
            QMessageBox.warning(self, "تنبيه", "يرجى اختيار المورد")
            return

        inv_no = self.inv_no_edit.text().strip()
        if not inv_no:
            QMessageBox.warning(self, "تنبيه", "يرجى إدخال رقم الفاتورة")
            self.inv_no_edit.setFocus()
            return

        if not self.items_data:
            QMessageBox.warning(self, "تنبيه", "لا يمكن حفظ فاتورة شراء بدون أصناف")
            return

        total_piasters = sum(it["total"] for it in self.items_data)
        try:
            paid_text = self.paid_edit.text().strip()
            paid_piasters = egp_to_piasters(paid_text) if paid_text else 0
        except Exception:
            QMessageBox.warning(self, "تنبيه", "صيغة المبلغ المدفوع غير صحيحة")
            return

        if paid_piasters < 0:
            QMessageBox.warning(self, "تنبيه", "المبلغ المدفوع لا يمكن أن يكون سالباً")
            return
        if paid_piasters > total_piasters:
            QMessageBox.warning(self, "تنبيه", "المبلغ المدفوع أكبر من إجمالي الفاتورة")
            return

        account_id = self.acc_combo.currentData()
        notes = self.notes_edit.text().strip()

        try:
            purchase = purchase_service.create_purchase(
                session=self.session,
                user=self.user,
                supplier_id=supplier_id,
                invoice_number=inv_no,
                items_data=self.items_data,
                paid_amount=paid_piasters,
                account_id=account_id,
                notes=notes,
            )
            self.session.commit()
            QMessageBox.information(
                self,
                "تمت العملية بنجاح",
                f"تم ترحيل وحفظ فاتورة الشراء رقم {purchase.invoice_number} بإجمالي {format_money(purchase.total)} بنجاح!"
            )
            self.accept()
        except Exception as e:
            self.session.rollback()
            QMessageBox.critical(self, "خطأ أثناء حفظ الفاتورة", f"تعذر حفظ فاتورة الشراء:\n{str(e)}")

