"""Main application window with RTL layout, navigation sidebar, header, and module views."""
from __future__ import annotations

import datetime
from typing import Optional

try:
    from PySide6.QtWidgets import (
        QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
        QPushButton, QStackedWidget, QStatusBar, QFrame, QMessageBox,
    )
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QFont, QIcon, QColor

    HAS_QT = True
except ImportError:
    HAS_QT = False

from app.i18n import ar
from app.core.database import get_session
from app.models.user import User
from app.ui.inventory.inventory_window import InventoryWindow


STYLESHEET = """
QMainWindow {
    background-color: #F8FAFC;
}
QWidget {
    font-family: "Tajawal", "Segoe UI", "Tahoma", sans-serif;
    font-size: 13px;
    color: #1E293B;
}
QFrame#Header {
    background-color: #0F172A;
    border-bottom: 2px solid #38BDF8;
    padding: 10px 20px;
}
QLabel#AppTitle {
    color: #FFFFFF;
    font-size: 18px;
    font-weight: bold;
}
QLabel#UserInfo {
    color: #94A3B8;
    font-size: 13px;
}
QLabel#RoleBadge {
    background-color: #0284C7;
    color: #FFFFFF;
    font-weight: bold;
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 12px;
}
QFrame#Sidebar {
    background-color: #FFFFFF;
    border-left: 1px solid #E2E8F0;
    min-width: 220px;
    max-width: 220px;
}
QPushButton.NavBtn {
    text-align: right;
    padding: 12px 16px;
    border: none;
    border-radius: 8px;
    margin: 3px 8px;
    font-size: 14px;
    font-weight: 500;
    background-color: transparent;
    color: #475569;
}
QPushButton.NavBtn:hover {
    background-color: #F1F5F9;
    color: #0284C7;
}
QPushButton.NavBtnActive {
    background-color: #E0F2FE;
    color: #0369A1;
    font-weight: bold;
    border-right: 4px solid #0284C7;
}
QTableWidget {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    gridline-color: #F1F5F9;
}
QHeaderView::section {
    background-color: #F1F5F9;
    color: #334155;
    font-weight: bold;
    padding: 8px;
    border: none;
    border-bottom: 1px solid #CBD5E1;
}
QPushButton {
    background-color: #0284C7;
    color: #FFFFFF;
    font-weight: bold;
    border-radius: 6px;
    padding: 7px 16px;
    border: none;
}
QPushButton:hover {
    background-color: #0369A1;
}
QPushButton:pressed {
    background-color: #075985;
}
QLineEdit, QSpinBox, QComboBox {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 6px 10px;
    color: #0F172A;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border: 2px solid #0284C7;
}
QTabWidget::pane {
    border: 1px solid #CBD5E1;
    background-color: #FFFFFF;
    border-radius: 6px;
}
QTabBar::tab {
    background: #E2E8F0;
    color: #475569;
    padding: 10px 24px;
    margin-left: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: bold;
}
QTabBar::tab:selected {
    background: #FFFFFF;
    color: #0284C7;
    border-bottom: 2px solid #0284C7;
}
"""


