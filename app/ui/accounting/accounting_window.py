"""Accounting and cash accounts management screen."""
from __future__ import annotations
from app.i18n import ar

import datetime
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QTabWidget, QComboBox, QMessageBox, QFrame, QScrollArea,
)

from app.core.money import format_money
from app.models.accounting import CashAccount, CashTransaction, Expense, OwnerDraw
from app.services import accounting_service, shift_service
from app.ui.accounting.daily_close_dialog import DailyCloseDialog
from app.ui.accounting.expense_dialog import ExpenseDialog
from app.ui.accounting.owner_draw_dialog import OwnerDrawDialog
from app.ui.accounting.transfer_dialog import TransferDialog
from app.ui.design.style import set_prop, style_label, variant


CATEGORY_AR = {
    "sale": ar.CAT_SALE, "purchase": ar.CAT_PURCHASE, "expense": ar.CAT_EXPENSE, "supplier_payment": ar.CAT_SUPPLIER_PAYMENT,
    "debt_collection": ar.CAT_DEBT_COLLECTION, "owner_draw": ar.CAT_OWNER_DRAW, "transfer": ar.CAT_TRANSFER,
    "repair": ar.CAT_REPAIR, "return": ar.CAT_RETURN, "shift_open": ar.CAT_SHIFT_OPEN,
    "initial_balance": ar.CAT_INITIAL, "shift_diff": ar.CAT_SHIFT_DIFF, "used_device_purchase": ar.CAT_USED_DEVICE, "wallet_cash": ar.CAT_WALLET_CASH,
}


def category_label(category) -> str:
    if not category:
        return "—"
    if category.startswith("wallet_"):
        return ar.CAT_WALLET_CASH
    return CATEGORY_AR.get(category, category)


