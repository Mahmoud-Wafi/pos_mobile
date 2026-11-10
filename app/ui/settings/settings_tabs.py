"""Shop settings, user administration and audit-log tabs."""
from __future__ import annotations

import csv
import datetime

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from app.core import clock
from app.core.permissions import PermissionDenied
from app.i18n import ar
from app.services import audit_service, settings_service, user_service


def _table(headers: list[str]) -> QTableWidget:
    t = QTableWidget()
    t.setColumnCount(len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QTableWidget.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectRows)
    t.setSelectionMode(QTableWidget.SingleSelection)
    t.setAlternatingRowColors(True)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    return t


def _error(parent, exc: Exception) -> None:
    if isinstance(exc, PermissionDenied):
        QMessageBox.warning(parent, ar.WARNING, ar.PERMISSION_DENIED)
    else:
        QMessageBox.warning(parent, ar.WARNING, str(exc))


# ── Shop settings ─────────────────────────────────────────────────────────────

class ShopSettingsTab(QWidget):
    FIELDS = [
        ("shop_name", ar.SET_SHOP_NAME),
        ("shop_address", ar.SET_SHOP_ADDRESS),
        ("shop_phone", ar.SET_SHOP_PHONE),
        ("invoice_footer", ar.SET_INVOICE_FOOTER),
        ("warranty_text", ar.SET_WARRANTY_TEXT),
        ("cashier_discount_limit_pct", ar.SET_DISCOUNT_LIMIT),
        ("idle_lock_minutes", ar.SET_IDLE_LOCK),
    ]

    def __init__(self, session, user, parent=None):
        super().__init__(parent)
        self.session, self.user = session, user
        self.edits: dict[str, QLineEdit] = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        for key, label in self.FIELDS:
            e = QLineEdit()
            e.setMinimumHeight(36)
            self.edits[key] = e
            form.addRow(label, e)
        root.addLayout(form)
        btn = QPushButton(ar.SAVE)
        btn.setObjectName("PrimaryBtn")
        btn.setMinimumHeight(40)
        btn.clicked.connect(self.save)
        row = QHBoxLayout()
        row.addWidget(btn)
        row.addStretch()
        root.addLayout(row)
        root.addStretch()
        self.refresh()

    def refresh(self) -> None:
        values = settings_service.get_all(self.session)
        for key, edit in self.edits.items():
            edit.setText(values.get(key, ""))

    def save(self) -> None:
        try:
            settings_service.update(self.session, self.user, {k: e.text() for k, e in self.edits.items()})
            self.session.commit()
        except Exception as exc:
            self.session.rollback()
            _error(self, exc)
            return
        QMessageBox.information(self, ar.SUCCESS, ar.SET_SAVED)


# ── Users ─────────────────────────────────────────────────────────────────────

ROLE_AR = {"manager": ar.ROLE_MANAGER, "cashier": ar.ROLE_CASHIER, "wallet_employee": ar.ROLE_WALLET_EMPLOYEE}


