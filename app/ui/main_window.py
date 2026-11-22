"""Main application window with modern RTL layout, navigation sidebar, header, and module views."""
from __future__ import annotations

import datetime
import logging
from typing import Optional

try:
    from PySide6.QtWidgets import (
        QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
        QPushButton, QStackedWidget, QStatusBar, QFrame, QMenu, QMessageBox,
    )
    from PySide6.QtCore import QSettings, QSize, Qt, QTimer, Signal
    from PySide6.QtGui import QFont, QKeySequence, QShortcut

    HAS_QT = True
except ImportError:
    HAS_QT = False

from app.ui.components import show_error
from app.config import APP_VERSION, DATA_DIR
from app.core import clock
from app.i18n import ar
from app.ui.design import icons
from app.ui.design.tokens import COLORS as C
from app.ui.access import can_open
from app.core.database import get_session
from app.models.user import User
from app.ui.dashboard.dashboard_widget import DashboardWidget
from app.ui.inventory.inventory_window import InventoryWindow
from app.ui.pos.pos_window import POSWindow
from app.ui.pos.returns_window import ReturnsWindow
from app.ui.repairs.repairs_window import RepairsWidget
from app.ui.invoices.history_view import InvoiceHistoryWidget
from app.ui.purchases.purchases_window import PurchasesWidget
from app.ui.wallets.wallets_window import WalletsWidget
from app.ui.accounting.accounting_window import AccountingWidget
from app.ui.customers.customers_window import CustomersWidget
from app.ui.reports.reports_window import ReportsWidget
from app.ui.settings.settings_window import SettingsWidget
from app.ui.design.style import set_prop, style_label, variant

log = logging.getLogger(__name__)


NAV_ICONS = {
    "dashboard": "layout-dashboard", "pos": "shopping-cart", "invoices": "receipt", "inventory": "package",
    "returns": "undo-2", "repairs": "wrench", "purchases": "truck", "wallets": "wallet", "accounting": "landmark",
    "customers": "users", "reports": "chart-column", "settings": "settings",
}

