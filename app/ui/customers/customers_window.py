"""Customers and receivables management view."""
from __future__ import annotations

from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QFrame,
)

from app.core.money import format_money
from app.models.customer import Customer
from app.services import customer_service
from app.ui.customers.collect_payment_dialog import CollectPaymentDialog
from app.ui.customers.customer_dialog import CustomerDialog


class CustomersWidget(QWidget):
    def __init__(self, session, user, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self._all_customers: list[Customer] = []
        self._build_ui()
        self.load_customers()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(14)

        # ── Top Bar ─────────────────────────────────────────
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        lbl_head = QLabel("👥 إدارة العملاء وحسابات الآجل والديون")
        lbl_head.setStyleSheet("font-size: 18px; font-weight: bold; color: #0F172A;")
        top_bar.addWidget(lbl_head)
        top_bar.addStretch()

        self.search_edit = QLineEdit()
        self.search_edit.setFixedHeight(38)
        self.search_edit.setMinimumWidth(260)
        self.search_edit.setPlaceholderText("🔍 بحث باسم العميل أو رقم الهاتف...")
        self.search_edit.textChanged.connect(self._filter_customers)
        top_bar.addWidget(self.search_edit)

        btn_refresh = QPushButton("🔄 تحديث")
        btn_refresh.setFixedHeight(38)
        btn_refresh.clicked.connect(self.load_customers)
        top_bar.addWidget(btn_refresh)

        btn_add = QPushButton("➕ إضافة عميل جديد")
        btn_add.setFixedHeight(38)
        btn_add.setStyleSheet("background-color: #2563EB; color: white; border-radius: 6px; font-weight: bold; padding: 0 16px;")
        btn_add.clicked.connect(self._open_new_customer)
        top_bar.addWidget(btn_add)

        main_layout.addLayout(top_bar)

        # ── KPI Cards ───────────────────────────────────────
        kpi_bar = QHBoxLayout()
        kpi_bar.setSpacing(12)

        # Card 1: Total Receivables
        self.card_receivables = self._create_kpi_card("إجمالي ديون العملاء (الآجل):", "0.00 ج.م", "#DC2626")
        kpi_bar.addWidget(self.card_receivables)

        # Card 2: Customers Count
        self.card_count = self._create_kpi_card("إجمالي عدد العملاء المسجلين:", "0 عميل", "#2563EB")
        kpi_bar.addWidget(self.card_count)

        kpi_bar.addStretch()
        main_layout.addLayout(kpi_bar)

        # ── Customers Table ─────────────────────────────────
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "#", "اسم العميل", "رقم الهاتف", "المديونية الحالية", "حد الائتمان", "ملاحظات", "إجراءات"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Fixed); self.table.setColumnWidth(0, 40)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.Fixed); self.table.setColumnWidth(2, 130)
        h.setSectionResizeMode(3, QHeaderView.Fixed); self.table.setColumnWidth(3, 140)
        h.setSectionResizeMode(4, QHeaderView.Fixed); self.table.setColumnWidth(4, 130)
        h.setSectionResizeMode(5, QHeaderView.Stretch)
        h.setSectionResizeMode(6, QHeaderView.Fixed); self.table.setColumnWidth(6, 170)
        main_layout.addWidget(self.table, 1)

    def _create_kpi_card(self, title: str, init_val: str, color: str) -> QFrame:
        card = QFrame()
        card.setFixedWidth(240)
        card.setFixedHeight(75)
        card.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; padding: 8px 12px;")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        lbl_t = QLabel(title)
        lbl_t.setStyleSheet("font-size: 11px; color: #64748B; font-weight: bold;")
        layout.addWidget(lbl_t)

        lbl_v = QLabel(init_val)
        lbl_v.setObjectName("Val")
        lbl_v.setStyleSheet(f"font-size: 17px; font-weight: bold; color: {color};")
        layout.addWidget(lbl_v)
        return card

    def load_customers(self):
        customers = self.session.query(Customer).order_by(Customer.balance.desc(), Customer.name.asc()).all()
        self._all_customers = customers
        self._render_customers(customers)

        # Update KPIs
        total_rec = sum(c.balance for c in customers if c.balance > 0)
        self.card_receivables.findChild(QLabel, "Val").setText(format_money(total_rec))
        self.card_count.findChild(QLabel, "Val").setText(f"{len(customers)} عميل")

    def _filter_customers(self):
        q = self.search_edit.text().strip().lower()
        if not q:
            self._render_customers(self._all_customers)
            return
        filtered = [
            c for c in self._all_customers
            if q in c.name.lower() or (c.phone and q in c.phone)
        ]
        self._render_customers(filtered)

    def _render_customers(self, customers: list[Customer]):
        self.table.setRowCount(len(customers))
        for idx, c in enumerate(customers):
            self.table.setItem(idx, 0, QTableWidgetItem(str(c.id)))
            self.table.setItem(idx, 1, QTableWidgetItem(c.name))
            self.table.setItem(idx, 2, QTableWidgetItem(c.phone or "—"))

            bal_item = QTableWidgetItem(format_money(c.balance))
            bal_item.setTextAlignment(Qt.AlignCenter)
            if c.balance > 0:
                bal_item.setForeground(Qt.red)
            else:
                bal_item.setForeground(Qt.green)
            self.table.setItem(idx, 3, bal_item)

            limit_item = QTableWidgetItem(format_money(c.credit_limit) if c.credit_limit else "بلا حد")
            limit_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(idx, 4, limit_item)

            self.table.setItem(idx, 5, QTableWidgetItem(c.notes or "—"))

            # Actions Box
            actions_box = QWidget()
            a_layout = QHBoxLayout(actions_box)
            a_layout.setContentsMargins(4, 2, 4, 2)
            a_layout.setSpacing(6)

            btn_collect = QPushButton("💵 تحصيل")
            btn_collect.setStyleSheet("background-color: #DCFCE7; color: #15803D; border: 1px solid #86EFAC; border-radius: 4px; font-weight: bold; font-size: 11px;")
            btn_collect.clicked.connect(lambda _, cust=c: self._open_collect(cust))
            a_layout.addWidget(btn_collect)

            btn_edit = QPushButton("✏️ تعديل")
            btn_edit.setStyleSheet("background-color: #F1F5F9; color: #475569; border: 1px solid #CBD5E1; border-radius: 4px; font-weight: bold; font-size: 11px;")
            btn_edit.clicked.connect(lambda _, cust=c: self._open_edit(cust))
            a_layout.addWidget(btn_edit)

            self.table.setCellWidget(idx, 6, actions_box)

    def _open_new_customer(self):
        dlg = CustomerDialog(self.session, self.user, parent=self)
        if dlg.exec() == CustomerDialog.Accepted:
            self.load_customers()

    def _open_edit(self, customer: Customer):
        dlg = CustomerDialog(self.session, self.user, customer=customer, parent=self)
        if dlg.exec() == CustomerDialog.Accepted:
            self.load_customers()

    def _open_collect(self, customer: Customer):
        if customer.balance <= 0:
            QMessageBox.information(self, "تنبيه", "هذا العميل ليس عليه أي مديونية مستحقة حالياً.")
            return
        dlg = CollectPaymentDialog(self.session, self.user, customer=customer, parent=self)
        if dlg.exec() == CollectPaymentDialog.Accepted:
            self.load_customers()