class AccountingWidget(QWidget):
    def __init__(self, session, user, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self._build_ui()
        self.load_all()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(14)

        # ── Top Bar ─────────────────────────────────────────
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        lbl_head = QLabel(ar.ACCOUNTING_WINDOW_CFA988)
        style_label(lbl_head, size="h2", tone="text", bold=True)
        top_bar.addWidget(lbl_head)
        top_bar.addStretch()

        btn_refresh = QPushButton(ar.REFRESH)
        btn_refresh.setMinimumHeight(40)
        btn_refresh.clicked.connect(self.load_all)
        top_bar.addWidget(btn_refresh)

        btn_daily_close = QPushButton(ar.ACCOUNTING_WINDOW_098A62)
        btn_daily_close.setMinimumHeight(40)
        variant(btn_daily_close, "secondary")
        btn_daily_close.clicked.connect(self._open_daily_close)
        top_bar.addWidget(btn_daily_close)

        btn_transfer = QPushButton(ar.ACCOUNTING_WINDOW_58CDEB)
        btn_transfer.setMinimumHeight(40)
        variant(btn_transfer, "secondary")
        btn_transfer.clicked.connect(self._open_transfer)
        top_bar.addWidget(btn_transfer)

        btn_expense = QPushButton(ar.ACCOUNTING_WINDOW_194506)
        btn_expense.setMinimumHeight(40)
        variant(btn_expense, "danger")
        btn_expense.clicked.connect(self._open_expense)
        top_bar.addWidget(btn_expense)

        btn_draw = QPushButton(ar.ACCOUNTING_WINDOW_401832)
        btn_draw.setMinimumHeight(40)
        variant(btn_draw, "secondary")
        btn_draw.clicked.connect(self._open_owner_draw)
        top_bar.addWidget(btn_draw)

        main_layout.addLayout(top_bar)

        # ── Account Cards ───────────────────────────────────
        self.cards_container = QWidget()
        self.cards_layout = QHBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(12)
        self.cards_layout.setAlignment(Qt.AlignRight)

        scroll_cards = QScrollArea()
        scroll_cards.setWidgetResizable(True)
        scroll_cards.setFixedHeight(115)
        scroll_cards.setFrameShape(QFrame.NoFrame)
        set_prop(scroll_cards, "transparent", True)
        scroll_cards.setWidget(self.cards_container)
        main_layout.addWidget(scroll_cards)

        # ── Tabs ────────────────────────────────────────────
        self.tabs = QTabWidget()


        # Tab 1: Ledger
        self.tab_ledger = QWidget()
        self._setup_ledger_tab()
        self.tabs.addTab(self.tab_ledger, ar.ACCOUNTING_WINDOW_97BD58)

        # Tab 2: Expenses
        self.tab_expenses = QWidget()
        self._setup_expenses_tab()
        self.tabs.addTab(self.tab_expenses, ar.ACCOUNTING_WINDOW_9798B9)

        # Tab 3: Draws & Transfers
        self.tab_draws = QWidget()
        self._setup_draws_tab()
        self.tabs.addTab(self.tab_draws, ar.ACCOUNTING_WINDOW_93FEBE)

        main_layout.addWidget(self.tabs, 1)

    def _setup_ledger_tab(self):
        layout = QVBoxLayout(self.tab_ledger)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        bar = QHBoxLayout()
        self.ledger_filter = QComboBox()
        self.ledger_filter.setMinimumHeight(40)
        self.ledger_filter.addItem(ar.ACCOUNTING_WINDOW_1E7388, "all")
        self.ledger_filter.addItem(ar.ACCOUNTING_WINDOW_308012, "in")
        self.ledger_filter.addItem(ar.ACCOUNTING_WINDOW_2FB65B, "out")
        self.ledger_filter.addItem(ar.ACCOUNTING_WINDOW_BA9922, "transfer")
        self.ledger_filter.currentIndexChanged.connect(self.load_ledger)
        bar.addWidget(self.ledger_filter)
        bar.addStretch()
        layout.addLayout(bar)

        self.ledger_table = QTableWidget()
        self.ledger_table.setColumnCount(8)
        self.ledger_table.setHorizontalHeaderLabels([
            "#", ar.ACCOUNTING_WINDOW_0869F7, ar.ACCOUNTING_WINDOW_BAB7C3, ar.ACCOUNTING_WINDOW_FABA46, ar.ACCOUNTING_WINDOW_CF1432, ar.AUDIT_USER, ar.RECEIPT_DATE, ar.ACCOUNTING_WINDOW_4746F9
        ])
        self.ledger_table.verticalHeader().setVisible(False)
        self.ledger_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.ledger_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.ledger_table.setAlternatingRowColors(True)
        h = self.ledger_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Fixed); self.ledger_table.setColumnWidth(0, 40)
        h.setSectionResizeMode(1, QHeaderView.Fixed); self.ledger_table.setColumnWidth(1, 130)
        h.setSectionResizeMode(2, QHeaderView.Fixed); self.ledger_table.setColumnWidth(2, 100)
        h.setSectionResizeMode(3, QHeaderView.Fixed); self.ledger_table.setColumnWidth(3, 110)
        h.setSectionResizeMode(4, QHeaderView.Fixed); self.ledger_table.setColumnWidth(4, 120)
        h.setSectionResizeMode(5, QHeaderView.Fixed); self.ledger_table.setColumnWidth(5, 110)
        h.setSectionResizeMode(6, QHeaderView.Fixed); self.ledger_table.setColumnWidth(6, 140)
        h.setSectionResizeMode(7, QHeaderView.Stretch)
        layout.addWidget(self.ledger_table)

    def _setup_expenses_tab(self):
        layout = QVBoxLayout(self.tab_expenses)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        self.exp_table = QTableWidget()
        self.exp_table.setColumnCount(7)
        self.exp_table.setHorizontalHeaderLabels([
            "#", ar.ACCOUNTING_WINDOW_61AAAF, ar.ACCOUNTING_WINDOW_FABA46, ar.ACCOUNTING_WINDOW_2027B5, ar.ACCOUNTING_WINDOW_268672, ar.RECEIPT_DATE, ar.IMPORT_COL_NAME
        ])
        self.exp_table.verticalHeader().setVisible(False)
        self.exp_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.exp_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.exp_table.setAlternatingRowColors(True)
        h = self.exp_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Fixed); self.exp_table.setColumnWidth(0, 40)
        h.setSectionResizeMode(1, QHeaderView.Fixed); self.exp_table.setColumnWidth(1, 150)
        h.setSectionResizeMode(2, QHeaderView.Fixed); self.exp_table.setColumnWidth(2, 120)
        h.setSectionResizeMode(3, QHeaderView.Fixed); self.exp_table.setColumnWidth(3, 140)
        h.setSectionResizeMode(4, QHeaderView.Fixed); self.exp_table.setColumnWidth(4, 110)
        h.setSectionResizeMode(5, QHeaderView.Fixed); self.exp_table.setColumnWidth(5, 140)
        h.setSectionResizeMode(6, QHeaderView.Stretch)
        layout.addWidget(self.exp_table)

    def _setup_draws_tab(self):
        layout = QVBoxLayout(self.tab_draws)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        self.draws_table = QTableWidget()
        self.draws_table.setColumnCount(6)
        self.draws_table.setHorizontalHeaderLabels([
            "#", ar.ACCOUNTING_WINDOW_98D124, ar.ACCOUNTING_WINDOW_2027B5, ar.AUDIT_USER, ar.RECEIPT_DATE, ar.ACCOUNTING_WINDOW_4746F9
        ])
        self.draws_table.verticalHeader().setVisible(False)
        self.draws_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.draws_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.draws_table.setAlternatingRowColors(True)
        h = self.draws_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Fixed); self.draws_table.setColumnWidth(0, 40)
        h.setSectionResizeMode(1, QHeaderView.Fixed); self.draws_table.setColumnWidth(1, 130)
        h.setSectionResizeMode(2, QHeaderView.Fixed); self.draws_table.setColumnWidth(2, 140)
        h.setSectionResizeMode(3, QHeaderView.Fixed); self.draws_table.setColumnWidth(3, 120)
        h.setSectionResizeMode(4, QHeaderView.Fixed); self.draws_table.setColumnWidth(4, 140)
        h.setSectionResizeMode(5, QHeaderView.Stretch)
        layout.addWidget(self.draws_table)

    def load_accounts_cards(self):
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        accounts = accounting_service.list_accounts(self.session, self.user)
        icons = {"drawer": "💵", "safe": "🔒", "bank": "🏦", "instapay": "⚡"}

        for acc in accounts:
            matched = accounting_service.verify_drawer_balance_integrity(self.session, acc.id)
            status_text = ar.ACCOUNTING_WINDOW_CB7EFC if matched else ar.ACCOUNTING_WINDOW_63D57D

            card = QFrame()
            card.setFixedWidth(240)
            card.setFixedHeight(100)
            set_prop(card, "card", True)
            c_layout = QVBoxLayout(card)
            c_layout.setContentsMargins(12, 8, 12, 8)
            c_layout.setSpacing(4)

            h_row = QHBoxLayout()
            icon = icons.get(acc.type, "")
            lbl_name = QLabel(f"{icon} {acc.name}")
            style_label(lbl_name, size="body", tone="text", bold=True)
            lbl_status = QLabel(status_text)
            style_label(lbl_status, size="caption")
            h_row.addWidget(lbl_name)
            h_row.addStretch()
            h_row.addWidget(lbl_status)
            c_layout.addLayout(h_row)

            lbl_bal = QLabel(format_money(acc.balance))
            style_label(lbl_bal, size="h2", tone="primary", bold=True)
            c_layout.addWidget(lbl_bal)

            self.cards_layout.addWidget(card)

        self.cards_layout.addStretch()

    def load_ledger(self):
        f = self.ledger_filter.currentData()
        q = self.session.query(CashTransaction)
        if f == "in":
            q = q.filter(CashTransaction.type.in_(["in", "transfer_in"]))
        elif f == "out":
            q = q.filter(CashTransaction.type.in_(["out", "transfer_out"]))
        elif f == "transfer":
            q = q.filter(CashTransaction.type.in_(["transfer_in", "transfer_out"]))

        txs = q.order_by(CashTransaction.created_at.desc()).limit(150).all()
        self.ledger_table.setRowCount(len(txs))

        for idx, t in enumerate(txs):
            self.ledger_table.setItem(idx, 0, QTableWidgetItem(str(t.id)))
            self.ledger_table.setItem(idx, 1, QTableWidgetItem(t.account.name if t.account else "—"))

            type_ar = {
                "in": ar.ACCOUNTING_WINDOW_CAA8CE,
                "out": ar.ACCOUNTING_WINDOW_C863F5,
                "transfer_in": ar.ACCOUNTING_WINDOW_2B8D0C,
                "transfer_out": ar.ACCOUNTING_WINDOW_A04F14,
            }.get(t.type, t.type)
            type_item = QTableWidgetItem(type_ar)
            type_item.setTextAlignment(Qt.AlignCenter)
            if "in" in t.type:
                type_item.setForeground(Qt.green)
            else:
                type_item.setForeground(Qt.red)
            self.ledger_table.setItem(idx, 2, type_item)

            amt_item = QTableWidgetItem(format_money(t.amount))
            amt_item.setTextAlignment(Qt.AlignCenter)
            self.ledger_table.setItem(idx, 3, amt_item)

            self.ledger_table.setItem(idx, 4, QTableWidgetItem(category_label(t.category)))
            self.ledger_table.setItem(idx, 5, QTableWidgetItem(str(t.user_id or "—")))
            self.ledger_table.setItem(idx, 6, QTableWidgetItem(t.created_at.strftime("%Y-%m-%d %H:%M")))
            self.ledger_table.setItem(idx, 7, QTableWidgetItem(t.note or "—"))

    def load_expenses(self):
        exps = self.session.query(Expense).order_by(Expense.created_at.desc()).limit(100).all()
        self.exp_table.setRowCount(len(exps))

        for idx, e in enumerate(exps):
            self.exp_table.setItem(idx, 0, QTableWidgetItem(str(e.id)))
            cat = self.session.get(accounting_service.ExpenseCategory, e.category_id)
            self.exp_table.setItem(idx, 1, QTableWidgetItem(cat.name if cat else "—"))

            amt_item = QTableWidgetItem(format_money(e.amount))
            amt_item.setTextAlignment(Qt.AlignCenter)
            amt_item.setForeground(Qt.red)
            self.exp_table.setItem(idx, 2, amt_item)

            acc = self.session.get(CashAccount, e.account_id)
            self.exp_table.setItem(idx, 3, QTableWidgetItem(acc.name if acc else "—"))
            self.exp_table.setItem(idx, 4, QTableWidgetItem(str(e.user_id or "—")))
            self.exp_table.setItem(idx, 5, QTableWidgetItem(e.created_at.strftime("%Y-%m-%d %H:%M")))
            self.exp_table.setItem(idx, 6, QTableWidgetItem(e.note or "—"))

    def load_draws(self):
        draws = self.session.query(OwnerDraw).order_by(OwnerDraw.created_at.desc()).limit(100).all()
        self.draws_table.setRowCount(len(draws))

        for idx, d in enumerate(draws):
            self.draws_table.setItem(idx, 0, QTableWidgetItem(str(d.id)))

            amt_item = QTableWidgetItem(format_money(d.amount))
            amt_item.setTextAlignment(Qt.AlignCenter)
            amt_item.setForeground(Qt.darkMagenta)
            self.draws_table.setItem(idx, 1, amt_item)

            acc = self.session.get(CashAccount, d.account_id)
            self.draws_table.setItem(idx, 2, QTableWidgetItem(acc.name if acc else "—"))
            self.draws_table.setItem(idx, 3, QTableWidgetItem(str(d.user_id or "—")))
            self.draws_table.setItem(idx, 4, QTableWidgetItem(d.created_at.strftime("%Y-%m-%d %H:%M")))
            self.draws_table.setItem(idx, 5, QTableWidgetItem(d.note or "—"))

    def _open_expense(self):
        dlg = ExpenseDialog(self.session, self.user, parent=self)
        if dlg.exec() == ExpenseDialog.Accepted:
            self.load_all()

    def _open_transfer(self):
        dlg = TransferDialog(self.session, self.user, parent=self)
        if dlg.exec() == TransferDialog.Accepted:
            self.load_all()

    def _open_owner_draw(self):
        dlg = OwnerDrawDialog(self.session, self.user, parent=self)
        if dlg.exec() == OwnerDrawDialog.Accepted:
            self.load_all()

    def _open_daily_close(self):
        dlg = DailyCloseDialog(self.session, self.user, parent=self)
        dlg.exec()

    def load_all(self):
        self.load_accounts_cards()
        self.load_ledger()
        self.load_expenses()
        self.load_draws()

