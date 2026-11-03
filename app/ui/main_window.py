"""Main application window with modern RTL layout, navigation sidebar, header, and module views."""
from __future__ import annotations

import datetime
from typing import Optional

try:
    from PySide6.QtWidgets import (
        QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
        QPushButton, QStackedWidget, QStatusBar, QFrame,
    )
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QFont

    HAS_QT = True
except ImportError:
    HAS_QT = False

from app.i18n import ar
from app.core.database import get_session
from app.models.user import User
from app.ui.dashboard.dashboard_widget import DashboardWidget
from app.ui.inventory.inventory_window import InventoryWindow
from app.ui.pos.pos_window import POSWindow
from app.ui.pos.returns_window import ReturnsWindow
from app.ui.purchases.purchases_window import PurchasesWidget
from app.ui.wallets.wallets_window import WalletsWidget
from app.ui.accounting.accounting_window import AccountingWidget
from app.ui.customers.customers_window import CustomersWidget
from app.ui.reports.reports_window import ReportsWidget
from app.ui.settings.settings_window import SettingsWidget


if HAS_QT:
    class MainWindow(QMainWindow):
        def __init__(self, current_user: Optional[User] = None) -> None:
            super().__init__()
            self.session = get_session()

            if current_user is None:
                current_user = self.session.query(User).filter_by(username="admin").first()
            self.current_user = current_user

            self.setWindowTitle(f"{ar.APP_TITLE} - الإصدار 1.0")
            self.resize(1340, 860)
            self.setMinimumSize(1080, 720)
            self.setLayoutDirection(Qt.RightToLeft)

            self._build_ui()

        def _build_ui(self) -> None:
            root_widget = QWidget()
            root_layout = QVBoxLayout(root_widget)
            root_layout.setContentsMargins(0, 0, 0, 0)
            root_layout.setSpacing(0)

            # Top Header Bar
            header = QFrame()
            header.setObjectName("Header")
            header_layout = QHBoxLayout(header)
            header_layout.setContentsMargins(20, 10, 20, 10)

            # Left side (in RTL, visually right): Brand
            brand_box = QVBoxLayout()
            brand_box.setSpacing(1)
            title_label = QLabel(f"📱 {ar.APP_TITLE}")
            title_label.setObjectName("AppTitle")
            sub_label = QLabel("نظام متكامل للمبيعات، الأجهزة بالسيريال (IMEI)، والمحافظ الإلكترونية")
            sub_label.setObjectName("AppSubtitle")
            brand_box.addWidget(title_label)
            brand_box.addWidget(sub_label)
            header_layout.addLayout(brand_box)

            header_layout.addStretch()

            # Center/Right: Live Clock
            self.time_label = QLabel()
            self.time_label.setObjectName("HeaderClock")
            header_layout.addWidget(self.time_label)
            self._update_time()
            self.timer = QTimer(self)
            self.timer.timeout.connect(self._update_time)
            self.timer.start(1000)

            # User profile card
            user_box = QHBoxLayout()
            user_box.setSpacing(10)

            user_name = self.current_user.full_name if self.current_user else "مدير النظام"
            user_label = QLabel(f"👤 {user_name}")
            user_label.setObjectName("UserPill")

            role_name = self.current_user.role.name if (self.current_user and self.current_user.role) else "manager"
            role_display = {"manager": "مدير النظام", "cashier": "كاشير", "wallet_employee": "موظف محافظ"}.get(role_name, role_name)
            role_badge = QLabel(role_display)
            role_badge.setObjectName("RolePill")

            user_box.addWidget(user_label)
            user_box.addWidget(role_badge)
            header_layout.addLayout(user_box)

            root_layout.addWidget(header)

            # Body: Sidebar (right in RTL) + Content Area
            body_layout = QHBoxLayout()
            body_layout.setContentsMargins(0, 0, 0, 0)
            body_layout.setSpacing(0)

            # Sidebar
            sidebar = QFrame()
            sidebar.setObjectName("Sidebar")
            sidebar_layout = QVBoxLayout(sidebar)
            sidebar_layout.setContentsMargins(8, 16, 8, 16)
            sidebar_layout.setSpacing(4)

            lbl_cat_ops = QLabel("العمليات والنشاط")
            lbl_cat_ops.setObjectName("SidebarCategory")
            sidebar_layout.addWidget(lbl_cat_ops)

            self.nav_buttons: list[QPushButton] = []

            self.nav_items = [
                ("📊  لوحة التحكم", self._show_dashboard),
                ("🛒  " + ar.POS + " (المبيعات)", self._show_pos),
                ("📦  " + ar.INVENTORY, self._show_inventory),
                ("↩️  الضمان والمرتجعات", self._show_returns),
                ("📥  " + ar.PURCHASES + " والموردين", self._show_purchases),
                ("💳  " + ar.WALLETS + " والشحن", self._show_wallets),
                ("💰  " + ar.ACCOUNTING + " والورديات", self._show_accounting),
                ("👥  " + ar.CUSTOMERS + " والديون", self._show_customers),
            ]

            for label, slot in self.nav_items:
                btn = QPushButton(label)
                btn.setProperty("class", "NavBtn")
                btn.clicked.connect(slot)
                sidebar_layout.addWidget(btn)
                self.nav_buttons.append(btn)

            sidebar_layout.addSpacing(16)
            lbl_cat_sys = QLabel("الإدارة والتقارير")
            lbl_cat_sys.setObjectName("SidebarCategory")
            sidebar_layout.addWidget(lbl_cat_sys)

            self.sys_nav_items = [
                ("📈  " + ar.REPORTS + " والأرباح", self._show_reports),
                ("⚙️  " + ar.SETTINGS + " والنسخ الاحتياطي", self._show_settings),
            ]

            for label, slot in self.sys_nav_items:
                btn = QPushButton(label)
                btn.setProperty("class", "NavBtn")
                btn.clicked.connect(slot)
                sidebar_layout.addWidget(btn)
                self.nav_buttons.append(btn)

            sidebar_layout.addStretch()

            # Drawer / Shift quick status box at sidebar bottom
            drawer_card = QFrame()
            drawer_card.setStyleSheet(
                "background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 10px; margin: 6px;"
            )
            d_layout = QVBoxLayout(drawer_card)
            d_layout.setContentsMargins(6, 6, 6, 6)
            d_layout.setSpacing(4)
            d_title = QLabel("💵 حالة الوردية")
            d_title.setStyleSheet("font-weight: bold; font-size: 11px; color: #475569;")
            d_val = QLabel("الدرج مفتوح - جاهز")
            d_val.setStyleSheet("font-size: 12px; font-weight: bold; color: #059669;")
            d_layout.addWidget(d_title)
            d_layout.addWidget(d_val)
            sidebar_layout.addWidget(drawer_card)

            body_layout.addWidget(sidebar)

            # Main Content Stack
            self.stack = QStackedWidget()
            self.stack.setContentsMargins(12, 12, 12, 12)

            # 0. Dashboard View (Phase 7)
            self.dashboard_view = DashboardWidget(self.session, self.current_user)
            self.dashboard_view.open_pos_requested.connect(self._show_pos)
            self.dashboard_view.open_inventory_requested.connect(self._show_inventory)
            self.dashboard_view.open_purchases_requested.connect(self._show_purchases)
            self.dashboard_view.open_wallets_requested.connect(self._show_wallets)
            self.dashboard_view.open_accounting_requested.connect(self._show_accounting)
            self.dashboard_view.open_customers_requested.connect(self._show_customers)
            self.dashboard_view.open_reports_requested.connect(self._show_reports)
            self.stack.addWidget(self.dashboard_view)

            # 1. POS View (Phase 3)
            self.pos_view = POSWindow(self.session, self.current_user)
            self.stack.addWidget(self.pos_view)

            # 2. Inventory View (Phase 2)
            self.inventory_view = InventoryWindow(self.session, self.current_user)
            self.stack.addWidget(self.inventory_view)

            # 3. Returns & Warranty View (Phase 3)
            self.returns_view = ReturnsWindow(self.session, self.current_user)
            self.stack.addWidget(self.returns_view)

            # 4. Purchases & Suppliers View (Phase 4)
            self.purchases_view = PurchasesWidget(self.session, self.current_user)
            self.stack.addWidget(self.purchases_view)

            # 5. Wallets & Operations View (Phase 5)
            self.wallets_view = WalletsWidget(self.session, self.current_user)
            self.stack.addWidget(self.wallets_view)

            # 6. Accounting & Cash Accounts View (Phase 6)
            self.accounting_view = AccountingWidget(self.session, self.current_user)
            self.stack.addWidget(self.accounting_view)

            # 7. Customers & Debts View (Phase 7)
            self.customers_view = CustomersWidget(self.session, self.current_user)
            self.stack.addWidget(self.customers_view)

            # 8. Reports & P&L View (Phase 7)
            self.reports_view = ReportsWidget(self.session, self.current_user)
            self.stack.addWidget(self.reports_view)

            # 9. Settings & Backup View (Phase 7)
            self.settings_view = SettingsWidget(self.session, self.current_user)
            self.stack.addWidget(self.settings_view)

            body_layout.addWidget(self.stack, 1)
            root_layout.addLayout(body_layout)

            self.setCentralWidget(root_widget)

            # Status bar
            status = QStatusBar()
            self.setStatusBar(status)
            status.showMessage("🟢 النظام يعمل بدون إنترنت (Offline Mode) - قاعدة البيانات SQLite مؤمنة بوضع WAL")

            # Show Dashboard by default
            self._show_dashboard()

        def _update_time(self):
            now = datetime.datetime.now()
            self.time_label.setText(now.strftime("%Y-%m-%d   %I:%M:%S %p"))

        def _set_active_nav(self, active_index: int):
            for i, btn in enumerate(self.nav_buttons):
                if i == active_index:
                    btn.setStyleSheet(
                        "background-color: #EFF6FF; color: #2563EB; font-weight: 700; border-right: 4px solid #2563EB;"
                    )
                else:
                    btn.setStyleSheet(
                        "background-color: transparent; color: #475569; font-weight: 600; border-right: none;"
                    )

        def _show_dashboard(self):
            self._set_active_nav(0)
            self.dashboard_view.refresh_data()
            self.stack.setCurrentWidget(self.dashboard_view)

        def _show_pos(self):
            self._set_active_nav(1)
            self.pos_view._check_shift_and_init_sale()
            self.stack.setCurrentWidget(self.pos_view)

        def _show_inventory(self):
            self._set_active_nav(2)
            self.inventory_view.refresh()
            self.stack.setCurrentWidget(self.inventory_view)

        def _show_returns(self):
            self._set_active_nav(3)
            self.stack.setCurrentWidget(self.returns_view)

        def _show_purchases(self):
            self._set_active_nav(4)
            self.purchases_view.load_all()
            self.stack.setCurrentWidget(self.purchases_view)

        def _show_wallets(self):
            self._set_active_nav(5)
            self.wallets_view.load_all()
            self.stack.setCurrentWidget(self.wallets_view)

        def _show_accounting(self):
            self._set_active_nav(6)
            self.accounting_view.load_all()
            self.stack.setCurrentWidget(self.accounting_view)

        def _show_customers(self):
            self._set_active_nav(7)
            self.customers_view.load_customers()
            self.stack.setCurrentWidget(self.customers_view)

        def _show_reports(self):
            self._set_active_nav(8)
            self.reports_view.run_report()
            self.stack.setCurrentWidget(self.reports_view)

        def _show_settings(self):
            self._set_active_nav(9)
            self.settings_view.load_backups()
            self.stack.setCurrentWidget(self.settings_view)

        def closeEvent(self, event):
            if hasattr(self, "session") and self.session:
                self.session.close()
            event.accept()

else:
    class MainWindow:  # type: ignore[no-redef]
        def __init__(self, current_user=None):
            pass
        def show(self) -> None:
            pass
