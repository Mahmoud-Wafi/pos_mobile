"""Dashboard view with high-level KPI cards, quick shortcuts, and real-time operational feeds."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QGridLayout, QScrollArea,
)

from app.core.money import format_money
from app.services import report_service


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
        self.session = session
        self.user = user
        self._build_ui()
        self.refresh_data()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(16)

        # ── Top Bar ─────────────────────────────────────────
        top_bar = QHBoxLayout()
        top_bar.setSpacing(12)

        lbl_title = QLabel("📊 لوحة المؤشرات ونظرة عامة على النشاط")
        lbl_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #0F172A;")
        top_bar.addWidget(lbl_title)

        top_bar.addStretch()

        self.lbl_date = QLabel()
        self.lbl_date.setStyleSheet("font-size: 13px; color: #64748B; font-weight: 600;")
        top_bar.addWidget(self.lbl_date)

        btn_refresh = QPushButton("🔄 تحديث البيانات")
        btn_refresh.setFixedHeight(36)
        btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 0 14px;
                font-weight: 600;
                color: #334155;
            }
            QPushButton:hover {
                background-color: #F8FAFC;
                border-color: #94A3B8;
            }
        """)
        btn_refresh.clicked.connect(self.refresh_data)
        top_bar.addWidget(btn_refresh)

        main_layout.addLayout(top_bar)

        # ── KPI Cards Grid ──────────────────────────────────
        kpi_grid = QGridLayout()
        kpi_grid.setSpacing(14)

        # 1. Today's Sales
        self.card_sales, self.lbl_sales_val, self.lbl_sales_sub = self._create_card(
            "🛒 مبيعات اليوم", "0.00 ج.م", "0 فواتير مسجلة", "#2563EB", "#EFF6FF"
        )
        kpi_grid.addWidget(self.card_sales, 0, 0)

        # 2. Today's Profit
        self.card_profit, self.lbl_profit_val, self.lbl_profit_sub = self._create_card(
            "📈 صافي أرباح اليوم", "0.00 ج.م", "المبيعات + المحافظ", "#059669", "#ECFDF5"
        )
        kpi_grid.addWidget(self.card_profit, 0, 1)

        # 3. Cash Drawer Balance
        self.card_drawer, self.lbl_drawer_val, self.lbl_drawer_sub = self._create_card(
            "💵 رصيد درج النقدية", "0.00 ج.م", "الخزينة المباشرة للكاشير", "#D97706", "#FFFBEB"
        )
        kpi_grid.addWidget(self.card_drawer, 0, 2)

        # 4. Total Wallets Balance
        self.card_wallets, self.lbl_wallets_val, self.lbl_wallets_sub = self._create_card(
            "💳 إجمالي أرصدة المحافظ", "0.00 ج.م", "فودافون كاش والأجهزة", "#0284C7", "#F0F9FF"
        )
        kpi_grid.addWidget(self.card_wallets, 1, 0)

        # 5. Low Stock Alert
        self.card_stock, self.lbl_stock_val, self.lbl_stock_sub = self._create_card(
            "⚠️ نواقص المخزون", "0 صنف", "أصناف بلغت الحد الأدنى", "#DC2626", "#FEF2F2"
        )
        kpi_grid.addWidget(self.card_stock, 1, 1)

        # 6. Active Shift Info
        self.card_shift, self.lbl_shift_val, self.lbl_shift_sub = self._create_card(
            "🕒 الوردية الحالية", "مفتوحة", "الكاشير: —", "#7C3AED", "#F5F3FF"
        )
        kpi_grid.addWidget(self.card_shift, 1, 2)

        main_layout.addLayout(kpi_grid)

        # ── Quick Action Shortcuts ──────────────────────────
        shortcut_frame = QFrame()
        shortcut_frame.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 10px;
                padding: 10px;
            }
        """)
        sc_layout = QHBoxLayout(shortcut_frame)
        sc_layout.setSpacing(10)

        sc_title = QLabel("⚡ وصول سريع:")
        sc_title.setStyleSheet("font-weight: bold; color: #475569; font-size: 13px;")
        sc_layout.addWidget(sc_title)

        shortcuts = [
            ("🛒 نقطة البيع (POS)", "#2563EB", self.open_pos_requested.emit),
            ("💳 عمليات المحافظ", "#0284C7", self.open_wallets_requested.emit),
            ("📥 فاتورة مشتريات", "#059669", self.open_purchases_requested.emit),
            ("💰 الخزينة والمصروفات", "#D97706", self.open_accounting_requested.emit),
            ("👥 حسابات العملاء", "#4F46E5", self.open_customers_requested.emit),
            ("📦 إدارة المخزون", "#0D9488", self.open_inventory_requested.emit),
            ("📊 التقارير الشاملة", "#475569", self.open_reports_requested.emit),
        ]

        for text, color, slot in shortcuts:
            btn = QPushButton(text)
            btn.setFixedHeight(34)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #F8FAFC;
                    border: 1px solid #E2E8F0;
                    border-radius: 6px;
                    padding: 0 12px;
                    font-size: 12px;
                    font-weight: bold;
                    color: {color};
                }}
                QPushButton:hover {{
                    background-color: #EFF6FF;
                    border-color: {color};
                }}
            """)
            btn.clicked.connect(slot)
            sc_layout.addWidget(btn)

        sc_layout.addStretch()
        main_layout.addWidget(shortcut_frame)

        # ── Feeds Split (Recent Sales + Low Stock Alerts) ───
        feeds_layout = QHBoxLayout()
        feeds_layout.setSpacing(14)

        # Right Feed: Recent Sales
        recent_box = QFrame()
        recent_box.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 12px;")
        recent_layout = QVBoxLayout(recent_box)
        recent_layout.setSpacing(10)

        r_title = QLabel("🛒 أحدث مبيعات اليوم")
        r_title.setStyleSheet("font-weight: bold; font-size: 14px; color: #0F172A;")
        recent_layout.addWidget(r_title)

        self.recent_table = QTableWidget()
        self.recent_table.setColumnCount(4)
        self.recent_table.setHorizontalHeaderLabels(["رقم الفاتورة", "العميل", "الإجمالي", "الوقت"])
        self.recent_table.verticalHeader().setVisible(False)
        self.recent_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.recent_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.recent_table.setAlternatingRowColors(True)
        rh = self.recent_table.horizontalHeader()
        rh.setSectionResizeMode(0, QHeaderView.Fixed); self.recent_table.setColumnWidth(0, 110)
        rh.setSectionResizeMode(1, QHeaderView.Stretch)
        rh.setSectionResizeMode(2, QHeaderView.Fixed); self.recent_table.setColumnWidth(2, 100)
        rh.setSectionResizeMode(3, QHeaderView.Fixed); self.recent_table.setColumnWidth(3, 90)
        recent_layout.addWidget(self.recent_table)

        feeds_layout.addWidget(recent_box, 1)

        # Left Feed: Low Stock Alerts
        stock_box = QFrame()
        stock_box.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 12px;")
        stock_layout = QVBoxLayout(stock_box)
        stock_layout.setSpacing(10)

        s_title = QLabel("⚠️ تنبيهات النواقص بالمخزون")
        s_title.setStyleSheet("font-weight: bold; font-size: 14px; color: #B91C1C;")
        stock_layout.addWidget(s_title)

        self.stock_table = QTableWidget()
        self.stock_table.setColumnCount(4)
        self.stock_table.setHorizontalHeaderLabels(["اسم الصنف", "النوع", "الكمية الحالية", "الحد الأدنى"])
        self.stock_table.verticalHeader().setVisible(False)
        self.stock_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.stock_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.stock_table.setAlternatingRowColors(True)
        sh = self.stock_table.horizontalHeader()
        sh.setSectionResizeMode(0, QHeaderView.Stretch)
        sh.setSectionResizeMode(1, QHeaderView.Fixed); self.stock_table.setColumnWidth(1, 80)
        sh.setSectionResizeMode(2, QHeaderView.Fixed); self.stock_table.setColumnWidth(2, 90)
        sh.setSectionResizeMode(3, QHeaderView.Fixed); self.stock_table.setColumnWidth(3, 90)
        stock_layout.addWidget(self.stock_table)

        feeds_layout.addWidget(stock_box, 1)

        main_layout.addLayout(feeds_layout, 1)

    def _create_card(self, title: str, init_val: str, subtitle: str, color: str, bg_tint: str):
        card = QFrame()
        card.setFixedHeight(105)
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_tint};
                border: 1px solid #E2E8F0;
                border-radius: 10px;
                padding: 10px 14px;
            }}
        """)
        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(6, 6, 6, 6)
        vbox.setSpacing(3)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {color};")
        vbox.addWidget(lbl_title)

        lbl_val = QLabel(init_val)
        lbl_val.setStyleSheet(f"font-size: 19px; font-weight: bold; color: #0F172A;")
        vbox.addWidget(lbl_val)

        lbl_sub = QLabel(subtitle)
        lbl_sub.setStyleSheet("font-size: 11px; color: #64748B;")
        vbox.addWidget(lbl_sub)

        return card, lbl_val, lbl_sub

    def refresh_data(self):
        try:
            metrics = report_service.dashboard_metrics(self.session, self.user)
            self.lbl_date.setText(f"تاريخ اليوم: {metrics['today_str']}")

            # Sales
            self.lbl_sales_val.setText(format_money(metrics["sales_total"]))
            self.lbl_sales_sub.setText(f"{metrics['sales_count']} فاتورة بيع مسجلة اليوم")

            # Profit
            if metrics["sales_profit"] is not None:
                tot_p = metrics["sales_profit"] + (metrics["wallet_profit"] or 0)
                self.lbl_profit_val.setText(format_money(tot_p))
                self.lbl_profit_sub.setText(f"مبيعات: {format_money(metrics['sales_profit'])}")
            else:
                self.lbl_profit_val.setText("— — —")
                self.lbl_profit_sub.setText("غير مصرح بعرض الأرباح")

            # Cash Drawer
            self.lbl_drawer_val.setText(format_money(metrics["drawer_balance"]))
            self.lbl_drawer_sub.setText(f"رصيد الخزينة: {format_money(metrics['safe_balance'])}")

            # Wallets
            self.lbl_wallets_val.setText(format_money(metrics["total_wallets_balance"]))
            self.lbl_wallets_sub.setText(f"{metrics['wallet_count']} عملية محفظة مسجلة اليوم")

            # Low Stock
            lsc = metrics["low_stock_count"]
            self.lbl_stock_val.setText(f"{lsc} أصناف" if lsc > 0 else "المخزون كافٍ")
            if lsc > 0:
                self.card_stock.setStyleSheet("background-color: #FEF2F2; border: 1px solid #FCA5A5; border-radius: 10px; padding: 10px 14px;")
            else:
                self.card_stock.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 10px; padding: 10px 14px;")

            # Shift
            shift_info = metrics["active_shift"]
            if shift_info["is_open"]:
                self.lbl_shift_val.setText(f"وردية #{shift_info['id']} (نشطة)")
                self.lbl_shift_sub.setText(f"الكاشير: {shift_info['user_name']} | بدأت {shift_info['opened_at']}")
                self.card_shift.setStyleSheet("background-color: #ECFDF5; border: 1px solid #A7F3D0; border-radius: 10px; padding: 10px 14px;")
            else:
                self.lbl_shift_val.setText("الوردية مغلقة")
                self.lbl_shift_sub.setText("لا توجد وردية مفتوحة حالياً")
                self.card_shift.setStyleSheet("background-color: #FFF1F2; border: 1px solid #FECDD3; border-radius: 10px; padding: 10px 14px;")

            # Populate Recent Sales Table
            self.recent_table.setRowCount(len(metrics["recent_sales"]))
            for r, s in enumerate(metrics["recent_sales"]):
                self.recent_table.setItem(r, 0, QTableWidgetItem(s["invoice_no"]))
                self.recent_table.setItem(r, 1, QTableWidgetItem(s["customer_name"]))
                self.recent_table.setItem(r, 2, QTableWidgetItem(format_money(s["total"])))
                self.recent_table.setItem(r, 3, QTableWidgetItem(s["time"]))

            # Populate Low Stock Table
            self.stock_table.setRowCount(len(metrics["low_stock_items"]))
            type_ar = {"phone": "هاتف", "accessory": "إكسسوار", "spare_part": "قطع غيار", "card": "كارت"}
            for r, itm in enumerate(metrics["low_stock_items"]):
                self.stock_table.setItem(r, 0, QTableWidgetItem(itm["name"]))
                self.stock_table.setItem(r, 1, QTableWidgetItem(type_ar.get(itm["type"], itm["type"])))
                
                qty_item = QTableWidgetItem(str(itm["qty"]))
                qty_item.setForeground(Qt.red)
                qty_item.setTextAlignment(Qt.AlignCenter)
                self.stock_table.setItem(r, 2, qty_item)

                min_item = QTableWidgetItem(str(itm["min_stock"]))
                min_item.setTextAlignment(Qt.AlignCenter)
                self.stock_table.setItem(r, 3, min_item)

        except Exception as e:
            pass

