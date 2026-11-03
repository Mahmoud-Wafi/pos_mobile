"""Consolidated Reports Center with multi-report preview, date filtering, and Excel export."""
from __future__ import annotations

import datetime
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QDateEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QMessageBox, QFrame, QFileDialog,
)

from app.core.money import format_money
from app.services import report_service


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
        bar.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 12px;")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setSpacing(12)

        # Report Type Selector
        bar_layout.addWidget(QLabel("نوع التقرير:"))
        self.report_type_combo = QComboBox()
        self.report_type_combo.setFixedHeight(38)
        self.report_type_combo.setMinimumWidth(220)
        self.report_type_combo.addItem("🛒 تقرير المبيعات التفصيلي", "sales")
        self.report_type_combo.addItem("📈 تقرير الأرباح والخسائر الشامل (P&L)", "profit")
        self.report_type_combo.addItem("📦 تقرير تقييم وجرد المخزون", "stock")
        self.report_type_combo.addItem("💳 تقرير المحافظ والعمولات", "wallet")
        self.report_type_combo.addItem("👥 تقرير المديونيات وحسابات الآجل", "debts")
        self.report_type_combo.addItem("💰 تقرير حركة الخزينة والنقدية", "cash")
        self.report_type_combo.currentIndexChanged.connect(self._on_type_changed)
        bar_layout.addWidget(self.report_type_combo)

        # Date Pickers
        self.lbl_from = QLabel("من تاريخ:")
        bar_layout.addWidget(self.lbl_from)
        self.date_from = QDateEdit()
        self.date_from.setFixedHeight(38)
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addDays(-30))
        bar_layout.addWidget(self.date_from)

        self.lbl_to = QLabel("إلى تاريخ:")
        bar_layout.addWidget(self.lbl_to)
        self.date_to = QDateEdit()
        self.date_to.setFixedHeight(38)
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        bar_layout.addWidget(self.date_to)

        # Run Button
        btn_run = QPushButton("🔍 استخراج التقرير")
        btn_run.setFixedHeight(38)
        btn_run.setStyleSheet("background-color: #2563EB; color: white; border-radius: 6px; font-weight: bold; padding: 0 16px;")
        btn_run.clicked.connect(self.run_report)
        bar_layout.addWidget(btn_run)

        # Export Excel Button
        btn_export = QPushButton("📥 تصدير Excel (CSV)")
        btn_export.setFixedHeight(38)
        btn_export.setStyleSheet("background-color: #16A34A; color: white; border-radius: 6px; font-weight: bold; padding: 0 16px;")
        btn_export.clicked.connect(self.export_excel)
        bar_layout.addWidget(btn_export)

        bar_layout.addStretch()
        main_layout.addWidget(bar)

        # ── KPI Summary Banner ──────────────────────────────
        self.kpi_banner = QFrame()
        self.kpi_banner.setStyleSheet("background-color: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 10px; padding: 12px;")
        self.kpi_layout = QHBoxLayout(self.kpi_banner)
        self.kpi_layout.setSpacing(20)
        self.lbl_summary = QLabel("جاري إعداد التقرير...")
        self.lbl_summary.setStyleSheet("font-size: 14px; font-weight: bold; color: #1E3A8A;")
        self.kpi_layout.addWidget(self.lbl_summary)
        self.kpi_layout.addStretch()
        main_layout.addWidget(self.kpi_banner)

        # ── Report Results Table ────────────────────────────
        self.table = QTableWidget()
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 10px;
            }
            QHeaderView::section {
                background-color: #F8FAFC;
                color: #334155;
                font-weight: bold;
                padding: 8px;
                border: none;
                border-bottom: 1px solid #E2E8F0;
            }
        """)
        main_layout.addWidget(self.table, 1)

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

            self.current_report_data = data
        except Exception as e:
            QMessageBox.critical(self, "خطأ في استخراج التقرير", str(e))

    def _render_sales(self, data: dict):
        self.lbl_summary.setText(
            f"🛒 عدد الفواتير: {data['total_invoices']} | "
            f"إجمالي المبيعات: {format_money(data['total_net'])} | "
            f"المحصل: {format_money(data['total_paid'])} | "
            f"المتبقي (آجل): {format_money(data['total_remaining'])} | "
            f"صافي الأرباح: {format_money(data['total_profit'])}"
        )
        headers = ["#", "رقم الفاتورة", "العميل", "التاريخ", "الأصناف", "الإجمالي", "المدفوع", "المتبقي", "الأرباح", "الكاشير"]
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
        net_str = f"+{format_money(net)}" if net > 0 else format_money(net)
        self.lbl_summary.setText(
            f"📈 إيرادات المبيعات: {format_money(data['sales_revenue'])} | "
            f"أرباح المبيعات: {format_money(data['sales_profit'])} | "
            f"أرباح المحافظ: {format_money(data['wallet_profit'])} | "
            f"المصروفات: -{format_money(data['total_expenses'])} | "
            f"صافي الربح النهائي: {net_str}"
        )
        headers = ["البند المالي", "القيمة الإجمالية", "الملاحظات وتفاصيل الاحتساب"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        items = [
            ("إيرادات المبيعات الإجمالية", format_money(data["sales_revenue"]), f"عدد {data['sales_count']} فاتورة بيع"),
            ("أرباح المبيعات التجارية (إجمالي الربح)", format_money(data["sales_profit"]), "سعر البيع ناقص تكلفة المنتجات والأجهزة"),
            ("عمولات وأرباح المحافظ الإلكترونية", format_money(data["wallet_profit"]), f"عدد {data['wallet_tx_count']} معاملة محفظة"),
            ("المصروفات التشغيلية للمحل", f"-{format_money(data['total_expenses'])}", f"عدد {data['expenses_count']} بند مصروف"),
            ("فروقات جرد الورديات (عجز / زيادة)", format_money(data["shift_diff"]), "الفروقات المسجلة على الكاشيرية عند الإغلاق"),
            ("صافي الربح التشغيلي النهائي (Net Profit)", net_str, "المحصلة النهائية لأرباح الفترة"),
        ]
        self.table.setRowCount(len(items))
        for idx, (b, val, note) in enumerate(items):
            self.table.setItem(idx, 0, QTableWidgetItem(b))
            v_item = QTableWidgetItem(val)
            v_item.setTextAlignment(Qt.AlignCenter)
            if idx == 5:
                v_item.setForeground(Qt.blue)
            self.table.setItem(idx, 1, v_item)
            self.table.setItem(idx, 2, QTableWidgetItem(note))

    def _render_stock(self, data: dict):
        self.lbl_summary.setText(
            f"📦 إجمالي الأصناف: {data['total_products']} | "
            f"الأصناف التي وصلت للحد الأدنى (نواقص): {data['low_stock_count']} صنف | "
            f"القيمة الإجمالية للمخزون بسعر التكلفة: {format_money(data['total_stock_cost_value']) if data['total_stock_cost_value'] else '—'} | "
            f"القيمة بسعر البيع: {format_money(data['total_stock_sale_value'])}"
        )
        headers = ["#", "اسم المنتج", "النوع", "الباركود", "الكمية المتاحة", "الحد الأدنى", "حالة النواقص", "سعر التكلفة", "سعر البيع", "إجمالي قيمة المخزون"]
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

            st_item = QTableWidgetItem("⚠️ نقص مخزون" if r["is_low"] else "🟢 متوفر")
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
            f"💳 عدد العمليات: {data['total_operations']} | "
            f"إجمالي مبالغ العمليات: {format_money(data['total_amount'])} | "
            f"إجمالي العمولات: {format_money(data['total_commission'])} | "
            f"صافي أرباح المحافظ: {format_money(data['total_profit'])}"
        )
        headers = ["#", "المحفظة", "نوع العملية", "هاتف العميل", "المبلغ", "العمولة", "صافي الربح", "التاريخ والوقت"]
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
            f"👥 ديون العملاء (لنا بالخارج): {format_money(data['total_receivables'])} (عدد {data['customers_count']} عميل) | "
            f"مستحقات الموردين (علينا): {format_money(data['total_payables'])} | "
            f"صافي المركز المالي للديون: {format_money(data['net_debt_position'])}"
        )
        headers = ["#", "النوع", "الاسم", "رقم الهاتف", "الرصيد المدين / الدائن"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        custs = data["customers"]
        sups = data["suppliers"]
        total_rows = len(custs) + len(sups)
        self.table.setRowCount(total_rows)

        cur = 0
        for c in custs:
            self.table.setItem(cur, 0, QTableWidgetItem(str(c["id"])))
            self.table.setItem(cur, 1, QTableWidgetItem("عميل (لنا)"))
            self.table.setItem(cur, 2, QTableWidgetItem(c["name"]))
            self.table.setItem(cur, 3, QTableWidgetItem(c["phone"]))
            b_item = QTableWidgetItem(format_money(c["balance"]))
            b_item.setForeground(Qt.red)
            self.table.setItem(cur, 4, b_item)
            cur += 1

        for s in sups:
            self.table.setItem(cur, 0, QTableWidgetItem(str(s["id"])))
            self.table.setItem(cur, 1, QTableWidgetItem("مورد (علينا)"))
            self.table.setItem(cur, 2, QTableWidgetItem(s["name"]))
            self.table.setItem(cur, 3, QTableWidgetItem(s["phone"]))
            b_item = QTableWidgetItem(format_money(s["balance"]))
            b_item.setForeground(Qt.darkRed)
            self.table.setItem(cur, 4, b_item)
            cur += 1

    def _render_cash(self, data: dict):
        self.lbl_summary.setText(
            f"💰 إجمالي المقبوضات: {format_money(data['total_in'])} | "
            f"إجمالي المدفوعات: {format_money(data['total_out'])} | "
            f"صافي التدفق النقدي: {format_money(data['net_cash_flow'])} | "
            f"الرصيد الفعلي الحالي بكافة الخزائن: {format_money(data['total_cash_now'])}"
        )
        headers = ["الخزينة / الحساب", "الرصيد الحالي", "الحالة"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        accs = data["accounts"]
        self.table.setRowCount(len(accs))
        for idx, (name, bal) in enumerate(accs.items()):
            self.table.setItem(idx, 0, QTableWidgetItem(name))
            b_item = QTableWidgetItem(format_money(bal))
            b_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(idx, 1, b_item)
            self.table.setItem(idx, 2, QTableWidgetItem("🟢 نشط"))

    def export_excel(self):
        if not self.current_report_data:
            QMessageBox.warning(self, "تنبيه", "يرجى استخراج التقرير أولاً")
            return

        rep_name = self.report_type_combo.currentText().replace(" ", "_")
        dest_file, _ = QFileDialog.getSaveFileName(
            self,
            "حفظ التقرير بصيغة Excel (CSV)",
            f"{rep_name}_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            "CSV Files (*.csv)",
        )
        if not dest_file:
            return

        try:
            report_service.export_report_to_csv(self.current_report_data, dest_file)
            msg = QMessageBox(self)
            msg.setWindowTitle("تم التصدير بنجاح")
            msg.setText(f"تم تصدير التقرير بنجاح إلى:\n{dest_file}")
            btn_open = msg.addButton("📂 فتح المجلد", QMessageBox.ActionRole)
            btn_ok = msg.addButton("حسناً", QMessageBox.AcceptRole)
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
            QMessageBox.critical(self, "خطأ في التصدير", str(e))

