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
    from PySide6.QtCore import Qt, QTimer, Signal
    from PySide6.QtGui import QColor, QFont, QKeySequence, QShortcut
    HAS_QT = True
except ImportError:
    HAS_QT = False

from app.core.money import format_money, egp_to_piasters, parse_egp_input, piasters_to_input
from app.i18n import ar
from app.models.product import Product
from app.models.stock import Device
from app.models.customer import Customer
from app.services import settings_service, sales_service, shift_service, customer_service, inventory_service
from app.ui.pos.payment_dialog import PaymentDialog
from app.ui.approval_dialog import request_manager_approval
from app.ui.pos.choosers import (
    DeviceChooserDialog, HeldInvoicesDialog, LineEditDialog, ProductChooserDialog,
)
from app.core.permissions import PERM_SALES_BELOW_MIN_PRICE, PERM_SALES_DISCOUNT
from app.services.sales_service import (
    CreditLimitExceededError, DiscountLimitExceededError, InsufficientStockError, PriceBelowMinimumError,
)


HEADERS = ["#", "اسم الصنف", "السيريال (IMEI)", "الكمية", "سعر الوحدة", "الخصم", "الإجمالي", "حذف"]


if HAS_QT:
    class POSWindow(QWidget):
        """Main POS cash register window."""

        shift_changed = Signal()

        def __init__(self, session, user, parent=None):
            super().__init__(parent)
            self.session = session
            self.user = user
            self.current_sale = None
            self._discount_manager = None   # manager who approved the current discount
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

            # Open-shift status row with the close-shift action
            self.shift_bar = QFrame()
            bar_l = QHBoxLayout(self.shift_bar)
            bar_l.setContentsMargins(4, 0, 4, 0)
            self.lbl_shift_status = QLabel("")
            self.lbl_shift_status.setStyleSheet("color: #059669; font-weight: 700;")
            self.btn_close_shift = QPushButton("🔒 " + ar.SHIFT_CLOSE)
            self.btn_close_shift.clicked.connect(self._close_shift_dialog)
            bar_l.addWidget(self.lbl_shift_status)
            bar_l.addStretch()
            bar_l.addWidget(self.btn_close_shift)
            root_layout.addWidget(self.shift_bar)

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

            self.cart_table.doubleClicked.connect(self._edit_selected_line)
            self.cart_table.itemActivated.connect(self._edit_selected_line)
            cart_layout.addWidget(self.cart_table)

            self.undo_bar = QFrame()
            self.undo_bar.setVisible(False)
            ub = QHBoxLayout(self.undo_bar)
            ub.setContentsMargins(8, 4, 8, 4)
            ub.addWidget(QLabel(ar.CART_REMOVED))
            btn_undo = QPushButton(ar.CART_UNDO)
            btn_undo.clicked.connect(self._undo_remove)
            ub.addWidget(btn_undo)
            ub.addStretch()
            cart_layout.addWidget(self.undo_bar)
            self._undo_line = None
            self._undo_timer = QTimer(self)
            self._undo_timer.setSingleShot(True)
            self._undo_timer.timeout.connect(lambda: self.undo_bar.setVisible(False))

            # Quick POS shortcuts toolbar at bottom of cart
            bot_bar = QHBoxLayout()
            bot_bar.setSpacing(10)

            btn_new_inv = QPushButton("📄 فاتورة جديدة [F9]")
            btn_new_inv.clicked.connect(self._new_invoice)
            bot_bar.addWidget(btn_new_inv)

            btn_hold = QPushButton("⏸️ تعليق الفاتورة")
            btn_hold.clicked.connect(self._hold_invoice)
            bot_bar.addWidget(btn_hold)

            self.btn_resume = QPushButton("▶️ المعلّقة")
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
            self.disc_edit.editingFinished.connect(self._on_discount_committed)
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
                self.shift_bar.setVisible(True)
                st = shift_service.shift_status(self.session, self.user)
                self.lbl_shift_status.setText(f"🟢 {ar.SHIFT_OPEN_STATUS} #{st['id']} — {st['opened_at']}")
                self.btn_pay.setEnabled(True)
            else:
                self.shift_banner.setVisible(True)
                self.shift_bar.setVisible(False)
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
                if self.current_sale is not None:
                    sales_service.discard_empty_draft(self.session, self.current_sale)
                self.current_sale = sales_service.start_sale(
                    self.session, self.user, customer_id=cust_id
                )
                self.lbl_inv_no.setText(f"رقم الفاتورة: {self.current_sale.invoice_no}")
                self.disc_edit.setText("0")
                self._discount_manager = None
                self._refresh_cart()
                self._focus_search()
            except Exception as e:
                QMessageBox.critical(self, "خطأ", str(e))

        def _on_scan_or_search(self):
            query = self.scan_edit.text().strip()
            if not query or not self.current_sale:
                return

            # Exact barcode / IMEI first (scanner path: no dialogs for devices).
            found = inventory_service.find_by_barcode_or_imei(self.session, query)
            if found is None:
                prods = inventory_service.search_products(self.session, query)
                if len(prods) == 1:
                    found = prods[0]
                elif prods:
                    dlg = ProductChooserDialog(self.session, query, self)
                    if dlg.exec() != QDialog.Accepted:
                        self._focus_search()
                        return
                    found = dlg.chosen

            if found is None:
                QMessageBox.warning(self, "تنبيه", f"لم يتم العثور على أي صنف أو سيريال يطابق: {query}")
                self._focus_search()
                return

            try:
                if isinstance(found, Device):
                    self._add_to_cart(found.product, device=found)
                elif found.track_imei:
                    in_cart = {it.device_id for it in self.current_sale.items if it.device_id}
                    dlg = DeviceChooserDialog(self.session, found, exclude_ids=in_cart, parent=self)
                    if dlg.device_count == 0:
                        QMessageBox.warning(self, "تنبيه", f"لا توجد أجهزة متوفرة في المخزن للصنف '{found.name}'")
                    elif dlg.exec() == QDialog.Accepted and dlg.chosen:
                        self._add_to_cart(found, device=dlg.chosen)
                else:
                    self._add_to_cart(found)
                self.scan_edit.clear()
                self._refresh_cart()
            except Exception as e:
                QMessageBox.critical(self, "خطأ في إضافة الصنف", str(e))

            self._focus_search()

        def _add_to_cart(self, product, device=None):
            """Add one unit; an accessory already in the cart gets its quantity bumped."""
            if device is None:
                for it in self.current_sale.items:
                    if it.product_id == product.id and not it.device_id and it.discount == 0:
                        sales_service.update_line(
                            self.session, self.user, self.current_sale, it.id, quantity=it.quantity + 1
                        )
                        return
            if device is not None and any(it.device_id == device.id for it in self.current_sale.items):
                raise sales_service.SaleError("هذا الجهاز مضاف بالفعل في الفاتورة")
            sales_service.add_line(
                self.session, self.user, self.current_sale, product, quantity=1, device=device
            )

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
                btn_del.setToolTip("حذف البند")
                self.cart_table.setCellWidget(row, 7, btn_del)

            self.lbl_subtotal.setText(format_money(self.current_sale.subtotal))
            self.lbl_big_total.setText(format_money(self.current_sale.total))
            self._refresh_held_badge()

        def _refresh_held_badge(self):
            n = len(sales_service.list_held_sales(self.session))
            # The invoice being edited is itself "held" in the DB; show only the others.
            if self.current_sale is not None and self.current_sale.status == "held":
                n = max(0, n - 1)
            self.btn_resume.setText(f"▶️ المعلّقة ({n})" if n else "▶️ المعلّقة")

        def _remove_item(self, item_id: int):
            item = next((i for i in self.current_sale.items if i.id == item_id), None)
            if item is not None:
                self._undo_line = {
                    "product": item.product, "device": item.device, "quantity": item.quantity,
                    "unit_price": item.unit_price, "discount": item.discount,
                }
            sales_service.remove_line(self.session, self.user, self.current_sale, item_id)
            self._refresh_cart()
            if item is not None:
                self.undo_bar.setVisible(True)
                self._undo_timer.start(8000)

        def _undo_remove(self):
            data = getattr(self, "_undo_line", None)
            self.undo_bar.setVisible(False)
            if not data or not self.current_sale:
                return
            try:
                sales_service.add_line(
                    self.session, self.user, self.current_sale, data["product"],
                    quantity=data["quantity"], unit_price=data["unit_price"],
                    device=data["device"], discount=data["discount"],
                )
            except Exception as exc:
                QMessageBox.warning(self, ar.ERROR, str(exc))
            self._undo_line = None
            self._refresh_cart()

        def _edit_selected_line(self, *_):
            row = self.cart_table.currentRow()
            if not self.current_sale or not (0 <= row < len(self.current_sale.items)):
                return
            item = self.current_sale.items[row]
            dlg = LineEditDialog(item, can_set_qty=not item.device_id, parent=self)
            if dlg.exec() != QDialog.Accepted or not dlg.values:
                return
            v = dlg.values
            manager = None
            while True:
                try:
                    sales_service.update_line(
                        self.session, self.user, self.current_sale, item.id,
                        quantity=v["quantity"] if not item.device_id else None,
                        unit_price=v["unit_price"], discount=v["discount"], manager_override=manager,
                    )
                    break
                except DiscountLimitExceededError as exc:
                    if manager is not None:
                        QMessageBox.warning(self, ar.ERROR, str(exc))
                        return
                    manager = request_manager_approval(
                        self, self.session, self.user, PERM_SALES_DISCOUNT, str(exc)
                    )
                    if manager is None:
                        return
                except (ValueError, sales_service.SaleError) as exc:
                    QMessageBox.warning(self, ar.ERROR, str(exc))
                    return
            self._refresh_cart()
            self._focus_search()

        def _apply_discount_text(self, manager=None) -> None:
            disc_piasters = parse_egp_input(self.disc_edit.text() or "0")
            sales_service.apply_discount(
                self.session, self.user, self.current_sale, disc_piasters, manager_override=manager
            )
            self.lbl_big_total.setText(format_money(self.current_sale.total))

        def _on_discount_changed(self):
            """Live preview while typing; limits needing approval are handled on commit."""
            if not self.current_sale:
                return
            try:
                self._apply_discount_text(self._discount_manager)
            except DiscountLimitExceededError:
                self.disc_edit.setToolTip(ar.APPROVAL_DISCOUNT_HINT)
            except (ValueError, sales_service.SaleError):
                pass

        def _on_discount_committed(self):
            """Enter / focus-out: ask a manager if the cashier's discount limit was exceeded."""
            if not self.current_sale:
                return
            try:
                self._apply_discount_text(self._discount_manager)
            except DiscountLimitExceededError as exc:
                manager = request_manager_approval(
                    self, self.session, self.user, PERM_SALES_DISCOUNT, str(exc)
                )
                if manager is None:
                    self.disc_edit.setText(piasters_to_input(self.current_sale.discount))
                    return
                self._discount_manager = manager
                self._apply_discount_text(manager)
            except (ValueError, sales_service.SaleError):
                self.disc_edit.setText(piasters_to_input(self.current_sale.discount))

        def _on_checkout(self):
            if not self.current_sale or not self.current_sale.items:
                QMessageBox.warning(self, "سلة فارغة", "يرجى إضافة أصناف إلى السلة أولاً")
                return

            cust_name = self.customer_combo.currentText()
            dlg = PaymentDialog(self.current_sale.total, cust_name, parent=self)
            if dlg.exec() != QDialog.Accepted:
                return
            manager = self._discount_manager
            while True:
                try:
                    sales_service.post_sale(
                        self.session, self.user, self.current_sale, dlg.payments_breakdown,
                        manager_override=manager,
                    )
                    self.session.commit()
                    break
                except (PriceBelowMinimumError, CreditLimitExceededError, InsufficientStockError) as exc:
                    # Needs a manager: ask once, then retry the same sale with their approval.
                    if manager is not None:
                        QMessageBox.critical(self, "خطأ في اعتماد الفاتورة", str(exc))
                        return
                    manager = request_manager_approval(
                        self, self.session, self.user, PERM_SALES_BELOW_MIN_PRICE, str(exc)
                    )
                    if manager is None:
                        return
                except Exception as exc:
                    self.session.rollback()
                    QMessageBox.critical(self, "خطأ في اعتماد الفاتورة", str(exc))
                    return

            if dlg.print_receipt:
                from app.ui.print_dialogs import SaleCompleteDialog
                SaleCompleteDialog(self.session, self.current_sale, self).exec()
            else:
                QMessageBox.information(self, ar.SUCCESS, f"{ar.SALE_DONE_TITLE} #{self.current_sale.invoice_no}")
            self._new_invoice()

        def _hold_invoice(self):
            if not self.current_sale or not self.current_sale.items:
                return
            self.session.commit()
            QMessageBox.information(self, "تم التعليق", f"تم تعليق الفاتورة #{self.current_sale.invoice_no}")
            self._new_invoice()

        def _resume_held_dialog(self):
            dlg = HeldInvoicesDialog(self.session, self.user, self)
            if dlg.exec() != QDialog.Accepted or dlg.chosen is None:
                self._refresh_held_badge()
                return
            if self.current_sale is not None and self.current_sale is not dlg.chosen:
                if self.current_sale.items:
                    self.session.commit()   # current invoice stays held in the list
                else:
                    sales_service.discard_empty_draft(self.session, self.current_sale)
            self.current_sale = dlg.chosen
            self.lbl_inv_no.setText(f"رقم الفاتورة: {self.current_sale.invoice_no}")
            self.disc_edit.setText(piasters_to_input(self.current_sale.discount))
            self._refresh_cart()
            self._focus_search()

        def _clear_cart(self):
            if not self.current_sale or not self.current_sale.items:
                return
            reply = QMessageBox.question(self, "تأكيد", "هل تريد مسح الأصناف الحالية من السلة؟", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                for it in list(self.current_sale.items):
                    sales_service.remove_line(self.session, self.user, self.current_sale, it.id)
                self.session.expire(self.current_sale, ["items"])
                self._new_invoice()

        def _close_shift_dialog(self):
            from app.ui.shift_dialog import CloseShiftDialog

            shift = shift_service.get_active_shift(self.session, self.user.id)
            if shift is None:
                self._check_shift_and_init_sale()
                return
            if self.current_sale and self.current_sale.items:
                QMessageBox.warning(self, ar.WARNING, "أكمل الفاتورة الحالية أو علّقها قبل إغلاق الوردية")
                return
            dlg = CloseShiftDialog(self.session, self.user, shift, parent=self)
            dlg.exec()
            if dlg.closed:
                self._check_shift_and_init_sale()
                self.shift_changed.emit()

        def _open_shift_dialog(self):
            amount, ok = QInputDialog.getDouble(self, "فتح وردية جديدة", "أدخل رصيد العهدة الافتتاحي (كاش الدرج بالجنيه):", 0.0, 0.0, 999999.0, 2)
            if ok:
                try:
                    shift_service.open_shift(self.session, self.user, opening_cash=egp_to_piasters(amount))
                    self.session.commit()
                    QMessageBox.information(self, "تم بنجاح", "تم فتح الوردية بنجاح ✓")
                    self._check_shift_and_init_sale()
                    self.shift_changed.emit()
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

