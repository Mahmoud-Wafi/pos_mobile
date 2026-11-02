"""Purchases and Suppliers management screen (Tab 1: Invoices, Tab 2: Used Phones, Tab 3: Suppliers)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QTabWidget, QMessageBox, QFrame,
)

from app.core.money import format_money
from app.models.purchase import Purchase, Supplier, UsedDevicePurchase
from app.services import purchase_service
from app.ui.purchases.purchase_invoice_dialog import PurchaseInvoiceDialog
from app.ui.purchases.supplier_dialog import SupplierDialog
from app.ui.purchases.supplier_payment_dialog import SupplierPaymentDialog
from app.ui.purchases.used_device_dialog import UsedDeviceDialog


class PurchasesWidget(QWidget):
    def __init__(self, session, user, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self._build_ui()
        self.load_all()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #E2E8F0;
                background-color: #FFFFFF;
                border-radius: 8px;
                padding: 12px;
            }
            QTabBar::tab {
                background: #F1F5F9;
                color: #475569;
                font-weight: bold;
                font-size: 13px;
                padding: 10px 20px;
                margin-left: 4px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
            QTabBar::tab:selected {
                background: #2563EB;
                color: white;
            }
        """)

        # ── Tab 1: فواتير المشتريات ─────────────────────────
        self.tab_invoices = QWidget()
        self._setup_invoices_tab()
        self.tabs.addTab(self.tab_invoices, "📦 فواتير المشتريات")

        # ── Tab 2: الأجهزة المستعملة ────────────────────────
        self.tab_used = QWidget()
        self._setup_used_tab()
        self.tabs.addTab(self.tab_used, "📱 الأجهزة المستعملة والإقرارات")

        # ── Tab 3: الموردين والمدفوعات ───────────────────────
        self.tab_suppliers = QWidget()
        self._setup_suppliers_tab()
        self.tabs.addTab(self.tab_suppliers, "🏢 الموردين والحسابات")

        main_layout.addWidget(self.tabs)

    # ── Tab 1 Implementation ──────────────────────────────────────────

    def _setup_invoices_tab(self):
        layout = QVBoxLayout(self.tab_invoices)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        # Bar
        bar = QHBoxLayout()
        self.inv_search_edit = QLineEdit()
        self.inv_search_edit.setFixedHeight(38)
        self.inv_search_edit.setPlaceholderText("🔍 بحث برقم الفاتورة أو اسم المورد...")
        self.inv_search_edit.textChanged.connect(self._filter_invoices)
        bar.addWidget(self.inv_search_edit, 1)

        btn_refresh = QPushButton("🔄 تحديث")
        btn_refresh.setFixedHeight(38)
        btn_refresh.clicked.connect(self.load_invoices)
        bar.addWidget(btn_refresh)

        btn_new_inv = QPushButton("➕ فاتورة شراء جديدة")
        btn_new_inv.setFixedHeight(38)
        btn_new_inv.setStyleSheet("background-color: #2563EB; color: white; border-radius: 6px; font-weight: bold; padding: 0 16px;")
        btn_new_inv.clicked.connect(self._open_new_invoice_dialog)
        bar.addWidget(btn_new_inv)
        layout.addLayout(bar)

        # Invoices Table
        self.inv_table = QTableWidget()
        self.inv_table.setColumnCount(8)
        self.inv_table.setHorizontalHeaderLabels([
            "#", "رقم الفاتورة", "المورد", "التاريخ", "إجمالي الفاتورة", "المدفوع", "المتبقي (آجل)", "الحالة"
        ])
        self.inv_table.verticalHeader().setVisible(False)
        self.inv_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.inv_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.inv_table.setAlternatingRowColors(True)
        h = self.inv_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Fixed); self.inv_table.setColumnWidth(0, 40)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        h.setSectionResizeMode(3, QHeaderView.Fixed); self.inv_table.setColumnWidth(3, 140)
        h.setSectionResizeMode(4, QHeaderView.Fixed); self.inv_table.setColumnWidth(4, 110)
        h.setSectionResizeMode(5, QHeaderView.Fixed); self.inv_table.setColumnWidth(5, 110)
        h.setSectionResizeMode(6, QHeaderView.Fixed); self.inv_table.setColumnWidth(6, 110)
        h.setSectionResizeMode(7, QHeaderView.Fixed); self.inv_table.setColumnWidth(7, 80)
        layout.addWidget(self.inv_table)

    def _open_new_invoice_dialog(self):
        dlg = PurchaseInvoiceDialog(self.session, self.user, parent=self)
        if dlg.exec() == PurchaseInvoiceDialog.Accepted:
            self.load_all()

    def load_invoices(self):
        invoices = purchase_service.list_purchases(self.session, self.user)
        self._all_invoices = invoices
        self._render_invoices(invoices)

    def _filter_invoices(self):
        q = self.inv_search_edit.text().strip().lower()
        if not hasattr(self, "_all_invoices"):
            return
        if not q:
            self._render_invoices(self._all_invoices)
            return
        filtered = [
            inv for inv in self._all_invoices
            if q in inv.invoice_number.lower() or (inv.supplier and q in inv.supplier.name.lower())
        ]
        self._render_invoices(filtered)

    def _render_invoices(self, invoices: list[Purchase]):
        self.inv_table.setRowCount(len(invoices))
        for idx, inv in enumerate(invoices):
            self.inv_table.setItem(idx, 0, QTableWidgetItem(str(inv.id)))
            self.inv_table.setItem(idx, 1, QTableWidgetItem(inv.invoice_number))
            self.inv_table.setItem(idx, 2, QTableWidgetItem(inv.supplier.name if inv.supplier else "—"))
            self.inv_table.setItem(idx, 3, QTableWidgetItem(inv.created_at.strftime("%Y-%m-%d %H:%M")))

            tot_item = QTableWidgetItem(format_money(inv.total))
            tot_item.setTextAlignment(Qt.AlignCenter)
            self.inv_table.setItem(idx, 4, tot_item)

            paid_item = QTableWidgetItem(format_money(inv.paid))
            paid_item.setTextAlignment(Qt.AlignCenter)
            self.inv_table.setItem(idx, 5, paid_item)

            rem_item = QTableWidgetItem(format_money(inv.balance))
            rem_item.setTextAlignment(Qt.AlignCenter)
            if inv.balance > 0:
                rem_item.setForeground(Qt.red)
            self.inv_table.setItem(idx, 6, rem_item)

            st_item = QTableWidgetItem("مرحلة" if inv.status == "posted" else inv.status)
            st_item.setTextAlignment(Qt.AlignCenter)
            self.inv_table.setItem(idx, 7, st_item)

    # ── Tab 2 Implementation (Used Devices) ───────────────────────────

    def _setup_used_tab(self):
        layout = QVBoxLayout(self.tab_used)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        bar = QHBoxLayout()
        self.used_search_edit = QLineEdit()
        self.used_search_edit.setFixedHeight(38)
        self.used_search_edit.setPlaceholderText("🔍 بحث باسم البائع، الرقم القومي، أو الهاتف...")
        self.used_search_edit.textChanged.connect(self._filter_used)
        bar.addWidget(self.used_search_edit, 1)

        btn_refresh = QPushButton("🔄 تحديث")
        btn_refresh.setFixedHeight(38)
        btn_refresh.clicked.connect(self.load_used_purchases)
        bar.addWidget(btn_refresh)

        btn_new_used = QPushButton("📱 شراء جهاز مستعمل جديد")
        btn_new_used.setFixedHeight(38)
        btn_new_used.setStyleSheet("background-color: #16A34A; color: white; border-radius: 6px; font-weight: bold; padding: 0 16px;")
        btn_new_used.clicked.connect(self._open_new_used_dialog)
        bar.addWidget(btn_new_used)
        layout.addLayout(bar)

        # Used Table
        self.used_table = QTableWidget()
        self.used_table.setColumnCount(8)
        self.used_table.setHorizontalHeaderLabels([
            "#", "اسم البائع", "الرقم القومي", "الهاتف", "الجهاز / الموديل", "سيريال IMEI", "السعر", "إقرار التنازل"
        ])
        self.used_table.verticalHeader().setVisible(False)
        self.used_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.used_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.used_table.setAlternatingRowColors(True)
        h = self.used_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Fixed); self.used_table.setColumnWidth(0, 40)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.Fixed); self.used_table.setColumnWidth(2, 130)
        h.setSectionResizeMode(3, QHeaderView.Fixed); self.used_table.setColumnWidth(3, 110)
        h.setSectionResizeMode(4, QHeaderView.Stretch)
        h.setSectionResizeMode(5, QHeaderView.Fixed); self.used_table.setColumnWidth(5, 140)
        h.setSectionResizeMode(6, QHeaderView.Fixed); self.used_table.setColumnWidth(6, 110)
        h.setSectionResizeMode(7, QHeaderView.Fixed); self.used_table.setColumnWidth(7, 100)
        layout.addWidget(self.used_table)

    def _open_new_used_dialog(self):
        dlg = UsedDeviceDialog(self.session, self.user, parent=self)
        if dlg.exec() == UsedDeviceDialog.Accepted:
            self.load_all()

    def load_used_purchases(self):
        used_list = purchase_service.list_used_purchases(self.session, self.user)
        self._all_used = used_list
        self._render_used(used_list)

    def _filter_used(self):
        q = self.used_search_edit.text().strip().lower()
        if not hasattr(self, "_all_used"):
            return
        if not q:
            self._render_used(self._all_used)
            return
        filtered = [
            u for u in self._all_used
            if q in u.seller_name.lower() or q in u.seller_national_id or q in u.seller_phone
        ]
        self._render_used(filtered)

    def _render_used(self, used_list: list[UsedDevicePurchase]):
        self.used_table.setRowCount(len(used_list))
        for idx, u in enumerate(used_list):
            self.used_table.setItem(idx, 0, QTableWidgetItem(str(u.id)))
            self.used_table.setItem(idx, 1, QTableWidgetItem(u.seller_name))
            self.used_table.setItem(idx, 2, QTableWidgetItem(u.seller_national_id))
            self.used_table.setItem(idx, 3, QTableWidgetItem(u.seller_phone))

            dev_name = u.device.product.name if u.device and u.device.product else "هاتف"
            self.used_table.setItem(idx, 4, QTableWidgetItem(dev_name))

            imei_str = u.device.imei1 if u.device else "—"
            self.used_table.setItem(idx, 5, QTableWidgetItem(imei_str))

            price_item = QTableWidgetItem(format_money(u.price))
            price_item.setTextAlignment(Qt.AlignCenter)
            self.used_table.setItem(idx, 6, price_item)

            btn_print = QPushButton("🖨️ طباعة")
            btn_print.setStyleSheet("background-color: #EFF6FF; color: #2563EB; border: 1px solid #BFDBFE; border-radius: 4px; font-weight: bold;")
            btn_print.clicked.connect(lambda _, rec_id=u.id: self._print_declaration(rec_id))
            self.used_table.setCellWidget(idx, 7, btn_print)

    def _print_declaration(self, used_purchase_id: int):
        try:
            pdf_path = purchase_service.generate_declaration(
                self.session, self.user, used_purchase_id
            )
            self.session.commit()
            if sys.platform.startswith("linux"):
                subprocess.Popen(["xdg-open", str(pdf_path)])
            elif sys.platform.startswith("win"):
                os.startfile(str(pdf_path))
            elif sys.platform.startswith("darwin"):
                subprocess.Popen(["open", str(pdf_path)])
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"تعذر فتح أو طباعة الإقرار:\n{str(e)}")

    # ── Tab 3 Implementation (Suppliers) ──────────────────────────────

    def _setup_suppliers_tab(self):
        layout = QVBoxLayout(self.tab_suppliers)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        bar = QHBoxLayout()
        self.sup_search_edit = QLineEdit()
        self.sup_search_edit.setFixedHeight(38)
        self.sup_search_edit.setPlaceholderText("🔍 بحث باسم المورد أو رقم الهاتف...")
        self.sup_search_edit.textChanged.connect(self._filter_suppliers)
        bar.addWidget(self.sup_search_edit, 1)

        btn_refresh = QPushButton("🔄 تحديث")
        btn_refresh.setFixedHeight(38)
        btn_refresh.clicked.connect(self.load_suppliers)
        bar.addWidget(btn_refresh)

        btn_new_sup = QPushButton("➕ إضافة مورد جديد")
        btn_new_sup.setFixedHeight(38)
        btn_new_sup.setStyleSheet("background-color: #2563EB; color: white; border-radius: 6px; font-weight: bold; padding: 0 16px;")
        btn_new_sup.clicked.connect(self._open_new_supplier_dialog)
        bar.addWidget(btn_new_sup)
        layout.addLayout(bar)

        # Suppliers Table
        self.sup_table = QTableWidget()
        self.sup_table.setColumnCount(6)
        self.sup_table.setHorizontalHeaderLabels([
            "#", "اسم المورد / الشركة", "الهاتف", "الرصيد المستحق للمورد", "ملاحظات", "سداد دفعة"
        ])
        self.sup_table.verticalHeader().setVisible(False)
        self.sup_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.sup_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.sup_table.setAlternatingRowColors(True)
        h = self.sup_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Fixed); self.sup_table.setColumnWidth(0, 40)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.Fixed); self.sup_table.setColumnWidth(2, 130)
        h.setSectionResizeMode(3, QHeaderView.Fixed); self.sup_table.setColumnWidth(3, 140)
        h.setSectionResizeMode(4, QHeaderView.Stretch)
        h.setSectionResizeMode(5, QHeaderView.Fixed); self.sup_table.setColumnWidth(5, 110)
        layout.addWidget(self.sup_table)

    def _open_new_supplier_dialog(self):
        dlg = SupplierDialog(self.session, self.user, parent=self)
        if dlg.exec() == SupplierDialog.Accepted:
            self.load_suppliers()

    def load_suppliers(self):
        suppliers = purchase_service.list_suppliers(self.session, self.user)
        self._all_suppliers = suppliers
        self._render_suppliers(suppliers)

    def _filter_suppliers(self):
        q = self.sup_search_edit.text().strip().lower()
        if not hasattr(self, "_all_suppliers"):
            return
        if not q:
            self._render_suppliers(self._all_suppliers)
            return
        filtered = [
            s for s in self._all_suppliers
            if q in s.name.lower() or (s.phone and q in s.phone)
        ]
        self._render_suppliers(filtered)

    def _render_suppliers(self, suppliers: list[Supplier]):
        self.sup_table.setRowCount(len(suppliers))
        for idx, s in enumerate(suppliers):
            self.sup_table.setItem(idx, 0, QTableWidgetItem(str(s.id)))
            self.sup_table.setItem(idx, 1, QTableWidgetItem(s.name))
            self.sup_table.setItem(idx, 2, QTableWidgetItem(s.phone or "—"))

            bal_item = QTableWidgetItem(format_money(s.balance))
            bal_item.setTextAlignment(Qt.AlignCenter)
            if s.balance > 0:
                bal_item.setForeground(Qt.red)
            else:
                bal_item.setForeground(Qt.green)
            self.sup_table.setItem(idx, 3, bal_item)

            self.sup_table.setItem(idx, 4, QTableWidgetItem(s.notes or "—"))

            btn_pay = QPushButton("💳 سداد دفعة")
            btn_pay.setStyleSheet("background-color: #FEF3C7; color: #B45309; border: 1px solid #F59E0B; border-radius: 4px; font-weight: bold;")
            btn_pay.clicked.connect(lambda _, sup=s: self._pay_supplier_dialog(sup))
            self.sup_table.setCellWidget(idx, 5, btn_pay)

    def _pay_supplier_dialog(self, supplier: Supplier):
        dlg = SupplierPaymentDialog(self.session, self.user, supplier=supplier, parent=self)
        if dlg.exec() == SupplierPaymentDialog.Accepted:
            self.load_all()

    def load_all(self):
        self.load_invoices()
        self.load_used_purchases()
        self.load_suppliers()

