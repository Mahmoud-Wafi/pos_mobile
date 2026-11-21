"""Settings and maintenance view: Backups, security, and system status."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QFrame, QLineEdit, QGroupBox, QGridLayout,
)

from app.ui.components import confirm, confirm_typed, show_error, show_toast
from app.core.permissions import PermissionDenied
from app.services import backup_service
from app.i18n import ar
from app.services.auth_service import hash_password, verify_password
from app.ui.design.style import style_label, variant


class BackupSecurityTab(QWidget):
    def __init__(self, session, user, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self._build_ui()
        self.load_backups()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(16)

        # ── Top Bar ─────────────────────────────────────────
        top_bar = QHBoxLayout()
        top_bar.setSpacing(12)

        lbl_title = QLabel(ar.SETTINGS_WINDOW_091362)
        style_label(lbl_title, size="h2", tone="text", bold=True)
        top_bar.addWidget(lbl_title)
        top_bar.addStretch()

        main_layout.addLayout(top_bar)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(16)

        # ── Left Column: Backup Management ───────────────────
        backup_group = QGroupBox(ar.SETTINGS_WINDOW_84BBD9)
        bg_layout = QVBoxLayout(backup_group)
        bg_layout.setContentsMargins(8, 4, 8, 8)
        bg_layout.setSpacing(10)

        desc = QLabel(
            ar.SETTINGS_WINDOW_64D8D1
        )
        desc.setWordWrap(True)
        style_label(desc, size="caption", tone="muted")
        bg_layout.addWidget(desc)

        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(10)

        btn_create = QPushButton(ar.SETTINGS_WINDOW_6E962D)
        btn_create.setFixedHeight(42)
        variant(btn_create, "primary")
        btn_create.clicked.connect(self._create_backup)
        btn_bar.addWidget(btn_create)

        self.btn_offsite = QPushButton(ar.OFFSITE_COPY_NOW)
        self.btn_offsite.setFixedHeight(42)
        self.btn_offsite.clicked.connect(self._copy_offsite)
        btn_bar.addWidget(self.btn_offsite)

        btn_refresh = QPushButton(ar.LOW_STOCK_WIDGET_8EB2F5)
        btn_refresh.setFixedHeight(42)
        btn_refresh.clicked.connect(self.load_backups)
        btn_bar.addWidget(btn_refresh)

        btn_bar.addStretch()
        bg_layout.addLayout(btn_bar)

        self.table_backups = QTableWidget()
        self.table_backups.setColumnCount(3)
        self.table_backups.setHorizontalHeaderLabels([ar.SETTINGS_WINDOW_947B46, ar.SETTINGS_WINDOW_E3EBFE, ar.RETURNS_WINDOW_155E71])
        self.table_backups.verticalHeader().setVisible(False)
        self.table_backups.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_backups.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_backups.setAlternatingRowColors(True)
        self.table_backups.verticalHeader().setDefaultSectionSize(48)
        bh = self.table_backups.horizontalHeader()
        bh.setSectionResizeMode(0, QHeaderView.Stretch)
        bh.setSectionResizeMode(1, QHeaderView.Fixed); self.table_backups.setColumnWidth(1, 90)
        bh.setSectionResizeMode(2, QHeaderView.Fixed); self.table_backups.setColumnWidth(2, 110)
        bg_layout.addWidget(self.table_backups, 1)

        content_layout.addWidget(backup_group, 3)

        # ── Right Column: Password & System Specs ───────────
        right_box = QVBoxLayout()
        right_box.setSpacing(16)

        # Security Box
        sec_group = QGroupBox(ar.CHANGE_PASSWORD)
        sec_layout = QVBoxLayout(sec_group)
        sec_layout.setContentsMargins(8, 4, 8, 8)
        sec_layout.setSpacing(10)

        sec_layout.addWidget(QLabel(ar.SETTINGS_WINDOW_2D53C8))
        self.old_pass_edit = QLineEdit()
        self.old_pass_edit.setEchoMode(QLineEdit.Password)
        self.old_pass_edit.setFixedHeight(42)
        sec_layout.addWidget(self.old_pass_edit)
        sec_layout.addSpacing(4)

        sec_layout.addWidget(QLabel(ar.USERS_NEW_PASSWORD_PROMPT))
        self.new_pass_edit = QLineEdit()
        self.new_pass_edit.setEchoMode(QLineEdit.Password)
        self.new_pass_edit.setFixedHeight(42)
        sec_layout.addWidget(self.new_pass_edit)
        sec_layout.addSpacing(8)

        btn_save_pass = QPushButton(ar.SETTINGS_WINDOW_0404C0)
        btn_save_pass.setFixedHeight(44)
        variant(btn_save_pass, "success")
        btn_save_pass.clicked.connect(self._change_password)
        sec_layout.addWidget(btn_save_pass)

        right_box.addWidget(sec_group)

        # System Info Box
        info_group = QGroupBox(ar.SETTINGS_WINDOW_026F2F)
        info_layout = QVBoxLayout(info_group)
        info_layout.setContentsMargins(8, 4, 8, 8)
        info_layout.setSpacing(8)

        infos = [
            (ar.SETTINGS_WINDOW_33C0CB, ar.APP_TITLE),
            (ar.SETTINGS_WINDOW_1425CB, ar.SETTINGS_WINDOW_6DC5FB),
            (ar.SETTINGS_WINDOW_CE31EB, ar.SETTINGS_WINDOW_9F518B),
            (ar.SETTINGS_WINDOW_A76753, ar.SETTINGS_WINDOW_025AE3),
            (ar.SETTINGS_WINDOW_4D8B5E, ar.SETTINGS_WINDOW_914B7D),
            (ar.SETTINGS_WINDOW_1B43FD, ar.SETTINGS_WINDOW_72871A),
        ]
        for label, val in infos:
            box = QVBoxLayout()
            box.setSpacing(1)
            lbl_k = QLabel(label.rstrip(":").strip())
            style_label(lbl_k, size="caption", tone="muted", bold=True)
            lbl_v = QLabel("\u200f" + val + "\u200f")   # RLM: keeps (parentheses) and Latin words in order
            lbl_v.setWordWrap(True)
            style_label(lbl_v, tone="text", bold=True)
            box.addWidget(lbl_k)
            box.addWidget(lbl_v)
            info_layout.addLayout(box)

        right_box.addWidget(info_group)
        right_box.addStretch()

        content_layout.addLayout(right_box, 2)
        main_layout.addLayout(content_layout, 1)

    def load_backups(self):
        try:
            backups = backup_service.listing(self.session, self.user)
        except PermissionDenied:
            backups = []
        self.table_backups.setRowCount(len(backups))
        for r, bp in enumerate(backups):
            self.table_backups.setItem(r, 0, QTableWidgetItem(bp.name))
            size_kb = os.path.getsize(bp) / 1024
            self.table_backups.setItem(r, 1, QTableWidgetItem(f"{size_kb:.1f} KB"))

            btn_res = QPushButton(ar.RESTORE_PHRASE)
            variant(btn_res, "secondary")   # destructive only after the typed confirmation
            btn_res.clicked.connect(lambda _, path=bp: self._confirm_restore(path))
            self.table_backups.setCellWidget(r, 2, btn_res)

    def _copy_offsite(self):
        try:
            backup_service.copy_offsite_now(self.session, self.user)
        except Exception as e:
            self.session.rollback()
            show_error(self, e)
            return
        show_toast(self, ar.OFFSITE_COPIED)

    def _create_backup(self):
        try:
            bp = backup_service.create(self.session, self.user)
            show_toast(self, f"تم إنشاء النسخة الاحتياطية بنجاح:\n{bp.name}")
            self.load_backups()
        except Exception as e:
            show_error(self, e)

    def _confirm_restore(self, backup_path: Path):
        msg = (f"ستتم استعادة النسخة ({backup_path.name}) بعد حفظ نسخة أمان من قاعدة البيانات الحالية، "
               "وسيتم استبدال كل البيانات الحالية ببيانات هذه النسخة، ثم يُعاد تشغيل البرنامج.")
        if not confirm_typed(self, ar.SETTINGS_WINDOW_9876A4, msg, ar.RESTORE_PHRASE, ar.RESTORE_PHRASE):
            return
        try:
            backup_service.restore(self.session, self.user, backup_path)
        except Exception as e:
            show_error(self, e)
            return
        self._offer_restart()

    def _offer_restart(self):
        if confirm(self, ar.RESTORE_DONE_TITLE, ar.RESTORE_DONE_MSG, ar.RESTART_NOW):
            from PySide6.QtCore import QProcess
            from PySide6.QtWidgets import QApplication
            from app.core.startup import restart_command

            program, args = restart_command()
            QProcess.startDetached(program, args)
        from PySide6.QtWidgets import QApplication
        QApplication.quit()

    def _change_password(self):
        old_pwd = self.old_pass_edit.text()
        new_pwd = self.new_pass_edit.text()

        if not old_pwd or not new_pwd:
            show_error(self, message=ar.SETTINGS_WINDOW_078221)
            return

        if len(new_pwd) < 6:
            show_error(self, message=ar.PASSWORD_TOO_SHORT)
            return

        if not verify_password(old_pwd, self.user.password_hash):
            show_error(self, message=ar.SETTINGS_WINDOW_1ED93E)
            return

        try:
            self.user.password_hash = hash_password(new_pwd)
            self.session.commit()
            self.old_pass_edit.clear()
            self.new_pass_edit.clear()
            show_toast(self, ar.SETTINGS_WINDOW_07E187)
        except Exception as e:
            self.session.rollback()
            show_error(self, e)


class SettingsWidget(QWidget):
    """Settings screen: shop info, users, audit log, backup & password (tabs depend on permissions)."""

    def __init__(self, session, user, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QTabWidget
        from app.core import permissions as P
        from app.i18n import ar
        from app.ui.settings.settings_tabs import AuditTab, ShopSettingsTab, UsersTab

        perms = user.permission_codes()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.shop_tab = self.users_tab = self.audit_tab = None
        if P.PERM_SETTINGS_MANAGE in perms:
            self.shop_tab = ShopSettingsTab(session, user)
            self.tabs.addTab(self.shop_tab, ar.SET_TAB_SHOP)
        self.hardware_tab = None
        if P.PERM_SETTINGS_MANAGE in perms:
            from app.ui.settings.hardware_tab import HardwareTab
            self.hardware_tab = HardwareTab(session, user)
            self.tabs.addTab(self.hardware_tab, ar.HW_TAB)
        if P.PERM_USERS_MANAGE in perms:
            self.users_tab = UsersTab(session, user)
            self.tabs.addTab(self.users_tab, ar.SET_TAB_USERS)
        if P.PERM_AUDIT_VIEW in perms:
            self.audit_tab = AuditTab(session, user)
            self.tabs.addTab(self.audit_tab, ar.SET_TAB_AUDIT)
        self.backup_tab = BackupSecurityTab(session, user)
        self.tabs.addTab(self.backup_tab, ar.SET_TAB_BACKUP)

    def load_backups(self):
        """Called by the main window whenever the screen is opened."""
        self.backup_tab.load_backups()
        for tab in (self.shop_tab, self.hardware_tab, self.users_tab, self.audit_tab):
            if tab is not None:
                tab.refresh()