class UserDialog(QDialog):
    """Create (user=None) or edit a user."""

    def __init__(self, roles, user=None, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setWindowTitle(ar.USERS_ADD if user is None else ar.USERS_EDIT)
        self.setMinimumWidth(380)
        form = QFormLayout(self)
        self.username = QLineEdit(user.username if user else "")
        self.username.setEnabled(user is None)
        self.full_name = QLineEdit(user.full_name if user else "")
        self.role = QComboBox()
        for r in roles:
            self.role.addItem(ROLE_AR.get(r.name, r.name), r.id)
        if user:
            self.role.setCurrentIndex(max(0, self.role.findData(user.role_id)))
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.active = QCheckBox(ar.USERS_ACTIVE)
        self.active.setChecked(user.is_active if user else True)
        form.addRow(ar.USERNAME, self.username)
        form.addRow(ar.USERS_FULL_NAME, self.full_name)
        form.addRow(ar.USERS_ROLE, self.role)
        if user is None:
            form.addRow(ar.PASSWORD, self.password)
        else:
            form.addRow("", self.active)
        ok = QPushButton(ar.SAVE)
        ok.setObjectName("PrimaryBtn")
        ok.clicked.connect(self.accept)
        form.addRow(ok)


class UsersTab(QWidget):
    def __init__(self, session, user, parent=None):
        super().__init__(parent)
        self.session, self.user = session, user
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        bar = QHBoxLayout()
        for text, slot in ((ar.USERS_ADD, self.add), (ar.USERS_EDIT, self.edit),
                           (ar.USERS_RESET_PW, self.reset_pw), (ar.USERS_UNLOCK, self.unlock)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            bar.addWidget(b)
        bar.addStretch()
        root.addLayout(bar)
        self.table = _table([ar.USERNAME, ar.USERS_FULL_NAME, ar.USERS_ROLE, ar.USERS_STATUS, ar.USERS_LAST_LOGIN])
        root.addWidget(self.table, 1)
        self.refresh()

    def refresh(self) -> None:
        try:
            users = user_service.list_users(self.session, self.user)
        except PermissionDenied:
            users = []
        self.table.setRowCount(len(users))
        now = clock.utcnow()
        for r, u in enumerate(users):
            if not u.is_active:
                status = ar.USERS_STATUS_INACTIVE
            elif u.locked_until and u.locked_until > now:
                status = ar.USERS_STATUS_LOCKED
            else:
                status = ar.USERS_STATUS_ACTIVE
            cells = [u.username, u.full_name, ROLE_AR.get(u.role.name, u.role.name), status,
                     clock.fmt_local(u.last_login)]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setData(Qt.UserRole, u.id)
                self.table.setItem(r, c, item)

    def _selected_id(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, ar.WARNING, ar.USERS_SELECT_FIRST)
            return None
        return self.table.item(row, 0).data(Qt.UserRole)

    def _run(self, fn) -> None:
        try:
            fn()
            self.session.commit()
        except Exception as exc:
            self.session.rollback()
            _error(self, exc)
        self.refresh()

    def add(self) -> None:
        dlg = UserDialog(user_service.list_roles(self.session, self.user), parent=self)
        if dlg.exec() == QDialog.Accepted:
            self._run(lambda: user_service.create_user(
                self.session, self.user, dlg.username.text(), dlg.full_name.text(),
                dlg.role.currentData(), dlg.password.text()))

    def edit(self) -> None:
        uid = self._selected_id()
        if uid is None:
            return
        target = self.session.get(type(self.user), uid)
        dlg = UserDialog(user_service.list_roles(self.session, self.user), target, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self._run(lambda: user_service.update_user(
                self.session, self.user, uid, full_name=dlg.full_name.text(),
                role_id=dlg.role.currentData(), is_active=dlg.active.isChecked()))

    def reset_pw(self) -> None:
        uid = self._selected_id()
        if uid is None:
            return
        pw, ok = QInputDialog.getText(self, ar.USERS_RESET_PW, ar.USERS_NEW_PASSWORD_PROMPT, QLineEdit.Password)
        if ok:
            self._run(lambda: user_service.reset_password(self.session, self.user, uid, pw))

    def unlock(self) -> None:
        uid = self._selected_id()
        if uid is not None:
            self._run(lambda: user_service.unlock_user(self.session, self.user, uid))


# ── Audit log ─────────────────────────────────────────────────────────────────

class AuditTab(QWidget):
    def __init__(self, session, user, parent=None):
        super().__init__(parent)
        self.session, self.user = session, user
        self.rows: list[list[str]] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        bar = QHBoxLayout()
        self.date_from = QDateEdit(QDate.currentDate().addDays(-7))
        self.date_to = QDateEdit(QDate.currentDate())
        for d in (self.date_from, self.date_to):
            d.setCalendarPopup(True)
        self.user_combo = QComboBox()
        self.user_combo.addItem(ar.AUDIT_ALL_USERS, None)
        try:
            for u in user_service.list_users(session, user):
                self.user_combo.addItem(u.username, u.id)
        except PermissionDenied:
            pass
        self.action_edit = QLineEdit()
        self.action_edit.setPlaceholderText(ar.AUDIT_ACTION)
        self.action_edit.returnPressed.connect(self.refresh)
        search = QPushButton(ar.AUDIT_SEARCH)
        search.setObjectName("PrimaryBtn")
        search.clicked.connect(self.refresh)
        export = QPushButton(ar.AUDIT_EXPORT)
        export.clicked.connect(self.export_csv)
        for w in (QLabel(ar.AUDIT_FROM), self.date_from, QLabel(ar.AUDIT_TO), self.date_to,
                  self.user_combo, self.action_edit, search, export):
            bar.addWidget(w)
        bar.addStretch()
        root.addLayout(bar)
        self.table = _table(ar.AUDIT_COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        root.addWidget(self.table, 1)
        self.refresh()

    def refresh(self) -> None:
        try:
            entries = audit_service.list_entries(
                self.session, self.user,
                user_id=self.user_combo.currentData(),
                action=self.action_edit.text() or None,
                start_date=self.date_from.date().toPython(),
                end_date=self.date_to.date().toPython(),
            )
        except PermissionDenied:
            entries = []
        self.rows = []
        for e in entries:
            self.rows.append([
                clock.fmt_local(e.timestamp, "%Y-%m-%d %H:%M:%S"),
                e.user.username if e.user else "—",
                e.action, e.table_name or "", str(e.record_id or ""), e.new_value or e.reason or "",
            ])
        self.table.setRowCount(len(self.rows))
        for r, row in enumerate(self.rows):
            for c, text in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem(text))

    def export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, ar.AUDIT_EXPORT,
            f"audit_{clock.local_today():%Y%m%d}.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:   # BOM: opens correctly in Arabic Excel
            w = csv.writer(fh)
            w.writerow(ar.AUDIT_COLUMNS)
            w.writerows(self.rows)