if HAS_QT:
    class MainWindow(QMainWindow):
        def __init__(self, current_user: Optional[User] = None) -> None:
            super().__init__()
            self.session = get_session()

            # Ensure we have a valid logged in user (default admin if none provided)
            if current_user is None:
                current_user = self.session.query(User).filter_by(username="admin").first()
            self.current_user = current_user

            self.setWindowTitle(ar.APP_TITLE)
            self.resize(1280, 850)
            self.setMinimumSize(1024, 700)
            self.setLayoutDirection(Qt.RightToLeft)
            self.setStyleSheet(STYLESHEET)

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
            header_layout.setContentsMargins(16, 8, 16, 8)

            title_label = QLabel(f"📱 {ar.APP_TITLE}")
            title_label.setObjectName("AppTitle")
            header_layout.addWidget(title_label)

            header_layout.addStretch()

            # Current date & time
            self.time_label = QLabel()
            self.time_label.setStyleSheet("color: #94A3B8; font-size: 13px; font-weight: bold;")
            header_layout.addWidget(self.time_label)
            self._update_time()
            self.timer = QTimer(self)
            self.timer.timeout.connect(self._update_time)
            self.timer.start(1000)

            # User pill
            user_box = QHBoxLayout()
            user_box.setSpacing(8)

            user_name = self.current_user.full_name if self.current_user else "مدير النظام"
            user_label = QLabel(f"👤 {user_name}")
            user_label.setObjectName("UserInfo")

            role_name = self.current_user.role.name if (self.current_user and self.current_user.role) else "manager"
            role_display = {"manager": "مدير النظام", "cashier": "كاشير", "wallet_employee": "موظف محافظ"}.get(role_name, role_name)
            role_badge = QLabel(role_display)
            role_badge.setObjectName("RoleBadge")

            user_box.addWidget(user_label)
            user_box.addWidget(role_badge)
            header_layout.addLayout(user_box)

            root_layout.addWidget(header)

            # Body: Sidebar (right in RTL) + Content Stack (left in RTL)
            body_layout = QHBoxLayout()
            body_layout.setContentsMargins(0, 0, 0, 0)
            body_layout.setSpacing(0)

            # Sidebar
            sidebar = QFrame()
            sidebar.setObjectName("Sidebar")
            sidebar_layout = QVBoxLayout(sidebar)
            sidebar_layout.setContentsMargins(8, 16, 8, 16)
            sidebar_layout.setSpacing(4)

            self.nav_buttons: list[QPushButton] = []

            # Navigation items
            self.nav_items = [
                ("📦 " + ar.INVENTORY, self._show_inventory, True),
                ("🛒 " + ar.POS + " (المبيعات)", self._show_pos_placeholder, False),
                ("📥 " + ar.PURCHASES, self._show_purchases_placeholder, False),
                ("💳 " + ar.WALLETS, self._show_wallets_placeholder, False),
                ("💰 " + ar.ACCOUNTING, self._show_accounting_placeholder, False),
                ("👥 " + ar.CUSTOMERS, self._show_customers_placeholder, False),
                ("📊 " + ar.REPORTS, self._show_reports_placeholder, False),
                ("⚙️ " + ar.SETTINGS, self._show_settings_placeholder, False),
            ]

            for label, slot, is_active in self.nav_items:
                btn = QPushButton(label)
                btn.setProperty("class", "NavBtn")
                btn.clicked.connect(slot)
                sidebar_layout.addWidget(btn)
                self.nav_buttons.append(btn)

            sidebar_layout.addStretch()

            system_info = QLabel("الإصدار 1.0 (MVP)\nقاعدة بيانات غير متصلة (Offline)")
            system_info.setStyleSheet("color: #94A3B8; font-size: 11px; padding: 8px;")
            system_info.setAlignment(Qt.AlignCenter)
            sidebar_layout.addWidget(system_info)

            body_layout.addWidget(sidebar)

            # Main Content Stack
            self.stack = QStackedWidget()
            self.stack.setContentsMargins(16, 16, 16, 16)

            # 1. Inventory View (Phase 2)
            self.inventory_view = InventoryWindow(self.session, self.current_user)
            self.stack.addWidget(self.inventory_view)

            # 2. Placeholders for upcoming phases
            self.placeholder_view = QWidget()
            pl_layout = QVBoxLayout(self.placeholder_view)
            pl_layout.setAlignment(Qt.AlignCenter)
            self.placeholder_label = QLabel()
            self.placeholder_label.setStyleSheet("font-size: 18px; color: #64748B; font-weight: bold;")
            self.placeholder_label.setAlignment(Qt.AlignCenter)
            pl_layout.addWidget(self.placeholder_label)
            self.stack.addWidget(self.placeholder_view)

            body_layout.addWidget(self.stack, 1)
            root_layout.addLayout(body_layout)

            self.setCentralWidget(root_widget)

            # Status bar
            status = QStatusBar()
            self.setStatusBar(status)
            status.showMessage("جاهز للعمل - قاعدة البيانات متصلة بنجاح")

            # Activate inventory by default
            self._set_active_nav(0)

        def _update_time(self):
            now = datetime.datetime.now()
            self.time_label.setText(now.strftime("%Y-%m-%d  %I:%M:%S %p"))

        def _set_active_nav(self, active_index: int):
            for i, btn in enumerate(self.nav_buttons):
                if i == active_index:
                    btn.setStyleSheet(
                        "background-color: #E0F2FE; color: #0369A1; font-weight: bold; border-right: 4px solid #0284C7;"
                    )
                else:
                    btn.setStyleSheet(
                        "background-color: transparent; color: #475569; font-weight: 500; border-right: none;"
                    )

        def _show_inventory(self):
            self._set_active_nav(0)
            self.inventory_view.refresh()
            self.stack.setCurrentWidget(self.inventory_view)

        def _show_pos_placeholder(self):
            self._set_active_nav(1)
            self.placeholder_label.setText("شاشة نقطة البيع (POS) - قيد البناء في المرحلة 3 (Phase 3)")
            self.stack.setCurrentWidget(self.placeholder_view)

        def _show_purchases_placeholder(self):
            self._set_active_nav(2)
            self.placeholder_label.setText("شاشة المشتريات وتوريد الأجهزة - قيد البناء في المرحلة 4 (Phase 4)")
            self.stack.setCurrentWidget(self.placeholder_view)

        def _show_wallets_placeholder(self):
            self._set_active_nav(3)
            self.placeholder_label.setText("شاشة المحافظ الإلكترونية وكروت الشحن - قيد البناء في المرحلة 5 (Phase 5)")
            self.stack.setCurrentWidget(self.placeholder_view)

        def _show_accounting_placeholder(self):
            self._set_active_nav(4)
            self.placeholder_label.setText("شاشة المحاسبة وحركة الخزينة والورديات - قيد البناء في المرحلة 6 (Phase 6)")
            self.stack.setCurrentWidget(self.placeholder_view)

        def _show_customers_placeholder(self):
            self._set_active_nav(5)
            self.placeholder_label.setText("شاشة إدارة حسابات العملاء والديون - قيد البناء في المرحلة 3 (Phase 3)")
            self.stack.setCurrentWidget(self.placeholder_view)

        def _show_reports_placeholder(self):
            self._set_active_nav(6)
            self.placeholder_label.setText("شاشة التقارير والأرباح - قيد البناء في المرحلة 7 (Phase 7)")
            self.stack.setCurrentWidget(self.placeholder_view)

        def _show_settings_placeholder(self):
            self._set_active_nav(7)
            self.placeholder_label.setText("شاشة إعدادات النظام والمستخدمين والنسخ الاحتياطي - قيد البناء في المرحلة 7 (Phase 7)")
            self.stack.setCurrentWidget(self.placeholder_view)

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
