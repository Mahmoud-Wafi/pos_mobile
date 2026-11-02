"""POS (Point of Sale) main cash register screen."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

try:
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
        QTableWidgetItem, QHeaderView, QLabel, QLineEdit, QComboBox,
        QMessageBox, QFrame, QSplitter, QDialog, QInputDialog,
    )
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QColor, QFont, QKeySequence, QShortcut
    HAS_QT = True
except ImportError:
    HAS_QT = False

from app.core.money import format_money, egp_to_piasters
from app.models.product import Product
from app.models.stock import Device
from app.models.customer import Customer
from app.services import sales_service, shift_service, customer_service, inventory_service
from app.ui.pos.payment_dialog import PaymentDialog
from app.printing.receipt import generate_thermal_receipt_text, generate_warranty_invoice_pdf


HEADERS = ["#", "اسم الصنف", "السيريال (IMEI)", "الكمية", "سعر الوحدة", "الخصم", "الإجمالي", "حذف"]


if HAS_QT:
    class POSWindow(QWidget):
        """Main POS cash register window."""

        def __init__(self, session, user, parent=None):
            super().__init__(parent)
            self.session = session
            self.user = user
            self.current_sale = None
            self._build_ui()
            self._setup_shortcuts()
            self._check_shift_and_init_sale()

        def _build_ui(self):
            root_layout = QVBoxLayout(self)
            root_layout.setContentsMargins(14, 14, 14, 14)
            root_layout.setSpacing(12)

            # Shift alert banner (if shift is closed)
            self.shift_banner = QFrame()
            self.shift_banner.setStyleSheet("background-color: #FEF3C7; border: 1px solid #FCD34D; border-radius: 8px; padding: 10px;")
            sb_layout = QHBoxLayout(self.shift_banner)
            sb_layout.setContentsMargins(8, 4, 8, 4)
            self.lbl_shift_msg = QLabel("⚠️ تنبيه: لا توجد وردية مفتوحة حالياً للكاشير. يجب فتح الوردية للتمكن من البيع.")
            self.lbl_shift_msg.setStyleSheet("color: #92400E; font-weight: bold;")
            btn_open_shift = QPushButton("🔓 فتح الوردية الآن")
            btn_open_shift.setStyleSheet("background-color: #D97706; color: #FFFFFF; font-weight: bold; border-radius: 6px; padding: 6px 14px;")
            btn_open_shift.clicked.connect(self._open_shift_dialog)
            sb_layout.addWidget(self.lbl_shift_msg)
            sb_layout.addStretch()
            sb_layout.addWidget(btn_open_shift)
            root_layout.addWidget(self.shift_banner)

            # Main Body: Splitter (Cart Table on right/main + Totals sidebar on left)
            splitter = QSplitter(Qt.Horizontal)

            # ── Right / Main: Scanner Bar + Cart Table ──
            cart_widget = QWidget()
            cart_layout = QVBoxLayout(cart_widget)
            cart_layout.setContentsMargins(0, 0, 0, 0)
            cart_layout.setSpacing(10)

            # Scanner & Customer toolbar
            top_bar = QHBoxLayout()
            top_bar.setSpacing(10)

            # Barcode / IMEI scanner input
            self.scan_edit = QLineEdit()
            self.scan_edit.setPlaceholderText("🔍 امسح الباركود أو اكتب رقم السيريال (IMEI) أو اسم الصنف واضغط Enter...")
            self.scan_edit.setFixedHeight(44)
            self.scan_edit.setStyleSheet("font-size: 14px; font-weight: bold;")
            self.scan_edit.returnPressed.connect(self._on_scan_or_search)
            top_bar.addWidget(self.scan_edit, 3)

            # Customer Selector
            self.customer_combo = QComboBox()
            self.customer_combo.setFixedHeight(44)
            self.customer_combo.setMinimumWidth(180)
            self._load_customers()
            self.customer_combo.currentIndexChanged.connect(self._on_customer_changed)
            top_bar.addWidget(self.customer_combo, 1)

            btn_new_cust = QPushButton("عميل جديد +")
            btn_new_cust.setFixedHeight(44)
            btn_new_cust.clicked.connect(self._add_quick_customer)
            top_bar.addWidget(btn_new_cust)

            cart_layout.addLayout(top_bar)

            # Cart Table
            self.cart_table = QTableWidget()
            self.cart_table.setColumnCount(len(HEADERS))
            self.cart_table.setHorizontalHeaderLabels(HEADERS)
            self.cart_table.verticalHeader().setVisible(False)
            self.cart_table.verticalHeader().setDefaultSectionSize(46)
            self.cart_table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.cart_table.setSelectionBehavior(QTableWidget.SelectRows)
            self.cart_table.setAlternatingRowColors(True)

            header = self.cart_table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.Fixed); self.cart_table.setColumnWidth(0, 45)   # #
            header.setSectionResizeMode(1, QHeaderView.Stretch)                                         # Name
            header.setSectionResizeMode(2, QHeaderView.Fixed); self.cart_table.setColumnWidth(2, 170) # IMEI
            header.setSectionResizeMode(3, QHeaderView.Fixed); self.cart_table.setColumnWidth(3, 80)  # Qty
            header.setSectionResizeMode(4, QHeaderView.Fixed); self.cart_table.setColumnWidth(4, 120) # Price
            header.setSectionResizeMode(5, QHeaderView.Fixed); self.cart_table.setColumnWidth(5, 90)  # Discount
            header.setSectionResizeMode(6, QHeaderView.Fixed); self.cart_table.setColumnWidth(6, 130) # Total
            header.setSectionResizeMode(7, QHeaderView.Fixed); self.cart_table.setColumnWidth(7, 70)  # Delete

            cart_layout.addWidget(self.cart_table)

            # Quick POS shortcuts toolbar at bottom of cart
            bot_bar = QHBoxLayout()
            bot_bar.setSpacing(10)

            btn_new_inv = QPushButton("📄 فاتورة جديدة [F9]")
            btn_new_inv.clicked.connect(self._new_invoice)
            bot_bar.addWidget(btn_new_inv)

            btn_hold = QPushButton("⏸️ تعليق الفاتورة")
            btn_hold.clicked.connect(self._hold_invoice)
            bot_bar.addWidget(btn_hold)

            self.btn_resume = QPushButton("▶️ استرجاع المعلق")
            self.btn_resume.clicked.connect(self._resume_held_dialog)
            bot_bar.addWidget(self.btn_resume)

            bot_bar.addStretch()

            btn_clear = QPushButton("❌ تفريغ السلة [Esc]")
            btn_clear.clicked.connect(self._clear_cart)
            bot_bar.addWidget(btn_clear)

            cart_layout.addLayout(bot_bar)
            splitter.addWidget(cart_widget)

            # ── Left / Sidebar: Invoice Summary & Big Checkout Button ──
            summary_card = QFrame()
            summary_card.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 12px; padding: 16px;")
            summary_card.setMinimumWidth(320)
            summary_card.setMaximumWidth(360)
            s_layout = QVBoxLayout(summary_card)
            s_layout.setContentsMargins(12, 12, 12, 12)
            s_layout.setSpacing(14)

            # Invoice info
            self.lbl_inv_no = QLabel("رقم الفاتورة: —")
            self.lbl_inv_no.setStyleSheet("font-size: 14px; font-weight: bold; color: #0F172A;")
            s_layout.addWidget(self.lbl_inv_no)

            line = QFrame(); line.setFrameShape(QFrame.HLine); line.setStyleSheet("color: #E2E8F0;"); s_layout.addWidget(line)

            # Totals rows
            row_sub = QHBoxLayout()
            row_sub.addWidget(QLabel("المجموع الفرعي:"))
            self.lbl_subtotal = QLabel("0.00 ج.م")
            self.lbl_subtotal.setStyleSheet("font-weight: bold;")
            row_sub.addStretch(); row_sub.addWidget(self.lbl_subtotal)
            s_layout.addLayout(row_sub)

            # Discount row
            row_disc = QHBoxLayout()
            row_disc.addWidget(QLabel("الخصم الإضافي (ج.م):"))
            self.disc_edit = QLineEdit("0")
            self.disc_edit.setFixedWidth(100)
            self.disc_edit.setAlignment(Qt.AlignCenter)
            self.disc_edit.textChanged.connect(self._on_discount_changed)
            row_disc.addStretch(); row_disc.addWidget(self.disc_edit)
            s_layout.addLayout(row_disc)

            # Big Total Card
            total_box = QFrame()
            total_box.setStyleSheet("background-color: #0F172A; border-radius: 10px; padding: 16px;")
            tb_layout = QVBoxLayout(total_box)
            tb_layout.setAlignment(Qt.AlignCenter)
            tb_title = QLabel("صافي الإجمالي المطلوب")
            tb_title.setStyleSheet("color: #94A3B8; font-size: 13px; font-weight: bold;")
            tb_title.setAlignment(Qt.AlignCenter)
            self.lbl_big_total = QLabel("0.00 ج.م")
            self.lbl_big_total.setStyleSheet("color: #38BDF8; font-size: 26px; font-weight: 800;")
            self.lbl_big_total.setAlignment(Qt.AlignCenter)
            tb_layout.addWidget(tb_title)
            tb_layout.addWidget(self.lbl_big_total)
            s_layout.addWidget(total_box)

            s_layout.addStretch()

            # Checkout Button
            self.btn_pay = QPushButton("💳  الدفع وإنهاء الفاتورة [F4]")
            self.btn_pay.setFixedHeight(54)
            self.btn_pay.setStyleSheet("""
                QPushButton {
                    background-color: #059669;
                    color: #FFFFFF;
                    font-size: 16px;
                    font-weight: 800;
                    border: none;
                    border-radius: 10px;
                }
                QPushButton:hover {
                    background-color: #047857;
                }
                QPushButton:disabled {
                    background-color: #CBD5E1;
                    color: #94A3B8;
                }
            """)
            self.btn_pay.clicked.connect(self._on_checkout)
            s_layout.addWidget(self.btn_pay)

            splitter.addWidget(summary_card)
            root_layout.addWidget(splitter)

        def _setup_shortcuts(self):
            QShortcut(QKeySequence("F2"), self, self._focus_search)
            QShortcut(QKeySequence("F4"), self, self._on_checkout)
            QShortcut(QKeySequence("F9"), self, self._new_invoice)
            QShortcut(QKeySequence("Escape"), self, self._clear_cart)

        def _focus_search(self):
            self.scan_edit.setFocus()
            self.scan_edit.selectAll()

        def _check_shift_and_init_sale(self):
            active_shift = shift_service.get_active_shift(self.session, self.user.id)
            if active_shift:
                self.shift_banner.setVisible(False)
                self.btn_pay.setEnabled(True)
            else:
                self.shift_banner.setVisible(True)
                self.btn_pay.setEnabled(False)

            if not self.current_sale:
                self._new_invoice()

        def _load_customers(self):
            self.customer_combo.clear()
            customers = customer_service.search_customers(self.session)
            for c in customers:
                self.customer_combo.addItem(f"👤 {c.name}", c.id)

        def _on_customer_changed(self):
            if self.current_sale:
                cust_id = self.customer_combo.currentData()
                if cust_id:
                    self.current_sale.customer_id = cust_id
                    self.session.flush()

        def _new_invoice(self):
            try:
                cust_id = self.customer_combo.currentData()
                self.current_sale = sales_service.start_sale(
                    self.session, self.user, customer_id=cust_id
                )
                self.lbl_inv_no.setText(f"رقم الفاتورة: {self.current_sale.invoice_no}")
                self.disc_edit.setText("0")
                self._refresh_cart()
                self._focus_search()
            except Exception as e:
                QMessageBox.critical(self, "خطأ", str(e))

        def _on_scan_or_search(self):
            query = self.scan_edit.text().strip()
            if not query:
                return

            # Find by Barcode or IMEI
            found = inventory_service.find_by_barcode_or_imei(self.session, query)
            if not found:
                # Try search by partial name
                prods = self.session.query(Product).filter(Product.name.ilike(f"%{query}%")).all()
                if prods:
                    found = prods[0]

            if not found:
                QMessageBox.warning(self, "تنبيه", f"لم يتم العثور على أي صنف أو سيريال يطابق: {query}")
                self._focus_search()
                return

            try:
                if isinstance(found, Device):
                    # It's an IMEI device!
                    sales_service.add_line(
                        self.session, self.user, self.current_sale,
                        found.product, quantity=1, device=found
                    )
                else:
                    # It's a product
                    if found.track_imei:
                        # Need to choose an available in_stock device
                        devices = inventory_service.get_devices_for_product(self.session, found.id, status="in_stock")
                        if not devices:
                            QMessageBox.warning(self, "تنبيه", f"لا توجد أجهزة متوفرة في المخزن للصنف '{found.name}'")
                            self._focus_search()
                            return
                        device = devices[0]
                        sales_service.add_line(
                            self.session, self.user, self.current_sale,
                            found, quantity=1, device=device
                        )
                    else:
                        sales_service.add_line(
                            self.session, self.user, self.current_sale,
                            found, quantity=1
                        )

                self.session.flush()
                self.scan_edit.clear()
                self._refresh_cart()
            except Exception as e:
                QMessageBox.critical(self, "خطأ في إضافة الصنف", str(e))

            self._focus_search()

        def _refresh_cart(self):
            if not self.current_sale:
                return

            items = self.current_sale.items
            self.cart_table.setRowCount(len(items))

            for row, it in enumerate(items):
                imei_str = it.device.imei1 if it.device else "—"

                cols = [
                    str(row + 1),
                    it.product.name,
                    imei_str,
                    str(it.quantity),
                    format_money(it.unit_price),
                    format_money(it.discount),
                    format_money(it.line_total),
                ]

                for col, text in enumerate(cols):
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignCenter if col != 1 else (Qt.AlignRight | Qt.AlignVCenter))
                    if col in (1, 6):
                        f = item.font(); f.setBold(True); item.setFont(f)
                    self.cart_table.setItem(row, col, item)

                # Delete Button
                btn_del = QPushButton("🗑️")
                btn_del.setFixedWidth(40)
                btn_del.setStyleSheet("background-color: #FEE2E2; color: #DC2626; border: none; border-radius: 4px;")
                item_id = it.id
                btn_del.clicked.connect(lambda _, i=item_id: self._remove_item(i))
                self.cart_table.setCellWidget(row, 7, btn_del)

            self.lbl_subtotal.setText(format_money(self.current_sale.subtotal))
            self.lbl_big_total.setText(format_money(self.current_sale.total))

        def _remove_item(self, item_id: int):
            sales_service.remove_line(self.session, self.user, self.current_sale, item_id)
            self._refresh_cart()

        def _on_discount_changed(self):
            if not self.current_sale:
                return
            try:
                disc_egp = Decimal(self.disc_edit.text().strip() or "0")
                disc_piasters = egp_to_piasters(disc_egp)
                sales_service.apply_discount(self.session, self.user, self.current_sale, disc_piasters)
                self.lbl_big_total.setText(format_money(self.current_sale.total))
            except Exception:
                pass

        def _on_checkout(self):
            if not self.current_sale or not self.current_sale.items:
                QMessageBox.warning(self, "سلة فارغة", "يرجى إضافة أصناف إلى السلة أولاً")
                return

            cust_name = self.customer_combo.currentText()
            dlg = PaymentDialog(self.current_sale.total, cust_name, parent=self)
            if dlg.exec() == QDialog.Accepted:
                try:
                    sales_service.post_sale(
                        self.session, self.user, self.current_sale, dlg.payments_breakdown
                    )
                    self.session.commit()

                    # Print or preview thermal receipt
                    if dlg.print_receipt:
                        receipt_text = generate_thermal_receipt_text(self.current_sale)
                        QMessageBox.information(self, "تم حفظ الفاتورة بنجاح ✓", f"تم اعتماد الفاتورة #{self.current_sale.invoice_no}\n\n{receipt_text}")
                    else:
                        QMessageBox.information(self, "نجاح", f"تم اعتماد الفاتورة #{self.current_sale.invoice_no} بنجاح ✓")

                    self._new_invoice()
                except Exception as e:
                    self.session.rollback()
                    QMessageBox.critical(self, "خطأ في اعتماد الفاتورة", str(e))

        def _hold_invoice(self):
            if not self.current_sale or not self.current_sale.items:
                return
            self.session.commit()
            QMessageBox.information(self, "تم التعليق", f"تم تعليق الفاتورة #{self.current_sale.invoice_no}")
            self._new_invoice()

        def _resume_held_dialog(self):
            held_sales = sales_service.list_held_sales(self.session)
            if not held_sales:
                QMessageBox.information(self, "معلومة", "لا توجد فواتير معلقة حالياً")
                return
            items = [f"#{s.invoice_no} - {s.customer.name} ({format_money(s.total)})" for s in held_sales]
            chosen, ok = QInputDialog.getItem(self, "استرجاع فاتورة معلقة", "اختر الفاتورة:", items, 0, False)
            if ok and chosen:
                idx = items.index(chosen)
                self.current_sale = held_sales[idx]
                self.lbl_inv_no.setText(f"رقم الفاتورة: {self.current_sale.invoice_no}")
                self._refresh_cart()

        def _clear_cart(self):
            if not self.current_sale or not self.current_sale.items:
                return
            reply = QMessageBox.question(self, "تأكيد", "هل تريد مسح الأصناف الحالية من السلة؟", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self._new_invoice()

        def _open_shift_dialog(self):
            amount, ok = QInputDialog.getDouble(self, "فتح وردية جديدة", "أدخل رصيد العهدة الافتتاحي (كاش الدرج بالجنيه):", 0.0, 0.0, 999999.0, 2)
            if ok:
                try:
                    shift_service.open_shift(self.session, self.user, opening_cash=egp_to_piasters(amount))
                    self.session.commit()
                    QMessageBox.information(self, "تم بنجاح", "تم فتح الوردية بنجاح ✓")
                    self._check_shift_and_init_sale()
                except Exception as e:
                    self.session.rollback()
                    QMessageBox.critical(self, "خطأ", str(e))

        def _add_quick_customer(self):
            name, ok = QInputDialog.getText(self, "إضافة عميل جديد", "اسم العميل:")
            if ok and name.strip():
                phone, ok2 = QInputDialog.getText(self, "إضافة عميل جديد", "رقم الهاتف:")
                try:
                    cust = customer_service.create_customer(self.session, self.user, {"name": name.strip(), "phone": phone.strip()})
                    self.session.commit()
                    self._load_customers()
                    # Select new customer
                    for i in range(self.customer_combo.count()):
                        if self.customer_combo.itemData(i) == cust.id:
                            self.customer_combo.setCurrentIndex(i)
                            break
                except Exception as e:
                    self.session.rollback()
                    QMessageBox.critical(self, "خطأ", str(e))

