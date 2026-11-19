"""Modern Purchase Invoice Dialog for entering supplier invoices with IMEI support."""
from __future__ import annotations
from app.i18n import ar

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

from app.core.money import egp_to_piasters, format_money, piasters_to_egp, piasters_to_input
from app.models.accounting import CashAccount
from app.models.product import Product
from app.models.purchase import Supplier
from app.services import purchase_service
from app.ui.purchases.imei_input_dialog import IMEIInputDialog
from app.ui.purchases.supplier_dialog import SupplierDialog
from app.ui.design.style import set_prop, style_label, variant
from app.ui.design import icons
from app.ui.design.tokens import COLORS


from app.ui.components import icon_button, show_error, show_toast


class PurchaseInvoiceDialog(QDialog):
    def __init__(self, session, user, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self.items_data: list[dict] = []
        self.setWindowTitle(ar.PURCHASE_INVOICE_DIALOG_E74EFD)
        self.resize(960, 680)
        self.setModal(True)

        self._current_pending_imeis: list[dict] = []
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
        icon = QLabel()
        icon.setPixmap(icons.pixmap("package", COLORS["primary"], 28))
        hdr.addWidget(icon)

        t_box = QVBoxLayout()
        t_box.setSpacing(2)
        lbl_t = QLabel(ar.PURCHASE_INVOICE_DIALOG_CF08F9)
        style_label(lbl_t, size="h2", tone="text", bold=True)
        lbl_sub = QLabel(ar.PURCHASE_INVOICE_DIALOG_0B417E)
        style_label(lbl_sub, size="caption", tone="muted")
        t_box.addWidget(lbl_t)
        t_box.addWidget(lbl_sub)
        hdr.addLayout(t_box)
        hdr.addStretch()
        main_layout.addLayout(hdr)

        # ── Invoice Meta Card ───────────────────────────────
        meta_card = QFrame()
        set_prop(meta_card, "card", True)
        meta_grid = QGridLayout(meta_card)
        meta_grid.setHorizontalSpacing(14)
        meta_grid.setVerticalSpacing(8)

        # Supplier
        meta_grid.addWidget(QLabel(ar.PURCHASE_INVOICE_DIALOG_66A916), 0, 0)
        sup_box = QHBoxLayout()
        self.supplier_combo = QComboBox()
        self.supplier_combo.setMinimumHeight(40)
        self.supplier_combo.setMinimumWidth(220)
        sup_box.addWidget(self.supplier_combo)

        btn_add_sup = QPushButton(ar.DEVICE_CONDITION_NEW)
        btn_add_sup.setMinimumHeight(40)
        variant(btn_add_sup, "secondary")
        btn_add_sup.clicked.connect(self._add_new_supplier)
        sup_box.addWidget(btn_add_sup)
        meta_grid.addLayout(sup_box, 1, 0)

        # Invoice Number
        meta_grid.addWidget(QLabel(ar.PURCHASE_INVOICE_DIALOG_E5E3E3), 0, 1)
        self.inv_no_edit = QLineEdit()
        self.inv_no_edit.setMinimumHeight(40)
        default_inv = f"PUR-{datetime.datetime.now().strftime('%Y%m%d-%H%M')}"
        self.inv_no_edit.setText(default_inv)
        meta_grid.addWidget(self.inv_no_edit, 1, 1)

        # Notes
        meta_grid.addWidget(QLabel(ar.PURCHASE_INVOICE_DIALOG_100668), 0, 2)
        self.notes_edit = QLineEdit()
        self.notes_edit.setMinimumHeight(40)
        self.notes_edit.setPlaceholderText(ar.PURCHASE_INVOICE_DIALOG_28C2F6)
        meta_grid.addWidget(self.notes_edit, 1, 2)

        main_layout.addWidget(meta_card)

        # ── Add Line Item Section ───────────────────────────
        line_card = QFrame()
        set_prop(line_card, "card", True)
        line_grid = QGridLayout(line_card)
        line_grid.setHorizontalSpacing(12)
        line_grid.setVerticalSpacing(8)

        # Product Selector
        line_grid.addWidget(QLabel(ar.PURCHASE_INVOICE_DIALOG_6AA60B), 0, 0)
        self.product_search = QLineEdit()
        self.product_search.setMinimumHeight(40)
        self.product_search.setPlaceholderText(ar.PURCHASE_PRODUCT_SEARCH)
        self.product_search.setClearButtonEnabled(True)
        self.product_search.textChanged.connect(self._load_products)
        self.product_search.returnPressed.connect(self._pick_by_barcode)
        line_grid.addWidget(self.product_search, 2, 0, 1, 5)
        self.product_combo = QComboBox()
        self.product_combo.setMinimumHeight(40)
        self.product_combo.currentIndexChanged.connect(self._on_product_selected)
        line_grid.addWidget(self.product_combo, 1, 0)

        # Quantity
        line_grid.addWidget(QLabel(ar.PURCHASE_INVOICE_DIALOG_EA028B), 0, 1)
        self.qty_edit = QLineEdit("1")
        self.qty_edit.setMinimumHeight(40)
        self.qty_edit.setFixedWidth(80)
        self.qty_edit.setValidator(QIntValidator(1, 99999))
        self.qty_edit.textChanged.connect(self._recalc_line_hint)
        self.qty_edit.returnPressed.connect(self._add_line_item)
        line_grid.addWidget(self.qty_edit, 1, 1)

        # Unit Cost
        line_grid.addWidget(QLabel(ar.PURCHASE_INVOICE_DIALOG_17C391), 0, 2)
        self.cost_edit = QLineEdit()
        self.cost_edit.setMinimumHeight(40)
        self.cost_edit.setFixedWidth(120)
        self.cost_edit.setValidator(QDoubleValidator(0.0, 9999999.0, 2))
        self.cost_edit.textChanged.connect(self._recalc_line_hint)
        self.cost_edit.returnPressed.connect(self._add_line_item)
        line_grid.addWidget(self.cost_edit, 1, 2)

        # IMEI Action (for phones)
        line_grid.addWidget(QLabel(ar.PURCHASE_INVOICE_DIALOG_C6B92E), 0, 3)
        self.btn_imei = QPushButton(ar.PURCHASE_INVOICE_DIALOG_EE9BBF)
        self.btn_imei.setMinimumHeight(40)
        self.btn_imei.setEnabled(False)
        variant(self.btn_imei, "secondary")
        self.btn_imei.clicked.connect(self._open_imei_dialog)
        line_grid.addWidget(self.btn_imei, 1, 3)

        # Add Line Button
        self.btn_add_line = QPushButton(ar.PURCHASE_INVOICE_DIALOG_092130)
        self.btn_add_line.setMinimumHeight(40)
        variant(self.btn_add_line, "primary")
        self.btn_add_line.clicked.connect(self._add_line_item)
        line_grid.addWidget(self.btn_add_line, 1, 4)

        main_layout.addWidget(line_card)

        # ── Items Table ─────────────────────────────────────
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "#", ar.LOW_STOCK_WIDGET_1AB391, ar.RECEIPT_COL_QTY, ar.CART_UNIT_PRICE, ar.TOTAL, ar.PURCHASE_INVOICE_DIALOG_7EF49A, ar.DELETE
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
        set_prop(foot_card, "card", True)
        foot_layout = QHBoxLayout(foot_card)
        foot_layout.setSpacing(16)

        # Total Invoice
        tot_box = QVBoxLayout()
        tot_box.setSpacing(2)
        tot_box.addWidget(QLabel(ar.PURCHASE_INVOICE_DIALOG_0EF926))
        self.lbl_total = QLabel(ar.DAILY_CLOSE_DIALOG_388B15)
        style_label(self.lbl_total, size="h2", tone="text", bold=True)
        tot_box.addWidget(self.lbl_total)
        foot_layout.addLayout(tot_box)

        # Paid Amount
        paid_box = QVBoxLayout()
        paid_box.setSpacing(2)
        paid_box.addWidget(QLabel(ar.PURCHASE_INVOICE_DIALOG_9C7D89))
        self.paid_edit = QLineEdit("0.00")
        self.paid_edit.setMinimumHeight(40)
        self.paid_edit.setFixedWidth(130)
        self.paid_edit.setValidator(QDoubleValidator(0.0, 9999999.0, 2))
        self.paid_edit.textChanged.connect(self._recalc_totals)
        paid_box.addWidget(self.paid_edit)
        foot_layout.addLayout(paid_box)

        # Cash Account
        acc_box = QVBoxLayout()
        acc_box.setSpacing(2)
        acc_box.addWidget(QLabel(ar.PURCHASE_INVOICE_DIALOG_D2AD7B))
        self.acc_combo = QComboBox()
        self.acc_combo.setMinimumHeight(40)
        self.acc_combo.setMinimumWidth(160)
        acc_box.addWidget(self.acc_combo)
        foot_layout.addLayout(acc_box)

        # Remaining to balance
        rem_box = QVBoxLayout()
        rem_box.setSpacing(2)
        rem_box.addWidget(QLabel(ar.PURCHASE_INVOICE_DIALOG_A2A30D))
        self.lbl_remaining = QLabel(ar.DAILY_CLOSE_DIALOG_388B15)
        style_label(self.lbl_remaining, size="title", tone="danger", bold=True)
        rem_box.addWidget(self.lbl_remaining)
        foot_layout.addLayout(rem_box)

        foot_layout.addStretch()

        # Save Button
        self.btn_save = QPushButton(ar.PURCHASE_INVOICE_DIALOG_423198)
        self.btn_save.setFixedHeight(44)
        variant(self.btn_save, "success")
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
        if not suppliers:
            self.supplier_combo.addItem(ar.PURCHASE_NO_SUPPLIERS, None)

    def _load_products(self, *_args):
        text = self.product_search.text().strip().lower() if hasattr(self, "product_search") else ""
        self.product_combo.blockSignals(True)
        self.product_combo.clear()
        products = self.session.query(Product).filter(Product.is_active == True).order_by(Product.name.asc()).all()
        for p in products:
            if text and text not in p.name.lower() and not any(text in b.lower() for b in p.all_barcodes()):
                continue
            self.product_combo.addItem(p.name, p)
        if self.product_combo.count() == 0:
            self.product_combo.addItem(ar.PURCHASE_NO_PRODUCTS, None)
        self.product_combo.blockSignals(False)
        self._on_product_selected()

    def _pick_by_barcode(self):
        """A scanned (or typed) barcode that belongs to a product selects it and moves on to the quantity."""
        from app.services import inventory_service
        product = inventory_service.find_product_by_barcode(self.session, self.product_search.text())
        if product is None or not product.is_active:
            return
        self.product_search.blockSignals(True)
        self.product_search.setText(product.name)
        self.product_search.blockSignals(False)
        self._load_products()
        idx = next((i for i in range(self.product_combo.count())
                    if getattr(self.product_combo.itemData(i), "id", None) == product.id), -1)
        if idx >= 0:
            self.product_combo.setCurrentIndex(idx)
            self._on_product_selected()
            self.qty_edit.setFocus()
            self.qty_edit.selectAll()

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
            self.cost_edit.setText(f"{piasters_to_input(product.cost_price)}")
            if product.track_imei:
                self.btn_imei.setEnabled(True)
                qty = int(self.qty_edit.text() or 1)
                self.btn_imei.setText(f"إدخال ({qty}) سيريال IMEI")
                variant(self.btn_imei, "secondary")
            else:
                self.btn_imei.setEnabled(False)
                self.btn_imei.setText(ar.PURCHASE_INVOICE_DIALOG_92910D)
                variant(self.btn_imei, "secondary")

    def _recalc_line_hint(self):
        product: Optional[Product] = self.product_combo.currentData()
        if product and product.track_imei:
            qty = int(self.qty_edit.text() or 1)
            self.btn_imei.setText(f"إدخال ({qty}) سيريال IMEI")

    def _open_imei_dialog(self):
        product: Optional[Product] = self.product_combo.currentData()
        if not product or not product.track_imei:
            return
        qty = int(self.qty_edit.text() or 1)
        dlg = IMEIInputDialog(product.name, qty, existing_imeis=self._current_pending_imeis, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self._current_pending_imeis = dlg.imeis
            self.btn_imei.setText(f"تم إدخال ({len(self._current_pending_imeis)}) سيريال")
            variant(self.btn_imei, "secondary")

    def _add_line_item(self):
        product: Optional[Product] = self.product_combo.currentData()
        if not product:
            show_error(self, message=ar.PURCHASE_INVOICE_DIALOG_3CD7EF)
            return

        try:
            qty = int(self.qty_edit.text() or 0)
            if qty <= 0:
                raise ValueError()
        except ValueError:
            show_error(self, message=ar.PURCHASE_INVOICE_DIALOG_A018BD)
            self.qty_edit.setFocus()
            return

        try:
            cost_piasters = egp_to_piasters(self.cost_edit.text() or 0)
            if cost_piasters < 0:
                raise ValueError()
        except Exception:
            show_error(self, message=ar.PURCHASE_INVOICE_DIALOG_49C717)
            self.cost_edit.setFocus()
            return

        # Check IMEI requirement for phones
        if product.track_imei:
            if len(self._current_pending_imeis) != qty:
                show_error(self, message=f"المنتج '{product.name}' يتطلب إدخال {qty} سيريال IMEI.\nيرجى النقر على زر إدخال السيريالات واستكمالها.")
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
                imei_str = f"{len(it['imeis'])} سيريال مسجل"
            else:
                imei_str = "—"
            item_imei = QTableWidgetItem(imei_str)
            item_imei.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(idx, 5, item_imei)

            # 6: Delete
            btn_del = icon_button("trash-2", ar.DELETE, "danger-soft")
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
            style_label(self.lbl_remaining, size="title", tone="danger", bold=True)
        else:
            style_label(self.lbl_remaining, size="title", tone="success", bold=True)

    def _save_purchase(self):
        supplier_id = self.supplier_combo.currentData()
        if not supplier_id:
            show_error(self, message=ar.PURCHASE_INVOICE_DIALOG_7AF7D0)
            return

        inv_no = self.inv_no_edit.text().strip()
        if not inv_no:
            show_error(self, message=ar.PURCHASE_INVOICE_DIALOG_F9C4FB)
            self.inv_no_edit.setFocus()
            return

        if not self.items_data:
            show_error(self, message=ar.PURCHASE_INVOICE_DIALOG_C6749B)
            return

        total_piasters = sum(it["total"] for it in self.items_data)
        try:
            paid_text = self.paid_edit.text().strip()
            paid_piasters = egp_to_piasters(paid_text) if paid_text else 0
        except Exception:
            show_error(self, message=ar.PURCHASE_INVOICE_DIALOG_0B97BD)
            return

        if paid_piasters < 0:
            show_error(self, message=ar.PURCHASE_INVOICE_DIALOG_E2C151)
            return
        if paid_piasters > total_piasters:
            show_error(self, message=ar.PURCHASE_INVOICE_DIALOG_8FC5FE)
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
            show_toast(self, f"تم ترحيل وحفظ فاتورة الشراء رقم {purchase.invoice_number} بإجمالي {format_money(purchase.total)} بنجاح!")
            self.accept()
        except Exception as e:
            self.session.rollback()
            show_error(self, message=f"تعذر حفظ فاتورة الشراء:\n{str(e)}")

