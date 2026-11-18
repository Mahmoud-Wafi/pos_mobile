"""Dashboard: KPI cards with yesterday comparison, 7-day sales chart, top products, wallets, low stock."""
from __future__ import annotations

from PySide6.QtCharts import QBarCategoryAxis, QBarSeries, QBarSet, QChart, QChartView, QValueAxis
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from app.core.money import format_money, piasters_to_input
from app.i18n import ar
from app.services import report_service
from app.ui.components import Card, DataTable, EmptyState, KpiCard, PageHeader, button, icon_button
from app.ui.design.style import set_prop, text_role
from app.ui.design.tokens import COLORS as C

_DAYS = ["اثنين", "ثلاثاء", "أربعاء", "خميس", "جمعة", "سبت", "أحد"]


class SalesChart(QChartView):
    """7-day sales bars (EGP). Rendered with QtCharts, fully offline."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setLayoutDirection(Qt.LeftToRight)
        self.setMinimumHeight(220)
        self.setFrameShape(QFrame.NoFrame)
        self.set_data([])

    def set_data(self, series: list[dict]) -> None:
        chart = QChart()
        chart.legend().hide()
        chart.setBackgroundVisible(False)
        chart.setMargins(chart.margins())
        bars = QBarSet(ar.DASH_SALES)
        bars.setColor(QColor(C["primary"]))
        bars.setBorderColor(QColor(C["primary"]))
        cats, top = [], 0.0
        for d in series:
            v = float(piasters_to_input(d["total"]))
            bars.append(v)
            top = max(top, v)
            cats.append(f"{_DAYS[d['date'].weekday()]}\n{d['date'].day}")
        s = QBarSeries()
        s.append(bars)
        s.setLabelsVisible(False)
        chart.addSeries(s)
        ax = QBarCategoryAxis()
        ax.append(cats)
        chart.addAxis(ax, Qt.AlignBottom)
        s.attachAxis(ax)
        ay = QValueAxis()
        ay.setRange(0, top * 1.1 if top else 100)
        ay.setLabelFormat("%.0f")
        ay.applyNiceNumbers()
        chart.addAxis(ay, Qt.AlignLeft)
        s.attachAxis(ay)
        self.setChart(chart)
        self.bar_values = [bars.at(i) for i in range(bars.count())]


class DashboardWidget(QWidget):
    open_pos_requested = Signal()
    open_inventory_requested = Signal()
    open_purchases_requested = Signal()
    open_wallets_requested = Signal()
    open_accounting_requested = Signal()
    open_customers_requested = Signal()
    open_reports_requested = Signal()

    def __init__(self, session, user, parent=None):
        super().__init__(parent)
        self.session, self.user = session, user
        self._build_ui()
        self.refresh_data()

    # ── layout ───────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack)

        self.loading = EmptyState(ar.DASH_LOADING, "clock")
        self.stack.addWidget(self.loading)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        set_prop(scroll, "transparent", True)
        body = QWidget()
        set_prop(body, "transparent", True)
        scroll.setWidget(body)
        self.stack.addWidget(scroll)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(16)

        self.header = PageHeader(ar.NAV_DASHBOARD)
        self.lbl_date = QLabel()
        text_role(self.lbl_date, "muted")
        self.header.actions.addWidget(self.lbl_date)
        self.header.add_action(button(ar.REFRESH, "secondary", "rotate-cw")).clicked.connect(self.refresh_data)
        lay.addWidget(self.header)

        # KPI row
        self.kpi_row = QHBoxLayout()
        self.kpi_row.setSpacing(12)
        self.kpi_sales = KpiCard(ar.DASH_SALES_TODAY)
        self.kpi_count = KpiCard(ar.DASH_INVOICES_TODAY)
        self.kpi_profit = KpiCard(ar.DASH_PROFIT_TODAY)
        self.kpi_cash = KpiCard(ar.DASH_DRAWER)
        self.kpi_debt = KpiCard(ar.DASH_RECEIVABLES)
        for k in (self.kpi_sales, self.kpi_count, self.kpi_profit, self.kpi_cash, self.kpi_debt):
            self.kpi_row.addWidget(k)
        lay.addLayout(self.kpi_row)

        # chart + top products
        mid = QHBoxLayout()
        mid.setSpacing(12)
        self.chart_card = Card()
        t = QLabel(ar.DASH_LAST7)
        text_role(t, "title")
        self.chart_card.body.addWidget(t)
        self.chart = SalesChart()
        self.chart_card.body.addWidget(self.chart)
        self.chart_empty = EmptyState(ar.DASH_NO_SALES, "chart-column")
        self.chart_card.body.addWidget(self.chart_empty)
        mid.addWidget(self.chart_card, 3)

        self.top_card = Card()
        t = QLabel(ar.DASH_TOP5)
        text_role(t, "title")
        self.top_card.body.addWidget(t)
        self.top_table = DataTable([ar.COL_PRODUCT, ar.CART_QTY, ar.HISTORY_COL_TOTAL], ar.DASH_NO_SALES)
        self.top_table.setMinimumHeight(220)
        self.top_card.body.addWidget(self.top_table)
        mid.addWidget(self.top_card, 2)
        lay.addLayout(mid)

        # wallets strip
        self.wallet_card = Card()
        t = QLabel(ar.DASH_WALLETS)
        text_role(t, "title")
        self.wallet_card.body.addWidget(t)
        self.wallet_strip = QHBoxLayout()
        self.wallet_strip.setSpacing(10)
        self.wallet_card.body.addLayout(self.wallet_strip)
        lay.addWidget(self.wallet_card)

        # low stock
        low = Card()
        head = QHBoxLayout()
        t = QLabel(ar.DASH_LOW_STOCK)
        text_role(t, "title")
        head.addWidget(t)
        head.addStretch()
        self.btn_reorder = button(ar.DASH_REORDER, "primary", "plus")
        self.btn_reorder.clicked.connect(self.open_purchases_requested.emit)
        head.addWidget(self.btn_reorder)
        low.body.addLayout(head)
        self.low_table = DataTable([ar.COL_PRODUCT, ar.COL_STOCK, ar.DASH_MIN, ""], ar.DASH_STOCK_OK)
        self.low_table.setMinimumHeight(170)
        low.body.addWidget(self.low_table)
        lay.addWidget(low)

    # ── data ─────────────────────────────────────────────────────────────
    def refresh_data(self) -> None:
        self.stack.setCurrentIndex(0)           # loading state while the queries run
        try:
            self.session.rollback()
            m = report_service.dashboard_overview(self.session, self.user)
        except Exception:
            self.session.rollback()
            self.stack.setCurrentIndex(1)
            raise
        self.lbl_date.setText(f"{ar.DASH_TODAY}: {m['today'].strftime('%Y-%m-%d')}")
        self._fill_kpis(m)
        self._fill_charts(m)
        self._fill_wallets(m)
        self._fill_low_stock(m)
        self.stack.setCurrentIndex(1)

    def _fill_kpis(self, m: dict) -> None:
        sales = m["sales"]
        for card in (self.kpi_sales, self.kpi_count, self.kpi_profit):
            card.setVisible(sales is not None)
        if sales is not None:
            t, y = sales["today"], sales["yesterday"]
            pct = report_service.change_percent(t["total"], y["total"])
            self.kpi_sales.set_value(format_money(t["total"]), self._compare(pct, y["total"]))
            self.kpi_count.set_value(str(t["count"]), ar.DASH_YESTERDAY.format(n=y["count"]))
            self.kpi_profit.setVisible(t["profit"] is not None)       # hidden without profit permission
            if t["profit"] is not None:
                self.kpi_profit.set_value(format_money(t["profit"]))
        self.kpi_cash.setVisible(m["cash"] is not None)
        if m["cash"] is not None:
            self.kpi_cash.set_value(format_money(m["cash"]["drawer"]), f"{ar.DASH_SAFE}: {format_money(m['cash']['safe'])}")
        self.kpi_debt.setVisible(m["receivables"] is not None)
        if m["receivables"] is not None:
            self.kpi_debt.set_value(format_money(m["receivables"]))

    @staticmethod
    def _compare(pct, yesterday_total: int) -> str:
        if pct is None:
            return ar.DASH_NO_YESTERDAY if yesterday_total == 0 else ""
        arrow = "▲" if pct > 0 else ("▼" if pct < 0 else "=")
        return f"{arrow} {abs(pct)}% {ar.DASH_VS_YESTERDAY}"

    def _fill_charts(self, m: dict) -> None:
        has_sales = m["series"] is not None
        self.chart_card.setVisible(has_sales)
        self.top_card.setVisible(has_sales)
        if not has_sales:
            return
        any_sales = any(d["total"] for d in m["series"])
        self.chart.set_data(m["series"])
        self.chart.setVisible(any_sales)
        self.chart_empty.setVisible(not any_sales)
        self.top_table.set_rows([[p["name"], p["qty"], format_money(p["total"])] for p in m["top_products"]],
                                [Qt.AlignRight | Qt.AlignVCenter, Qt.AlignCenter, Qt.AlignCenter])

    def _fill_wallets(self, m: dict) -> None:
        while self.wallet_strip.count():
            w = self.wallet_strip.takeAt(0).widget()
            if w:
                w.deleteLater()
        wallets = m["wallets"]
        self.wallet_card.setVisible(wallets is not None)
        if not wallets:
            if wallets is not None:
                self.wallet_strip.addWidget(EmptyState(ar.DASH_NO_WALLETS, "wallet"))
            return
        for w in wallets:
            card = KpiCard(w["label"], format_money(w["balance"]), w["network"])
            self.wallet_strip.addWidget(card)
        self.wallet_strip.addStretch()

    def _fill_low_stock(self, m: dict) -> None:
        items = m["low_stock"]
        self.btn_reorder.setVisible(bool(items))
        self.low_table.set_rows([[i["name"], i["qty"], i["min_stock"], ""] for i in items],
                                [Qt.AlignRight | Qt.AlignVCenter, Qt.AlignCenter, Qt.AlignCenter, Qt.AlignCenter])
        for r, i in enumerate(items):
            b = icon_button("plus", ar.DASH_REORDER, "ghost")
            b.clicked.connect(self.open_purchases_requested.emit)
            self.low_table.setCellWidget(r, 3, b)
