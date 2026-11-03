"""Consolidated daily close report dialog for managers."""
from __future__ import annotations

import datetime
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame, QGridLayout,
)

from app.core.money import format_money
from app.services import accounting_service


class DailyCloseDialog(QDialog):
    def __init__(self, session, user, ref_date: datetime.date = None, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self.ref_date = ref_date or datetime.date.today()
        self.setWindowTitle(f"تقرير الإغلاق المالي اليومي — {self.ref_date.strftime('%Y-%m-%d')}")
        self.resize(750, 640)
        self.setModal(True)
        self.setStyleSheet("""
            QDialog {
                background-color: #F8FAFC;
            }
            QLabel {
                color: #0F172A;
                font-size: 13px;
            }
            QFrame#ReportCard {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 10px;
                padding: 12px;
            }
        """)
        self._build_ui()
        self._load_report()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header
        hdr = QHBoxLayout()
        icon = QLabel("📊")
        icon.setStyleSheet("font-size: 28px;")
        hdr.addWidget(icon)

        t_box = QVBoxLayout()
        t_box.setSpacing(2)
        lbl_t = QLabel(f"ملخص الإغلاق المالي والأرباح لليوم ({self.ref_date.strftime('%Y-%m-%d')})")
        lbl_t.setStyleSheet("font-size: 17px; font-weight: bold; color: #0F172A;")
        lbl_sub = QLabel("تقرير مالي شامل يجمع المبيعات والمشتريات والمصروفات وعمولات المحافظ وصافي الأرباح")
        lbl_sub.setStyleSheet("font-size: 12px; color: #64748B;")
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
        grid.addWidget(self._make_sec_title("🛒 1. المبيعات والأرباح التجارية"), 0, 0, 1, 2)
        self.lbl_sales_tot = QLabel("إجمالي المبيعات: 0.00 ج.م (عدد: 0)")
        self.lbl_sales_paid = QLabel("المحصل نقداً: 0.00 ج.م")
        self.lbl_sales_profit = QLabel("أرباح المبيعات المحققة: 0.00 ج.م")
        self.lbl_sales_profit.setStyleSheet("font-weight: bold; color: #16A34A;")
        grid.addWidget(self.lbl_sales_tot, 1, 0)
        grid.addWidget(self.lbl_sales_paid, 1, 1)
        grid.addWidget(self.lbl_sales_profit, 2, 0)

        # Purchases Section
        grid.addWidget(self._make_sec_title("📦 2. المشتريات والتوريدات"), 3, 0, 1, 2)
        self.lbl_pur_tot = QLabel("إجمالي فواتير الشراء: 0.00 ج.م")
        self.lbl_pur_paid = QLabel("المدفوع نقداً للموردين: 0.00 ج.م")
        grid.addWidget(self.lbl_pur_tot, 4, 0)
        grid.addWidget(self.lbl_pur_paid, 4, 1)

        # Wallets Section
        grid.addWidget(self._make_sec_title("💳 3. عمولات المحافظ الإلكترونية"), 5, 0, 1, 2)
        self.lbl_w_comm = QLabel("إجمالي العمولات المحصلة: 0.00 ج.م")
        self.lbl_w_profit = QLabel("صافي أرباح المحافظ: 0.00 ج.م")
        self.lbl_w_profit.setStyleSheet("font-weight: bold; color: #16A34A;")
        grid.addWidget(self.lbl_w_comm, 6, 0)
        grid.addWidget(self.lbl_w_profit, 6, 1)

        # Expenses & Shifts
        grid.addWidget(self._make_sec_title("💸 4. المصروفات وفروقات الورديات"), 7, 0, 1, 2)
        self.lbl_expenses = QLabel("المصروفات التشغيلية: 0.00 ج.م")
        self.lbl_expenses.setStyleSheet("font-weight: bold; color: #DC2626;")
        self.lbl_shifts = QLabel("عجز / زيادة الورديات: 0.00 ج.م")
        self.lbl_draws = QLabel("مسحوبات المالك الشخصية: 0.00 ج.م")
        grid.addWidget(self.lbl_expenses, 8, 0)
        grid.addWidget(self.lbl_shifts, 8, 1)
        grid.addWidget(self.lbl_draws, 9, 0)

        layout.addWidget(card)

        # Net Profit Card Banner
        net_card = QFrame()
        net_card.setStyleSheet("background-color: #EFF6FF; border: 2px solid #2563EB; border-radius: 10px; padding: 14px;")
        n_layout = QHBoxLayout(net_card)
        n_lbl = QLabel("صافي ربح اليوم التقديري (Net Profit):")
        n_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #1E3A8A;")
        self.lbl_net_profit = QLabel("0.00 ج.م")
        self.lbl_net_profit.setStyleSheet("font-size: 20px; font-weight: bold; color: #2563EB;")
        n_layout.addWidget(n_lbl)
        n_layout.addStretch()
        n_layout.addWidget(self.lbl_net_profit)
        layout.addWidget(net_card)

        layout.addStretch()

        btn_close = QPushButton("إغلاق")
        btn_close.setFixedHeight(40)
        btn_close.setStyleSheet("background-color: #F1F5F9; color: #475569; border: 1px solid #CBD5E1; border-radius: 8px; font-weight: bold;")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

    def _make_sec_title(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #0F172A; border-bottom: 1px solid #E2E8F0; padding-bottom: 4px; margin-top: 6px;")
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
                self.lbl_net_profit.setStyleSheet("font-size: 20px; font-weight: bold; color: #16A34A;")
            else:
                self.lbl_net_profit.setStyleSheet("font-size: 20px; font-weight: bold; color: #DC2626;")
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"تعذر تحميل التقرير اليومي:\n{str(e)}")

