"""Electronic Wallets management and instant operations screen."""
from __future__ import annotations

import datetime
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QDoubleValidator
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QMessageBox, QFrame, QGridLayout, QScrollArea,
)

from app.core.money import egp_to_piasters, format_money, piasters_to_egp
from app.models.wallet import Wallet, WalletTransaction
from app.services import wallet_service
from app.ui.wallets.commission_rules_dialog import CommissionRulesDialog
from app.ui.wallets.wallet_audit_dialog import WalletAuditDialog
from app.ui.wallets.wallet_dialog import WalletDialog


class WalletsWidget(QWidget):
    def __init__(self, session, user, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self.current_op_type = "cash_in"
        self._build_ui()
        self.load_all()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(14)

        # ── Top Control & Action Bar ────────────────────────
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        lbl_head = QLabel("💳 إدارة المحافظ الإلكترونية وشبكات الدفع الفوري")
        lbl_head.setStyleSheet("font-size: 18px; font-weight: bold; color: #0F172A;")
        top_bar.addWidget(lbl_head)
        top_bar.addStretch()

        btn_refresh = QPushButton("🔄 تحديث")
        btn_refresh.setFixedHeight(38)
        btn_refresh.clicked.connect(self.load_all)
        top_bar.addWidget(btn_refresh)

        btn_rules = QPushButton("⚙️ قواعد العمولات")
        btn_rules.setFixedHeight(38)
        btn_rules.setStyleSheet("background-color: #EFF6FF; color: #2563EB; border: 1px solid #BFDBFE; border-radius: 6px; font-weight: bold; padding: 0 14px;")
        btn_rules.clicked.connect(self._open_rules_dialog)
        top_bar.addWidget(btn_rules)

        btn_audit = QPushButton("⚖️ جرد المحافظ")
        btn_audit.setFixedHeight(38)
        btn_audit.setStyleSheet("background-color: #FEF3C7; color: #B45309; border: 1px solid #F59E0B; border-radius: 6px; font-weight: bold; padding: 0 14px;")
        btn_audit.clicked.connect(self._open_audit_dialog)
        top_bar.addWidget(btn_audit)

        btn_new_wallet = QPushButton("➕ إضافة خط محفظة")
        btn_new_wallet.setFixedHeight(38)
        btn_new_wallet.setStyleSheet("background-color: #2563EB; color: white; border-radius: 6px; font-weight: bold; padding: 0 16px;")
        btn_new_wallet.clicked.connect(self._open_new_wallet_dialog)
        top_bar.addWidget(btn_new_wallet)

        main_layout.addLayout(top_bar)

        # ── Wallet Cards Scroll Area ────────────────────────
        self.cards_container = QWidget()
        self.cards_layout = QHBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(12)
        self.cards_layout.setAlignment(Qt.AlignRight)

        scroll_cards = QScrollArea()
        scroll_cards.setWidgetResizable(True)
        scroll_cards.setFixedHeight(125)
        scroll_cards.setFrameShape(QFrame.NoFrame)
        scroll_cards.setStyleSheet("background: transparent;")
        scroll_cards.setWidget(self.cards_container)
        main_layout.addWidget(scroll_cards)

        # ── Fast Operations Panel ───────────────────────────
        op_card = QFrame()
        op_card.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 14px;")
        op_layout = QVBoxLayout(op_card)
        op_layout.setSpacing(12)

        # Operations Selector Pills
        pills_layout = QHBoxLayout()
        pills_layout.setSpacing(8)

        self.op_buttons = {}
        ops = [
            ("cash_in", "📥 إيداع للعميل (Cash In)", "#2563EB"),
            ("cash_out", "📤 سحب نقدي (Cash Out)", "#16A34A"),
            ("bill", "🧾 دفع فواتير (Bill)", "#7C3AED"),
            ("recharge", "📱 شحن رصيد (Recharge)", "#EA580C"),
            ("fund", "💼 تمويل من الدرج (Fund)", "#0284C7"),
            ("withdraw", "🏦 تفريغ للدرج (Withdraw)", "#0D9488"),
        ]

        for op_id, op_label, color in ops:
            btn = QPushButton(op_label)
            btn.setFixedHeight(36)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, k=op_id: self._select_op_type(k))
            pills_layout.addWidget(btn)
            self.op_buttons[op_id] = btn

        pills_layout.addStretch()
        op_layout.addLayout(pills_layout)

        # Op Form Grid
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)

        # 1. Select Wallet
        grid.addWidget(QLabel("المحفظة المستخدمة: *"), 0, 0)
        self.op_wallet_combo = QComboBox()
        self.op_wallet_combo.setFixedHeight(40)
        self.op_wallet_combo.setMinimumWidth(220)
        self.op_wallet_combo.currentIndexChanged.connect(self._recalc_commission_preview)
        grid.addWidget(self.op_wallet_combo, 1, 0)

        # 2. Customer Phone
        grid.addWidget(QLabel("رقم هاتف العميل:"), 0, 1)
        self.op_phone_edit = QLineEdit()
        self.op_phone_edit.setFixedHeight(40)
        self.op_phone_edit.setPlaceholderText("010/011/012/015...")
        grid.addWidget(self.op_phone_edit, 1, 1)

        # 3. Amount
        grid.addWidget(QLabel("المبلغ المطلوب (ج.م): *"), 0, 2)
        self.op_amount_edit = QLineEdit()
        self.op_amount_edit.setFixedHeight(40)
        self.op_amount_edit.setPlaceholderText("0.00 ج.م")
        self.op_amount_edit.setValidator(QDoubleValidator(0.01, 9999999.0, 2))
        self.op_amount_edit.textChanged.connect(self._recalc_commission_preview)
        grid.addWidget(self.op_amount_edit, 1, 2)

        # 4. Reference / Transaction SMS Code
        grid.addWidget(QLabel("رقم العملية / المرجع (SMS):"), 0, 3)
        self.op_ref_edit = QLineEdit()
        self.op_ref_edit.setFixedHeight(40)
        self.op_ref_edit.setPlaceholderText("كود العملية من رسالة الشبكة...")
        grid.addWidget(self.op_ref_edit, 1, 3)

        # 5. Commission & Profit preview badge
        grid.addWidget(QLabel("العمولة والربح المتوقع:"), 0, 4)
        self.lbl_comm_preview = QLabel("العمولة: 0.00 ج.م | الربح: 0.00 ج.م")
        self.lbl_comm_preview.setFixedHeight(40)
        self.lbl_comm_preview.setStyleSheet(
            "background-color: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 8px; color: #1D4ED8; font-weight: bold; padding: 0 12px;"
        )
        grid.addWidget(self.lbl_comm_preview, 1, 4)

        # 6. Submit Button
        self.btn_execute = QPushButton("🚀 تنفيذ العملية")
        self.btn_execute.setFixedHeight(40)
        self.btn_execute.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: white;
                border-radius: 8px;
                font-weight: bold;
                font-size: 14px;
                padding: 0 24px;
            }
            QPushButton:hover {
                background-color: #1D4ED8;
            }
        """)
        self.btn_execute.clicked.connect(self._execute_operation)
        grid.addWidget(self.btn_execute, 1, 5)

        op_layout.addLayout(grid)
        main_layout.addWidget(op_card)

        # ── Transactions Ledger Table ───────────────────────
        table_card = QFrame()
        table_card.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 12px;")
        t_layout = QVBoxLayout(table_card)
        t_layout.setSpacing(10)

        # Table Filter Header
        t_bar = QHBoxLayout()
        t_title = QLabel("سجل حركات وعمليات المحافظ الإلكترونية")
        t_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #0F172A;")
        t_bar.addWidget(t_title)
        t_bar.addStretch()

        self.tx_filter_type = QComboBox()
        self.tx_filter_type.setFixedHeight(36)
        self.tx_filter_type.addItem("جميع العمليات", "all")
        self.tx_filter_type.addItem("إيداع فقط", "cash_in")
        self.tx_filter_type.addItem("سحب فقط", "cash_out")
        self.tx_filter_type.addItem("فواتير فقط", "bill")
        self.tx_filter_type.addItem("شحن فقط", "recharge")
        self.tx_filter_type.addItem("تمويل / تفريغ", "fund_withdraw")
        self.tx_filter_type.currentIndexChanged.connect(self.load_transactions)
        t_bar.addWidget(self.tx_filter_type)

        t_layout.addLayout(t_bar)

        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "#", "المحفظة", "نوع العملية", "هاتف العميل", "المبلغ", "العمولة", "صافي الربح", "أثر الدرج", "التاريخ والوقت"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Fixed); self.table.setColumnWidth(0, 40)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.Fixed); self.table.setColumnWidth(2, 120)
        h.setSectionResizeMode(3, QHeaderView.Fixed); self.table.setColumnWidth(3, 120)
        h.setSectionResizeMode(4, QHeaderView.Fixed); self.table.setColumnWidth(4, 110)
        h.setSectionResizeMode(5, QHeaderView.Fixed); self.table.setColumnWidth(5, 90)
        h.setSectionResizeMode(6, QHeaderView.Fixed); self.table.setColumnWidth(6, 90)
        h.setSectionResizeMode(7, QHeaderView.Fixed); self.table.setColumnWidth(7, 110)
        h.setSectionResizeMode(8, QHeaderView.Fixed); self.table.setColumnWidth(8, 140)
        t_layout.addWidget(self.table)

        main_layout.addWidget(table_card, 1)

        self._select_op_type("cash_in")

    def _select_op_type(self, op_id: str):
        self.current_op_type = op_id
        for k, btn in self.op_buttons.items():
            if k == op_id:
                btn.setChecked(True)
                btn.setStyleSheet(
                    "background-color: #2563EB; color: white; border-radius: 6px; font-weight: bold; padding: 0 12px;"
                )
            else:
                btn.setChecked(False)
                btn.setStyleSheet(
                    "background-color: #F1F5F9; color: #475569; border: 1px solid #CBD5E1; border-radius: 6px; font-weight: 600; padding: 0 12px;"
                )
        self._recalc_commission_preview()

    def _recalc_commission_preview(self):
        w: Optional[Wallet] = self.op_wallet_combo.currentData()
        if not w:
            return
        amt_text = self.op_amount_edit.text().strip()
        try:
            amt_piasters = egp_to_piasters(amt_text) if amt_text else 0
        except Exception:
            amt_piasters = 0

        if amt_piasters > 0:
            comm, net_fee = wallet_service.compute_commission(
                self.session, w.network, self.current_op_type, amt_piasters
            )
            profit = comm - net_fee
            self.lbl_comm_preview.setText(f"العمولة: {format_money(comm)} | الربح: {format_money(profit)}")
        else:
            self.lbl_comm_preview.setText("العمولة: 0.00 ج.م | الربح: 0.00 ج.م")

    def _execute_operation(self):
        w: Optional[Wallet] = self.op_wallet_combo.currentData()
        if not w:
            QMessageBox.warning(self, "تنبيه", "يرجى اختيار المحفظة")
            return

        amt_text = self.op_amount_edit.text().strip()
        if not amt_text:
            QMessageBox.warning(self, "تنبيه", "يرجى كتابة المبلغ")
            self.op_amount_edit.setFocus()
            return

        try:
            amt_piasters = egp_to_piasters(amt_text)
            if amt_piasters <= 0:
                raise ValueError()
        except Exception:
            QMessageBox.warning(self, "تنبيه", "صيغة المبلغ غير صحيحة")
            self.op_amount_edit.setFocus()
            return

        phone = self.op_phone_edit.text().strip()
        ref = self.op_ref_edit.text().strip()

        try:
            tx = wallet_service.execute_wallet_transaction(
                session=self.session,
                user=self.user,
                wallet_id=w.id,
                op_type=self.current_op_type,
                amount=amt_piasters,
                customer_phone=phone,
                reference=ref,
            )
            self.session.commit()
            QMessageBox.information(
                self,
                "تمت العملية بنجاح",
                f"تم تنفيذ عملية {tx.op_type} بمبلغ {format_money(tx.amount)} بنجاح!\n"
                f"أثر الدرج: {format_money(tx.cash_effect)} | رصيد المحفظة الجديد: {format_money(w.balance)}"
            )
            self.op_amount_edit.clear()
            self.op_phone_edit.clear()
            self.op_ref_edit.clear()
            self.load_all()
        except Exception as e:
            self.session.rollback()
            QMessageBox.critical(self, "خطأ في العملية", f"تعذر تنفيذ العملية:\n{str(e)}")

    def load_wallets_cards(self):
        # Clear layout
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        wallets = wallet_service.list_wallets(self.session, self.user)
        self.op_wallet_combo.clear()

        color_map = {
            "vodafone": ("#EF4444", "#FEF2F2", "🔴"),
            "orange": ("#F97316", "#FFF7ED", "🟠"),
            "etisalat": ("#10B981", "#ECFDF5", "🟢"),
            "we": ("#8B5CF6", "#F5F3FF", "🟣"),
            "instapay": ("#6366F1", "#EEF2FF", "⚡"),
        }

        for w in wallets:
            self.op_wallet_combo.addItem(f"{w.label} ({format_money(w.balance)})", w)

            primary, bg, icon = color_map.get(w.network.lower(), ("#2563EB", "#EFF6FF", "💳"))
            used_today, _ = wallet_service.get_wallet_usage(self.session, w.id)

            card = QFrame()
            card.setFixedWidth(240)
            card.setFixedHeight(115)
            card.setStyleSheet(f"""
                QFrame {{
                    background-color: #FFFFFF;
                    border: 2px solid {primary};
                    border-radius: 10px;
                }}
            """)
            c_layout = QVBoxLayout(card)
            c_layout.setContentsMargins(10, 8, 10, 8)
            c_layout.setSpacing(4)

            # Card Header
            h_row = QHBoxLayout()
            lbl_icon = QLabel(f"{icon} {w.label}")
            lbl_icon.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {primary};")
            h_row.addWidget(lbl_icon)
            h_row.addStretch()
            c_layout.addLayout(h_row)

            # Balance
            lbl_bal = QLabel(format_money(w.balance))
            lbl_bal.setStyleSheet("font-size: 18px; font-weight: bold; color: #0F172A;")
            c_layout.addWidget(lbl_bal)

            # Limit progress
            if w.daily_limit > 0:
                lbl_lim = QLabel(f"اليومي: {format_money(used_today)} / {format_money(w.daily_limit)}")
            else:
                lbl_lim = QLabel(f"الاستخدام اليومي: {format_money(used_today)}")
            lbl_lim.setStyleSheet("font-size: 11px; color: #64748B;")
            c_layout.addWidget(lbl_lim)

            self.cards_layout.addWidget(card)

        self.cards_layout.addStretch()

    def load_transactions(self):
        filter_val = self.tx_filter_type.currentData()
        op_filter = None if filter_val == "all" else (filter_val if filter_val != "fund_withdraw" else None)
        txs = wallet_service.list_wallet_transactions(self.session, self.user, op_type=op_filter, limit=100)

        if filter_val == "fund_withdraw":
            txs = [t for t in txs if t.op_type in ("fund", "withdraw")]

        self.table.setRowCount(len(txs))
        for idx, t in enumerate(txs):
            self.table.setItem(idx, 0, QTableWidgetItem(str(t.id)))
            self.table.setItem(idx, 1, QTableWidgetItem(t.wallet.label if t.wallet else "—"))

            op_ar = {
                "cash_in": "إيداع للعميل",
                "cash_out": "سحب نقدي",
                "bill": "دفع فاتورة",
                "recharge": "شحن رصيد",
                "fund": "تمويل المحفظة",
                "withdraw": "تفريغ للدرج",
            }.get(t.op_type, t.op_type)
            self.table.setItem(idx, 2, QTableWidgetItem(op_ar))

            self.table.setItem(idx, 3, QTableWidgetItem(t.customer_phone or "—"))

            amt_item = QTableWidgetItem(format_money(t.amount))
            amt_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(idx, 4, amt_item)

            comm_item = QTableWidgetItem(format_money(t.commission))
            comm_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(idx, 5, comm_item)

            profit_item = QTableWidgetItem(format_money(t.profit))
            profit_item.setTextAlignment(Qt.AlignCenter)
            if t.profit > 0:
                profit_item.setForeground(Qt.green)
            self.table.setItem(idx, 6, profit_item)

            cash_item = QTableWidgetItem(f"{'+' if t.cash_effect > 0 else ''}{format_money(t.cash_effect)}")
            cash_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(idx, 7, cash_item)

            date_str = t.created_at.strftime("%Y-%m-%d %H:%M")
            self.table.setItem(idx, 8, QTableWidgetItem(date_str))

    def _open_new_wallet_dialog(self):
        dlg = WalletDialog(self.session, self.user, parent=self)
        if dlg.exec() == WalletDialog.Accepted:
            self.load_all()

    def _open_rules_dialog(self):
        dlg = CommissionRulesDialog(self.session, self.user, parent=self)
        dlg.exec()

    def _open_audit_dialog(self):
        dlg = WalletAuditDialog(self.session, self.user, parent=self)
        if dlg.exec() == WalletAuditDialog.Accepted:
            self.load_all()

    def load_all(self):
        self.load_wallets_cards()
        self.load_transactions()

