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

from app.core.backup import BACKUP_DIR, create_backup, list_backups, restore_backup
from app.services.auth_service import hash_password, verify_password


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

        lbl_title = QLabel("⚙️ إعدادات النظام والنسخ الاحتياطي والأمان")
        lbl_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #0F172A;")
        top_bar.addWidget(lbl_title)
        top_bar.addStretch()

        main_layout.addLayout(top_bar)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(16)

        # ── Left Column: Backup Management ───────────────────
        backup_group = QGroupBox("💾 إدارة النسخ الاحتياطي (Database Backups)")
        backup_group.setStyleSheet("QGroupBox { font-weight: bold; color: #1E3A8A; font-size: 14px; }")
        bg_layout = QVBoxLayout(backup_group)
        bg_layout.setContentsMargins(12, 16, 12, 12)
        bg_layout.setSpacing(10)

        desc = QLabel(
            "يقوم النظام بإنشاء نسخة احتياطية آمنة ومضغوطة من قاعدة البيانات لضمان عدم ضياع أي بيانات مبيعات أو فواتير."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #475569; font-size: 12px;")
        bg_layout.addWidget(desc)

        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(10)

        btn_create = QPushButton("➕ إنشاء نسخة احتياطية الآن")
        btn_create.setFixedHeight(38)
        btn_create.setStyleSheet("background-color: #2563EB; color: white; font-weight: bold; border-radius: 6px; padding: 0 14px;")
        btn_create.clicked.connect(self._create_backup)
        btn_bar.addWidget(btn_create)

        btn_refresh = QPushButton("🔄 تحديث القائمة")
        btn_refresh.setFixedHeight(38)
        btn_refresh.clicked.connect(self.load_backups)
        btn_bar.addWidget(btn_refresh)

        btn_bar.addStretch()
        bg_layout.addLayout(btn_bar)

        self.table_backups = QTableWidget()
        self.table_backups.setColumnCount(3)
        self.table_backups.setHorizontalHeaderLabels(["اسم ملف النسخة الاحتياطية", "الحجم", "إجراء"])
        self.table_backups.verticalHeader().setVisible(False)
        self.table_backups.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_backups.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_backups.setAlternatingRowColors(True)
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
        sec_group = QGroupBox("🔐 تغيير كلمة المرور")
        sec_group.setStyleSheet("QGroupBox { font-weight: bold; color: #1E3A8A; font-size: 14px; }")
        sec_layout = QVBoxLayout(sec_group)
        sec_layout.setContentsMargins(12, 16, 12, 12)
        sec_layout.setSpacing(8)

        sec_layout.addWidget(QLabel("كلمة المرور الحالية:"))
        self.old_pass_edit = QLineEdit()
        self.old_pass_edit.setEchoMode(QLineEdit.Password)
        self.old_pass_edit.setFixedHeight(34)
        sec_layout.addWidget(self.old_pass_edit)

        sec_layout.addWidget(QLabel("كلمة المرور الجديدة:"))
        self.new_pass_edit = QLineEdit()
        self.new_pass_edit.setEchoMode(QLineEdit.Password)
        self.new_pass_edit.setFixedHeight(34)
        sec_layout.addWidget(self.new_pass_edit)

        btn_save_pass = QPushButton("💾 تحديث كلمة المرور")
        btn_save_pass.setFixedHeight(36)
        btn_save_pass.setStyleSheet("background-color: #059669; color: white; font-weight: bold; border-radius: 6px;")
        btn_save_pass.clicked.connect(self._change_password)
        sec_layout.addWidget(btn_save_pass)

        right_box.addWidget(sec_group)

        # System Info Box
        info_group = QGroupBox("ℹ️ معلومات النظام والترخيص")
        info_group.setStyleSheet("QGroupBox { font-weight: bold; color: #1E3A8A; font-size: 14px; }")
        info_layout = QVBoxLayout(info_group)
        info_layout.setContentsMargins(12, 16, 12, 12)
        info_layout.setSpacing(6)

        infos = [
            ("اسم البرنامج:", "نظام إدارة محل الموبايلات"),
            ("الإصدار:", "1.0 (مستقر - وضع Offline كامل)"),
            ("المحرك المالي:", "نظام القروش الصحيحة (Integer Piasters)"),
            ("قاعدة البيانات:", "SQLite 3 (وضع WAL مؤمن + FK)"),
            ("بيئة التشغيل:", "سطح المكتب (Desktop App)"),
            ("الدعم الفني:", "محلي دون اتصال خارجي"),
        ]
        for label, val in infos:
            row = QHBoxLayout()
            lbl_k = QLabel(label)
            lbl_k.setStyleSheet("color: #64748B; font-weight: bold;")
            lbl_v = QLabel(val)
            lbl_v.setStyleSheet("color: #0F172A; font-weight: 600;")
            row.addWidget(lbl_k)
            row.addStretch()
            row.addWidget(lbl_v)
            info_layout.addLayout(row)

        right_box.addWidget(info_group)
        right_box.addStretch()

        content_layout.addLayout(right_box, 2)
        main_layout.addLayout(content_layout, 1)

    def load_backups(self):
        backups = list_backups(BACKUP_DIR)
        self.table_backups.setRowCount(len(backups))
        for r, bp in enumerate(backups):
            self.table_backups.setItem(r, 0, QTableWidgetItem(bp.name))
            size_kb = os.path.getsize(bp) / 1024
            self.table_backups.setItem(r, 1, QTableWidgetItem(f"{size_kb:.1f} KB"))

            btn_res = QPushButton("استعادة")
            btn_res.setStyleSheet("background-color: #DC2626; color: white; font-weight: bold; border-radius: 4px; padding: 4px;")
            btn_res.clicked.connect(lambda _, path=bp: self._confirm_restore(path))
            self.table_backups.setCellWidget(r, 2, btn_res)

    def _create_backup(self):
        try:
            bp = create_backup()
            QMessageBox.information(self, "نجاح", f"تم إنشاء النسخة الاحتياطية بنجاح:\n{bp.name}")
            self.load_backups()
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"تعذر إنشاء النسخة الاحتياطية:\n{e}")

    def _confirm_restore(self, backup_path: Path):
        reply = QMessageBox.warning(
            self,
            "تأكيد الاستعادة",
            f"تحذير: استعادة النسخة الاحتياطية ({backup_path.name}) ستقوم بحفظ نسخة أمان أولاً ثم استبدال قاعدة البيانات الحالية.\nهل أنت متأكد من المتابعة؟",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            try:
                restore_backup(backup_path)
                QMessageBox.information(self, "نجاح", "تمت استعادة النسخة الاحتياطية بنجاح. يُرجى إعادة تشغيل التطبيق لتحديث الجداول.")
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر استعادة النسخة الاحتياطية:\n{e}")

    def _change_password(self):
        old_pwd = self.old_pass_edit.text()
        new_pwd = self.new_pass_edit.text()

        if not old_pwd or not new_pwd:
            QMessageBox.warning(self, "تنبيه", "يرجى إدخال كلمة المرور الحالية والجديدة")
            return

        if len(new_pwd) < 6:
            QMessageBox.warning(self, "تنبيه", "كلمة المرور الجديدة يجب أن تكون 6 خانات على الأقل")
            return

        if not verify_password(old_pwd, self.user.password_hash):
            QMessageBox.warning(self, "خطأ", "كلمة المرور الحالية غير صحيحة")
            return

        try:
            self.user.password_hash = hash_password(new_pwd)
            self.session.commit()
            self.old_pass_edit.clear()
            self.new_pass_edit.clear()
            QMessageBox.information(self, "نجاح", "تم تغيير كلمة المرور بنجاح!")
        except Exception as e:
            self.session.rollback()
            QMessageBox.critical(self, "خطأ", f"تعذر حفظ كلمة المرور:\n{e}")



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
        for tab in (self.shop_tab, self.users_tab, self.audit_tab):
            if tab is not None:
                tab.refresh()
