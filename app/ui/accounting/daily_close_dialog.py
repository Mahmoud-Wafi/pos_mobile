"""Consolidated daily close report dialog for managers."""
from __future__ import annotations

import datetime
from app.ui.components import show_error
from app.core import clock
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame, QGridLayout,
)

from app.core.money import format_money
from app.services import accounting_service
from app.ui.design.style import set_prop, style_label, variant
from app.ui.design import icons
from app.ui.design.tokens import COLORS


class DailyCloseDialog(QDialog):
    def __init__(self, session, user, ref_date: datetime.date = None, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self.ref_date = ref_date or clock.local_today()
        self.setWindowTitle(f"تقرير الإغلاق المالي اليومي — {self.ref_date.strftime('%Y-%m-%d')}")
        self.resize(750, 640)
        self.setModal(True)

        self._build_ui()
        self._load_report()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header
        hdr = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(icons.pixmap("chart-column", COLORS["primary"], 28))
        hdr.addWidget(icon)

        t_box = QVBoxLayout()
        t_box.setSpacing(2)
        lbl_t = QLabel(f"ملخص الإغلاق المالي والأرباح لليوم ({self.ref_date.strftime('%Y-%m-%d')})")
        style_label(lbl_t, size="title", tone="text", bold=True)
        lbl_sub = QLabel("تقرير مالي شامل يجمع المبيعات والمشتريات والمصروفات وعمولات المحافظ وصافي الأرباح")
        style_label(lbl_sub, size="caption", tone="muted")
        t_box.addWidget(lbl_t)
        t_box.addWidget(lbl_sub)
        hdr.addLayout(t_box)
        hdr.addStretch()
        layout.addLayout(hdr)

        # Main Report Grid
        card = QFrame()
        card.setObjectName("ReportCard")
        grid = QGridLayout(card)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(12)

        # Sales Section
        grid.addWidget(self._make_sec_title("1. المبيعات والأرباح التجارية"), 0, 0, 1, 2)
        self.lbl_sales_tot = QLabel("إجمالي المبيعات: 0.00 ج.م (عدد: 0)")
        self.lbl_sales_paid = QLabel("المحصل نقداً: 0.00 ج.م")
        self.lbl_sales_profit = QLabel("أرباح المبيعات المحققة: 0.00 ج.م")
        style_label(self.lbl_sales_profit, tone="success", bold=True)
        grid.addWidget(self.lbl_sales_tot, 1, 0)
        grid.addWidget(self.lbl_sales_paid, 1, 1)
        grid.addWidget(self.lbl_sales_profit, 2, 0)

        # Purchases Section
        grid.addWidget(self._make_sec_title("2. المشتريات والتوريدات"), 3, 0, 1, 2)
        self.lbl_pur_tot = QLabel("إجمالي فواتير الشراء: 0.00 ج.م")
        self.lbl_pur_paid = QLabel("المدفوع نقداً للموردين: 0.00 ج.م")
        grid.addWidget(self.lbl_pur_tot, 4, 0)
        grid.addWidget(self.lbl_pur_paid, 4, 1)

        # Wallets Section
        grid.addWidget(self._make_sec_title("3. عمولات المحافظ الإلكترونية"), 5, 0, 1, 2)
        self.lbl_w_comm = QLabel("إجمالي العمولات المحصلة: 0.00 ج.م")
        self.lbl_w_profit = QLabel("صافي أرباح المحافظ: 0.00 ج.م")
        style_label(self.lbl_w_profit, tone="success", bold=True)
        grid.addWidget(self.lbl_w_comm, 6, 0)
        grid.addWidget(self.lbl_w_profit, 6, 1)

        # Expenses & Shifts
        grid.addWidget(self._make_sec_title("4. المصروفات وفروقات الورديات"), 7, 0, 1, 2)
        self.lbl_expenses = QLabel("المصروفات التشغيلية: 0.00 ج.م")
        style_label(self.lbl_expenses, tone="danger", bold=True)
        self.lbl_shifts = QLabel("عجز / زيادة الورديات: 0.00 ج.م")
        self.lbl_draws = QLabel("مسحوبات المالك الشخصية: 0.00 ج.م")
        grid.addWidget(self.lbl_expenses, 8, 0)
        grid.addWidget(self.lbl_shifts, 8, 1)
        grid.addWidget(self.lbl_draws, 9, 0)

        layout.addWidget(card)

        # Net Profit Card Banner
        net_card = QFrame()
        set_prop(net_card, "banner", "info")
        n_layout = QHBoxLayout(net_card)
        n_lbl = QLabel("صافي ربح اليوم التقديري (Net Profit):")
        style_label(n_lbl, size="title", tone="primary", bold=True)
        self.lbl_net_profit = QLabel("0.00 ج.م")
        style_label(self.lbl_net_profit, size="h2", tone="primary", bold=True)
        n_layout.addWidget(n_lbl)
        n_layout.addStretch()
        n_layout.addWidget(self.lbl_net_profit)
        layout.addWidget(net_card)

        layout.addStretch()

        btn_close = QPushButton("إغلاق")
        btn_close.setFixedHeight(40)
        variant(btn_close, "secondary")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

    def _make_sec_title(self, text: str) -> QLabel:
        lbl = QLabel(text)
        style_label(lbl, size="label", tone="text", bold=True)
        return lbl

    def _load_report(self):
        try:
            rep = accounting_service.daily_close(self.session, self.user, ref_date=self.ref_date)
            sales = rep["sales"]
            self.lbl_sales_tot.setText(f"إجمالي المبيعات: {format_money(sales['total'])} (عدد الفواتير: {sales['count']})")
            self.lbl_sales_paid.setText(f"المحصل نقداً: {format_money(sales['paid'])}")
            self.lbl_sales_profit.setText(f"أرباح المبيعات المحققة: {format_money(sales['profit'])}")

            pur = rep["purchases"]
            self.lbl_pur_tot.setText(f"إجمالي فواتير الشراء: {format_money(pur['total'])} (عدد: {pur['count']})")
            self.lbl_pur_paid.setText(f"المدفوع نقداً للموردين: {format_money(pur['paid'])}")

            wallets = rep["wallets"]
            self.lbl_w_comm.setText(f"إجمالي العمولات المحصلة: {format_money(wallets['commission'])}")
            self.lbl_w_profit.setText(f"صافي أرباح المحافظ: {format_money(wallets['profit'])}")

            self.lbl_expenses.setText(f"المصروفات التشغيلية: {format_money(rep['expenses'])}")
            self.lbl_draws.setText(f"مسحوبات المالك الشخصية: {format_money(rep['owner_draws'])}")

            diff = rep["shift_diff"]
            diff_str = f"+{format_money(diff)}" if diff > 0 else format_money(diff)
            self.lbl_shifts.setText(f"عجز / زيادة الورديات: {diff_str}")

            net = rep["net_profit"]
            self.lbl_net_profit.setText(format_money(net))
            if net >= 0:
                style_label(self.lbl_net_profit, size="h2", tone="success", bold=True)
            else:
                style_label(self.lbl_net_profit, size="h2", tone="danger", bold=True)
        except Exception as e:
            show_error(self, message=f"تعذر تحميل التقرير اليومي:\n{str(e)}")