if HAS_QT:
    class MainWindow(QMainWindow):
        logout_requested = Signal()
        lock_requested = Signal()
        closed_by_user = Signal()

        def __init__(self, user_id: Optional[int] = None, current_user: Optional[User] = None) -> None:
            super().__init__()
            self.session = get_session()
            self._closing_for_logout = False

            if user_id is None and current_user is not None:
                user_id = current_user.id
            if user_id is None:
                raise ValueError("MainWindow requires an authenticated user")
            self.user_id = user_id
            self.current_user = self.session.get(User, user_id)
            self.perms = self.current_user.permission_codes()

            self.setWindowTitle(f"{ar.APP_TITLE} - الإصدار 1.0")
            self.setMinimumSize(1024, 680)
            self._restore_geometry()
            self.setLayoutDirection(Qt.RightToLeft)

            self._build_ui()

        def _build_ui(self) -> None:
            root_widget = QWidget()
            root_layout = QVBoxLayout(root_widget)
            root_layout.setContentsMargins(0, 0, 0, 0)
            root_layout.setSpacing(0)

            # Top Header Bar: brand, shift pill, clock, user menu
            header = QFrame()
            header.setObjectName("Header")
            header_layout = QHBoxLayout(header)
            header_layout.setContentsMargins(20, 10, 20, 10)

            logo = QLabel()
            logo.setPixmap(icons.pixmap("smartphone", C["text_inverse"], 28))
            header_layout.addWidget(logo)
            brand_box = QVBoxLayout()
            brand_box.setSpacing(1)
            self.title_label = QLabel(self._shop_name())
            self.title_label.setObjectName("AppTitle")
            sub_label = QLabel(ar.APP_SUBTITLE)
            sub_label.setObjectName("AppSubtitle")
            brand_box.addWidget(self.title_label)
            brand_box.addWidget(sub_label)
            header_layout.addLayout(brand_box)

            header_layout.addStretch()

            self.shift_val = QLabel("")
            self.shift_val.setObjectName("ShiftPill")
            header_layout.addWidget(self.shift_val)

            self.time_label = QLabel()
            self.time_label.setObjectName("HeaderClock")
            header_layout.addWidget(self.time_label)
            self._update_time()
            self.timer = QTimer(self)
            self.timer.timeout.connect(self._update_time)
            self.timer.start(1000)

            user_box = QHBoxLayout()
            user_box.setSpacing(10)
            user_name = self.current_user.full_name if self.current_user else ""
            user_label = QLabel(user_name)
            user_label.setObjectName("UserPill")
            role_name = self.current_user.role.name if (self.current_user and self.current_user.role) else "manager"
            role_display = {"manager": ar.MAIN_WINDOW_C2CDE4, "cashier": ar.ROLE_CASHIER, "wallet_employee": ar.ROLE_WALLET_EMPLOYEE}.get(role_name, role_name)
            role_badge = QLabel(role_display)
            role_badge.setObjectName("RolePill")
            user_box.addWidget(user_label)
            user_box.addWidget(role_badge)

            btn_menu = QPushButton()
            btn_menu.setProperty("no_icon", True)
            variant(btn_menu, "ghost")
            btn_menu.setIcon(icons.icon("chevron-down", C["header_text"]))
            btn_menu.setFixedSize(36, 36)
            btn_menu.setAccessibleName(ar.USER_MENU_CHANGE_PASSWORD + " / " + ar.LOCK_NOW + " / " + ar.LOGOUT)
            btn_menu.setToolTip(btn_menu.accessibleName())
            menu = QMenu(btn_menu)
            menu.addAction(icons.icon("key-round"), ar.USER_MENU_CHANGE_PASSWORD, self._open_change_password)
            menu.addAction(icons.icon("lock"), ar.LOCK_NOW, self.lock_requested.emit)
            menu.addSeparator()
            menu.addAction(icons.icon("log-out"), ar.LOGOUT, self._confirm_logout)
            btn_menu.setMenu(menu)
            user_box.addWidget(btn_menu)
            header_layout.addLayout(user_box)

            root_layout.addWidget(header)

            # Body: Sidebar (right in RTL) + Content Area
            body_layout = QHBoxLayout()
            body_layout.setContentsMargins(0, 0, 0, 0)
            body_layout.setSpacing(0)

            sidebar = QFrame()
            sidebar.setObjectName("Sidebar")
            self.sidebar = sidebar
            self._sidebar_labels: list[QLabel] = []
            self._compact = False
            sidebar_layout = QVBoxLayout(sidebar)
            sidebar_layout.setContentsMargins(8, 16, 8, 16)
            sidebar_layout.setSpacing(4)

            lbl_cat_ops = QLabel(ar.MAIN_WINDOW_3C30D2)
            lbl_cat_ops.setObjectName("SidebarCategory")
            sidebar_layout.addWidget(lbl_cat_ops)
            self._sidebar_labels.append(lbl_cat_ops)

            self.nav_buttons: list[QPushButton] = []

            self.nav_items = [
                ("dashboard", ar.NAV_DASHBOARD, self._show_dashboard),
                ("pos", ar.POS + ar.MAIN_WINDOW_2F364A, self._show_pos),
                ("invoices", ar.HISTORY, self._show_invoices),
                ("inventory", ar.INVENTORY, self._show_inventory),
                ("returns", ar.MAIN_WINDOW_C7F537, self._show_returns),
                ("repairs", ar.REPAIR_TITLE, self._show_repairs),
                ("purchases", ar.PURCHASES + ar.MAIN_WINDOW_F5E66B, self._show_purchases),
                ("wallets", ar.WALLETS + ar.MAIN_WINDOW_36CC36, self._show_wallets),
                ("accounting", ar.ACCOUNTING + ar.MAIN_WINDOW_30E574, self._show_accounting),
                ("customers", ar.CUSTOMERS + ar.MAIN_WINDOW_813FA0, self._show_customers),
            ]
            self.sys_nav_items = [
                ("reports", ar.REPORTS + ar.MAIN_WINDOW_A2B306, self._show_reports),
                ("settings", ar.SETTINGS + ar.MAIN_WINDOW_305E88, self._show_settings),
            ]
            self._nav_by_key: dict[str, QPushButton] = {}
            shortcut_no = 1
            for group, items in ((None, self.nav_items), (ar.NAV_ADMIN, self.sys_nav_items)):
                if group:
                    sidebar_layout.addSpacing(16)
                    lbl = QLabel(group)
                    lbl.setObjectName("SidebarCategory")
                    lbl.setVisible(can_open(self.perms, "reports") or can_open(self.perms, "settings"))
                    sidebar_layout.addWidget(lbl)
                    self._sidebar_labels.append(lbl)
                for key, label, slot in items:
                    visible = can_open(self.perms, key)
                    btn = QPushButton(label)
                    btn.setProperty("nav_text", label)
                    btn.setProperty("nav", True)
                    btn.setProperty("active", False)
                    btn.setIcon(icons.icon(NAV_ICONS[key], C["header_muted"]))
                    btn.setIconSize(QSize(20, 20))
                    btn.setCursor(Qt.PointingHandCursor)
                    btn.clicked.connect(slot)
                    btn.setVisible(visible)
                    if visible and shortcut_no <= 9:
                        btn.setToolTip(f"Ctrl+{shortcut_no}")
                        btn.setProperty("nav_tip", f"Ctrl+{shortcut_no}")
                        QShortcut(QKeySequence(f"Ctrl+{shortcut_no}"), self, slot)
                        shortcut_no += 1
                    sidebar_layout.addWidget(btn)
                    self.nav_buttons.append(btn)
                    self._nav_by_key[key] = btn

            sidebar_layout.addStretch()

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
            self.pos_view = POSWindow(self.session, self.current_user) if can_open(self.perms, "pos") else None
            if self.pos_view is not None:
                self.stack.addWidget(self.pos_view)
                self.pos_view.shift_changed.connect(self.refresh_shift_status)

            # 1b. Invoice history
            self.invoices_view = InvoiceHistoryWidget(self.session, self.current_user) if can_open(self.perms, "invoices") else None
            if self.invoices_view is not None:
                self.stack.addWidget(self.invoices_view)

            # 2. Inventory View (Phase 2)
            self.inventory_view = InventoryWindow(self.session, self.current_user) if can_open(self.perms, "inventory") else None
            if self.inventory_view is not None:
                self.stack.addWidget(self.inventory_view)

            # 3. Returns & Warranty View (Phase 3)
            self.returns_view = ReturnsWindow(self.session, self.current_user) if can_open(self.perms, "returns") else None
            if self.returns_view is not None:
                self.stack.addWidget(self.returns_view)

            self.repairs_view = RepairsWidget(self.session, self.current_user) if can_open(self.perms, "repairs") else None
            if self.repairs_view is not None:
                self.stack.addWidget(self.repairs_view)

            # 4. Purchases & Suppliers View (Phase 4)
            self.purchases_view = PurchasesWidget(self.session, self.current_user) if can_open(self.perms, "purchases") else None
            if self.purchases_view is not None:
                self.stack.addWidget(self.purchases_view)

            # 5. Wallets & Operations View (Phase 5)
            self.wallets_view = WalletsWidget(self.session, self.current_user) if can_open(self.perms, "wallets") else None
            if self.wallets_view is not None:
                self.stack.addWidget(self.wallets_view)

            # 6. Accounting & Cash Accounts View (Phase 6)
            self.accounting_view = AccountingWidget(self.session, self.current_user) if can_open(self.perms, "accounting") else None
            if self.accounting_view is not None:
                self.stack.addWidget(self.accounting_view)

            # 7. Customers & Debts View (Phase 7)
            self.customers_view = CustomersWidget(self.session, self.current_user) if can_open(self.perms, "customers") else None
            if self.customers_view is not None:
                self.stack.addWidget(self.customers_view)

            # 8. Reports & P&L View (Phase 7)
            self.reports_view = ReportsWidget(self.session, self.current_user) if can_open(self.perms, "reports") else None
            if self.reports_view is not None:
                self.stack.addWidget(self.reports_view)

            # 9. Settings & Backup View (Phase 7)
            self.settings_view = SettingsWidget(self.session, self.current_user) if can_open(self.perms, "settings") else None
            if self.settings_view is not None:
                self.stack.addWidget(self.settings_view)

            body_layout.addWidget(self.stack, 1)
            self.stack.currentChanged.connect(self._fresh_session)
            root_layout.addLayout(body_layout)

            self.setCentralWidget(root_widget)

            # Status bar: DB state, last backup, user, version
            status = QStatusBar()
            self.setStatusBar(status)
            self.sb_db, self.sb_backup, self.sb_user, self.sb_version = QLabel(), QLabel(), QLabel(), QLabel()
            for w in (self.sb_db, self.sb_backup, self.sb_user):
                status.addWidget(w, 1)
            status.addPermanentWidget(self.sb_version)

            # Show Dashboard by default
            self.refresh_shift_status()
            self._show_dashboard()

        def refresh_shift_status(self):
            from app.services import shift_service

            if not can_open(self.perms, "pos"):
                self.shift_val.setVisible(False)
                return
            st = shift_service.shift_status(self.session, self.current_user)
            if st["is_open"]:
                self.shift_val.setText(f"{ar.SHIFT_OPEN_STATUS} #{st['id']}")
                self.shift_val.setToolTip(str(st["opened_at"]))
                set_prop(self.shift_val, "state", "open")
            else:
                self.shift_val.setText(ar.SHIFT_CLOSED_STATUS)
                self.shift_val.setToolTip("")
                set_prop(self.shift_val, "state", "closed")
            self._refresh_status_bar()

        def _shop_name(self) -> str:
            try:
                from app.services import settings_service
                return settings_service.get_all(self.session).get("shop_name") or ar.APP_TITLE
            except Exception:
                return ar.APP_TITLE

        def _refresh_status_bar(self) -> None:
            from app.core.backup import last_backup_time

            try:
                when = last_backup_time()
                last = when.strftime("%Y-%m-%d %H:%M") if when else ar.NO_BACKUP_YET
            except Exception:
                last = ar.NO_BACKUP_YET
            self.sb_db.setText(ar.STATUS_DB_OK)
            from app.core.backup import offsite_status

            off = offsite_status()
            extra = ""
            if off is not None:
                extra = f"  |  {ar.OFFSITE_STATUS_LABEL}: " + (ar.OFFSITE_STATUS_OK if off[0] == "ok" else ar.OFFSITE_STATUS_FAIL)
            self.sb_backup.setText(f"{ar.STATUS_LAST_BACKUP}: {last}{extra}")
            self.sb_user.setText(f"{ar.STATUS_USER}: {self.current_user.full_name}")
            self.sb_version.setText(f"v{APP_VERSION}")

        def _fresh_session(self, _index: int = 0) -> None:
            """Refresh stale objects when the user changes screen.

            Never roll back here: the POS keeps a flushed-but-uncommitted draft invoice, and a rollback
            would detach it (DetachedInstanceError on the next scan). Screens roll back their own errors.
            """
            try:
                if not self.session.dirty:          # keep unsaved edits
                    self.session.expire_all()
            except Exception:  # noqa: BLE001 - never block navigation
                log.exception("session refresh failed")

        def _update_time(self):
            now = datetime.datetime.now()
            self.time_label.setText(now.strftime("%Y-%m-%d   %I:%M:%S %p"))

        def _set_active_nav(self, key: str):
            for k, btn in self._nav_by_key.items():
                set_prop(btn, "active", k == key)
                btn.setIcon(icons.icon(NAV_ICONS[k], C["text_inverse"] if k == key else C["header_muted"]))
            self.refresh_shift_status()

        def _show_dashboard(self):
            self._set_active_nav("dashboard")
            self.dashboard_view.refresh_data()
            self.stack.setCurrentWidget(self.dashboard_view)

        def _show_pos(self):
            if not self._allow("pos"):
                return
            self._set_active_nav("pos")
            self.pos_view._check_shift_and_init_sale()
            self.stack.setCurrentWidget(self.pos_view)

        def _show_invoices(self):
            if not self._allow("invoices"):
                return
            self._set_active_nav("invoices")
            self.invoices_view.refresh()
            self.stack.setCurrentWidget(self.invoices_view)

        def _show_inventory(self):
            if not self._allow("inventory"):
                return
            self._set_active_nav("inventory")
            self.inventory_view.refresh()
            self.stack.setCurrentWidget(self.inventory_view)

        def _show_returns(self):
            if not self._allow("returns"):
                return
            self._set_active_nav("returns")
            self.stack.setCurrentWidget(self.returns_view)

        def _show_repairs(self):
            if not self._allow("repairs"):
                return
            self._set_active_nav("repairs")
            self.repairs_view.reload()
            self.stack.setCurrentWidget(self.repairs_view)

        def _show_purchases(self):
            if not self._allow("purchases"):
                return
            self._set_active_nav("purchases")
            self.purchases_view.load_all()
            self.stack.setCurrentWidget(self.purchases_view)

        def _show_wallets(self):
            if not self._allow("wallets"):
                return
            self._set_active_nav("wallets")
            self.wallets_view.load_all()
            self.stack.setCurrentWidget(self.wallets_view)

        def _show_accounting(self):
            if not self._allow("accounting"):
                return
            self._set_active_nav("accounting")
            self.accounting_view.load_all()
            self.stack.setCurrentWidget(self.accounting_view)

        def _show_customers(self):
            if not self._allow("customers"):
                return
            self._set_active_nav("customers")
            self.customers_view.load_customers()
            self.stack.setCurrentWidget(self.customers_view)

        def _show_reports(self):
            if not self._allow("reports"):
                return
            self._set_active_nav("reports")
            self.reports_view.run_report()
            self.stack.setCurrentWidget(self.reports_view)

        def _show_settings(self):
            if not self._allow("settings"):
                return
            self._set_active_nav("settings")
            self.settings_view.load_backups()
            self.stack.setCurrentWidget(self.settings_view)

        def _allow(self, screen: str) -> bool:
            if can_open(self.perms, screen):
                return True
            show_error(self, message=ar.ACCESS_DENIED_SCREEN)
            return False

        def _confirm_logout(self):
            if QMessageBox.question(self, ar.LOGOUT, ar.LOGOUT_CONFIRM,
                                    QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.logout_requested.emit()

        def _open_change_password(self):
            if self.settings_view is not None:
                self._show_settings()
            else:
                from app.ui.login_dialog import ForcePasswordDialog
                dlg = ForcePasswordDialog(self.user_id, self, mandatory=False)
                dlg.setWindowTitle(ar.CHANGE_PASSWORD)
                dlg.exec()

        def close_for_logout(self):
            """Close without treating it as the user quitting the application."""
            self._closing_for_logout = True
            self.timer.stop()
            self.close()

        def _settings(self) -> QSettings:
            return QSettings(str(DATA_DIR / "window.ini"), QSettings.IniFormat)

        COMPACT_BELOW = 1280      # narrower windows get an icon-only sidebar so pages keep their width

        def resizeEvent(self, event):
            super().resizeEvent(event)
            self._apply_compact(self.width() < self.COMPACT_BELOW)

        def _apply_compact(self, compact: bool) -> None:
            if not hasattr(self, "sidebar") or compact == self._compact:
                return
            self._compact = compact
            set_prop(self.sidebar, "compact", compact)
            for lbl in self._sidebar_labels:
                lbl.setVisible(False if compact else lbl is self._sidebar_labels[0] or can_open(self.perms, "reports") or can_open(self.perms, "settings"))
            for btn in self.nav_buttons:
                text = btn.property("nav_text") or ""
                btn.setText("" if compact else text)
                key_tip = btn.property("nav_tip") or ""
                btn.setToolTip((f"{text}  ({key_tip})" if key_tip else text) if compact else key_tip)
                btn.setIconSize(QSize(22, 22))

        def _restore_geometry(self) -> None:
            """Restore the last size/position; fall back to a size that fits 1366x768."""
            geo = self._settings().value("main/geometry")
            if geo is not None and self.restoreGeometry(geo):
                return
            screen = self.screen().availableGeometry() if self.screen() else None
            w, h = (min(1340, screen.width()), min(860, screen.height())) if screen else (1340, 860)
            self.resize(w, h)

        def closeEvent(self, event):
            self._settings().setValue("main/geometry", self.saveGeometry())
            if hasattr(self, "session") and self.session:
                self.session.close()
            event.accept()
            if not self._closing_for_logout:
                self.closed_by_user.emit()

else:
    class MainWindow:  # type: ignore[no-redef]
        def __init__(self, current_user=None):
            pass
        def show(self) -> None:
            pass
