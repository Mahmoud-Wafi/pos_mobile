"""Consolidated Reports Center with multi-report preview, date filtering, and Excel export."""
from __future__ import annotations
from app.i18n import ar

import datetime
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QLocale, QDate, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QDateEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QMessageBox, QFrame, QFileDialog,
)

from app.ui.components import show_error
from app.core.money import format_money_signed, format_money
from app.services import import_export_service
from app.services import report_service
from app.ui.design.style import set_prop, style_label, variant


class ReportsWidget(QWidget):
    def __init__(self, session, user, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self.current_report_data: dict[str, Any] = {}
        self._build_ui()
        self.run_report()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(14)

        # ── Control & Filter Bar ────────────────────────────
        bar = QFrame()
        set_prop(bar, "card", True)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setSpacing(12)

        # Report Type Selector
        bar_layout.addWidget(QLabel(ar.REPORTS_WINDOW_15DF36))
        self.report_type_combo = QComboBox()
        self.report_type_combo.setMinimumHeight(40)
        self.report_type_combo.setMinimumWidth(220)
        self.report_type_combo.addItem(ar.REPORTS_WINDOW_838E9A, "sales")
        self.report_type_combo.addItem(ar.REPORTS_WINDOW_005895, "profit")
        self.report_type_combo.addItem(ar.REPORTS_WINDOW_D6D3AB, "stock")
        self.report_type_combo.addItem(ar.REPORTS_WINDOW_D4FFBA, "wallet")
        self.report_type_combo.addItem(ar.REPORTS_WINDOW_21D66E, "debts")
        self.report_type_combo.addItem(ar.REPORTS_WINDOW_565B79, "cash")
        self.report_type_combo.currentIndexChanged.connect(self._on_type_changed)
        bar_layout.addWidget(self.report_type_combo)

        # Date Pickers
        self.lbl_from = QLabel(ar.REPORTS_WINDOW_75CD64)
        bar_layout.addWidget(self.lbl_from)
        self.date_from = QDateEdit()
        self.date_from.setMinimumHeight(40)
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("dd/MM/yyyy")
        self.date_from.setLocale(QLocale(QLocale.English))
        self.date_from.setMinimumWidth(130)
        self.date_from.setLayoutDirection(Qt.LeftToRight)
        self.date_from.setDate(QDate.currentDate().addDays(-30))
        bar_layout.addWidget(self.date_from)

        self.lbl_to = QLabel(ar.REPORTS_WINDOW_602217)
        bar_layout.addWidget(self.lbl_to)
        self.date_to = QDateEdit()
        self.date_to.setMinimumHeight(40)
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("dd/MM/yyyy")
        self.date_to.setLocale(QLocale(QLocale.English))
        self.date_to.setMinimumWidth(130)
        self.date_to.setLayoutDirection(Qt.LeftToRight)
        self.date_to.setDate(QDate.currentDate())
        bar_layout.addWidget(self.date_to)

        # Run Button
        btn_run = QPushButton(ar.REPORTS_WINDOW_B61D0F)
        btn_run.setMinimumHeight(40)
        variant(btn_run, "primary")
        btn_run.clicked.connect(self.run_report)
        bar_layout.addWidget(btn_run)

        # Export Excel Button
        btn_export = QPushButton(ar.EXPORT_BUTTON)
        btn_export.setMinimumHeight(40)
        variant(btn_export, "success")
        btn_export.clicked.connect(self.export_excel)
        bar_layout.addWidget(btn_export)

        bar_layout.addStretch()
        main_layout.addWidget(bar)

        # ── KPI Summary Banner ──────────────────────────────
        self.kpi_banner = QFrame()
        set_prop(self.kpi_banner, "banner", "info")
        self.kpi_layout = QHBoxLayout(self.kpi_banner)
        self.kpi_layout.setSpacing(20)
        self.lbl_summary = QLabel(ar.REPORTS_WINDOW_2E5B88)
        style_label(self.lbl_summary, size="label", tone="primary", bold=True)
        self.kpi_layout.addWidget(self.lbl_summary)
        self.kpi_layout.addStretch()
        main_layout.addWidget(self.kpi_banner)

        # ── Report Results Table ────────────────────────────
        self.table = QTableWidget()
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.horizontalHeader().setMinimumSectionSize(90)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)

        main_layout.addWidget(self.table, 1)

    def _fit_columns(self):
        """Few columns share the width evenly; many columns fit their content and the last one stretches."""
        hh = self.table.horizontalHeader()
        n = self.table.columnCount()
        hh.setStretchLastSection(n > 4)
        for c in range(n):
            hh.setSectionResizeMode(c, QHeaderView.Stretch if n <= 4 else QHeaderView.ResizeToContents)
        if n <= 4:
            hh.setSectionResizeMode(0, QHeaderView.Stretch)

    def _on_type_changed(self):
        rep_type = self.report_type_combo.currentData()
        is_dated = rep_type not in ("debts", "stock")
        self.lbl_from.setVisible(is_dated)
        self.date_from.setVisible(is_dated)
        self.lbl_to.setVisible(is_dated)
        self.date_to.setVisible(is_dated)
        self.run_report()

    def run_report(self):
        rep_type = self.report_type_combo.currentData()
        d_from = self.date_from.date().toPython()
        d_to = self.date_to.date().toPython()

        try:
            if rep_type == "sales":
                data = report_service.sales_report(self.session, self.user, start_date=d_from, end_date=d_to)
                self._render_sales(data)
            elif rep_type == "profit":
                data = report_service.profit_report(self.session, self.user, start_date=d_from, end_date=d_to)
                self._render_profit(data)
            elif rep_type == "stock":
                data = report_service.stock_report(self.session, self.user)
                self._render_stock(data)
            elif rep_type == "wallet":
                data = report_service.wallet_report(self.session, self.user, start_date=d_from, end_date=d_to)
                self._render_wallet(data)
            elif rep_type == "debts":
                data = report_service.debts_report(self.session, self.user)
                self._render_debts(data)
            elif rep_type == "cash":
                data = report_service.cash_report(self.session, self.user, start_date=d_from, end_date=d_to)
                self._render_cash(data)
            self._fit_columns()

            self.current_report_data = data
        except Exception as e:
            show_error(self, e)

    def _render_sales(self, data: dict):
        self.lbl_summary.setText(
            f"عدد الفواتير: {data['total_invoices']} | "
            f"إجمالي المبيعات: {format_money(data['total_net'])} | "
            f"المحصل: {format_money(data['total_paid'])} | "
            f"المتبقي (آجل): {format_money(data['total_remaining'])} | "
            f"صافي الأرباح: {format_money(data['total_profit'])}"
        )
        headers = ["#", ar.SALE_DONE_INVOICE, ar.RECEIPT_CUSTOMER, ar.RECEIPT_DATE, ar.REPORTS_WINDOW_817AD5, ar.TOTAL, ar.PAID, ar.REMAINING, ar.REPORTS_WINDOW_E3A4DB, ar.RECEIPT_CASHIER]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        rows = data["rows"]
        self.table.setRowCount(len(rows))
        for idx, r in enumerate(rows):
            self.table.setItem(idx, 0, QTableWidgetItem(str(r["id"])))
            self.table.setItem(idx, 1, QTableWidgetItem(r["invoice_no"]))
            self.table.setItem(idx, 2, QTableWidgetItem(r["customer_name"]))
            self.table.setItem(idx, 3, QTableWidgetItem(r["date"]))
            self.table.setItem(idx, 4, QTableWidgetItem(str(r["items_count"])))
            self.table.setItem(idx, 5, QTableWidgetItem(format_money(r["total"])))
            self.table.setItem(idx, 6, QTableWidgetItem(format_money(r["paid"])))

            rem = QTableWidgetItem(format_money(r["remaining"]))
            if r["remaining"] > 0:
                rem.setForeground(Qt.red)
            self.table.setItem(idx, 7, rem)

            prof_str = format_money(r["profit"]) if r["profit"] is not None else "—"
            self.table.setItem(idx, 8, QTableWidgetItem(prof_str))
            self.table.setItem(idx, 9, QTableWidgetItem(r["cashier"]))

    def _render_profit(self, data: dict):
        net = data["net_profit"]
        net_str = format_money_signed(net, always_sign=True)
        self.lbl_summary.setText(
            f"إيرادات المبيعات: {format_money(data['sales_revenue'])} | "
            f"أرباح المبيعات: {format_money(data['sales_profit'])} | "
            f"أرباح المحافظ: {format_money(data['wallet_profit'])} | "
            f"المصروفات: {format_money_signed(-data['total_expenses'])} | "
            f"صافي الربح النهائي: {net_str}"
        )
        headers = [ar.REPORTS_WINDOW_6563F3, ar.REPORTS_WINDOW_3A2A8B, ar.REPORTS_WINDOW_77A8AD]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        items = [
            (ar.REPORTS_WINDOW_9D5DF6, format_money(data["sales_revenue"]), f"عدد {data['sales_count']} فاتورة بيع"),
            (ar.REPORTS_WINDOW_E2D567, format_money(data["sales_profit"]), ar.REPORTS_WINDOW_9E7E22),
            (ar.REPORTS_WINDOW_FBB020, format_money(data["wallet_profit"]), f"عدد {data['wallet_tx_count']} معاملة محفظة"),
            (ar.REPORTS_WINDOW_7CA15C, format_money_signed(-data['total_expenses']), f"عدد {data['expenses_count']} بند مصروف"),
            (ar.REPORTS_WINDOW_F1D231, format_money(data["shift_diff"]), ar.REPORTS_WINDOW_66541C),
            (ar.REPORTS_WINDOW_9BAB0A, net_str, ar.REPORTS_WINDOW_DB4B49),
        ]
        self.table.setRowCount(len(items))
        for idx, (b, val, note) in enumerate(items):
            self.table.setItem(idx, 0, QTableWidgetItem(b))
            v_item = QTableWidgetItem(val)
            v_item.setTextAlignment(Qt.AlignCenter)
            if idx == 5:
                v_item.setForeground(Qt.darkGreen if net >= 0 else Qt.red)
                f = v_item.font()
                f.setBold(True)
                v_item.setFont(f)
            self.table.setItem(idx, 1, v_item)
            self.table.setItem(idx, 2, QTableWidgetItem(note))

    def _render_stock(self, data: dict):
        self.lbl_summary.setText(
            f"إجمالي الأصناف: {data['total_products']} | "
            f"الأصناف التي وصلت للحد الأدنى (نواقص): {data['low_stock_count']} صنف | "
            f"القيمة الإجمالية للمخزون بسعر التكلفة: {format_money(data['total_stock_cost_value']) if data['total_stock_cost_value'] else '—'} | "
            f"القيمة بسعر البيع: {format_money(data['total_stock_sale_value'])}"
        )
        headers = ["#", ar.LOW_STOCK_WIDGET_1AB391, ar.LOW_STOCK_WIDGET_A70B01, ar.PRODUCT_LIST_95520D, ar.REPORTS_WINDOW_2414C1, ar.DASH_MIN, ar.REPORTS_WINDOW_21C100, ar.REPORTS_WINDOW_2FFE9B, ar.PRODUCT_LIST_13E684, ar.REPORTS_WINDOW_7811C0]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        rows = data["rows"]
        self.table.setRowCount(len(rows))
        for idx, r in enumerate(rows):
            self.table.setItem(idx, 0, QTableWidgetItem(str(r["id"])))
            self.table.setItem(idx, 1, QTableWidgetItem(r["name"]))
            self.table.setItem(idx, 2, QTableWidgetItem(r["type"]))
            self.table.setItem(idx, 3, QTableWidgetItem(r["barcode"]))
            self.table.setItem(idx, 4, QTableWidgetItem(str(r["quantity"])))
            self.table.setItem(idx, 5, QTableWidgetItem(str(r["min_stock"])))

            st_item = QTableWidgetItem(ar.REPORTS_WINDOW_239317 if r["is_low"] else ar.REPORTS_WINDOW_3A550A)
            if r["is_low"]:
                st_item.setForeground(Qt.red)
            self.table.setItem(idx, 6, st_item)

            cost_str = format_money(r["cost_price"]) if r["cost_price"] is not None else "—"
            self.table.setItem(idx, 7, QTableWidgetItem(cost_str))
            self.table.setItem(idx, 8, QTableWidgetItem(format_money(r["sale_price"])))
            tot_str = format_money(r["stock_sale_value"])
            self.table.setItem(idx, 9, QTableWidgetItem(tot_str))

    def _render_wallet(self, data: dict):
        self.lbl_summary.setText(
            f"عدد العمليات: {data['total_operations']} | "
            f"إجمالي مبالغ العمليات: {format_money(data['total_amount'])} | "
            f"إجمالي العمولات: {format_money(data['total_commission'])} | "
            f"صافي أرباح المحافظ: {format_money(data['total_profit'])}"
        )
        headers = ["#", ar.REPORTS_WINDOW_1FE6B8, ar.REPORTS_WINDOW_72127C, ar.REPORTS_WINDOW_2C473A, ar.ACCOUNTING_WINDOW_FABA46, ar.REPORTS_WINDOW_F109E1, ar.REPORTS_WINDOW_9B69AB, ar.REPORTS_WINDOW_FF5C9D]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        rows = data["rows"]
        self.table.setRowCount(len(rows))
        for idx, r in enumerate(rows):
            self.table.setItem(idx, 0, QTableWidgetItem(str(r["id"])))
            self.table.setItem(idx, 1, QTableWidgetItem(r["wallet_label"]))
            self.table.setItem(idx, 2, QTableWidgetItem(r["op_type"]))
            self.table.setItem(idx, 3, QTableWidgetItem(r["phone"]))
            self.table.setItem(idx, 4, QTableWidgetItem(format_money(r["amount"])))
            self.table.setItem(idx, 5, QTableWidgetItem(format_money(r["commission"])))
            self.table.setItem(idx, 6, QTableWidgetItem(format_money(r["profit"])))
            self.table.setItem(idx, 7, QTableWidgetItem(r["date"]))

    def _render_debts(self, data: dict):
        self.lbl_summary.setText(
            f"ديون العملاء (لنا بالخارج): {format_money(data['total_receivables'])} (عدد {data['customers_count']} عميل) | "
            f"مستحقات الموردين (علينا): {format_money(data['total_payables'])} | "
            f"صافي المركز المالي للديون: {format_money(data['net_debt_position'])}"
        )
        headers = ["#", ar.LOW_STOCK_WIDGET_A70B01, ar.REPORTS_WINDOW_2E8B17, ar.SET_SHOP_PHONE, ar.REPORTS_WINDOW_23D797]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        custs = data["customers"]
        sups = data["suppliers"]
        total_rows = len(custs) + len(sups)
        self.table.setRowCount(total_rows)

        cur = 0
        for c in custs:
            self.table.setItem(cur, 0, QTableWidgetItem(str(c["id"])))
            self.table.setItem(cur, 1, QTableWidgetItem(ar.REPORTS_WINDOW_DE25CD))
            self.table.setItem(cur, 2, QTableWidgetItem(c["name"]))
            self.table.setItem(cur, 3, QTableWidgetItem(c["phone"]))
            b_item = QTableWidgetItem(format_money(c["balance"]))
            b_item.setForeground(Qt.red)
            self.table.setItem(cur, 4, b_item)
            cur += 1

        for s in sups:
            self.table.setItem(cur, 0, QTableWidgetItem(str(s["id"])))
            self.table.setItem(cur, 1, QTableWidgetItem(ar.REPORTS_WINDOW_D13E71))
            self.table.setItem(cur, 2, QTableWidgetItem(s["name"]))
            self.table.setItem(cur, 3, QTableWidgetItem(s["phone"]))
            b_item = QTableWidgetItem(format_money(s["balance"]))
            b_item.setForeground(Qt.darkRed)
            self.table.setItem(cur, 4, b_item)
            cur += 1

    def _render_cash(self, data: dict):
        self.lbl_summary.setText(
            f"إجمالي المقبوضات: {format_money(data['total_in'])} | "
            f"إجمالي المدفوعات: {format_money(data['total_out'])} | "
            f"صافي التدفق النقدي: {format_money(data['net_cash_flow'])} | "
            f"الرصيد الفعلي الحالي بكافة الخزائن: {format_money(data['total_cash_now'])}"
        )
        headers = [ar.REPORTS_WINDOW_126615, ar.REPORTS_WINDOW_0274F6, ar.USERS_STATUS]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        accs = data["accounts"]
        self.table.setRowCount(len(accs))
        for idx, (name, bal) in enumerate(accs.items()):
            self.table.setItem(idx, 0, QTableWidgetItem(name))
            b_item = QTableWidgetItem(format_money(bal))
            b_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(idx, 1, b_item)
            self.table.setItem(idx, 2, QTableWidgetItem(ar.PRODUCT_LIST_8CAAF9))

    def export_excel(self):
        if not self.current_report_data:
            show_error(self, message=ar.REPORTS_WINDOW_C6E818)
            return

        rep_name = self.report_type_combo.currentText().replace(" ", "_")
        dest_file, _ = QFileDialog.getSaveFileName(
            self,
            ar.REPORTS_WINDOW_FE7931,
            f"{rep_name}_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            "Excel (*.xlsx);;CSV (*.csv)",
        )
        if not dest_file:
            return

        try:
            import_export_service.export_report(self.user, self.current_report_data, dest_file)
            msg = QMessageBox(self)
            msg.setWindowTitle(ar.REPORTS_WINDOW_25AC5F)
            msg.setText(f"تم تصدير التقرير بنجاح إلى:\n{dest_file}")
            btn_open = msg.addButton(ar.REPORTS_WINDOW_92B734, QMessageBox.ActionRole)
            btn_ok = msg.addButton(ar.DIALOGS_E5B1B2, QMessageBox.AcceptRole)
            msg.exec()

            if msg.clickedButton() == btn_open:
                folder = str(Path(dest_file).parent)
                if sys.platform.startswith("linux"):
                    subprocess.Popen(["xdg-open", folder])
                elif sys.platform.startswith("win"):
                    os.startfile(folder)
                elif sys.platform.startswith("darwin"):
                    subprocess.Popen(["open", folder])
        except Exception as e:
            show_error(self, e)

