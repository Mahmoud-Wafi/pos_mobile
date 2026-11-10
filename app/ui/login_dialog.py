"""Login, forced-password-change and lock-screen dialogs."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QFormLayout,
)

from app.core.database import get_session
from app.core.security import verify_password
from app.i18n import ar
from app.services import auth_service

DEFAULT_PASSWORDS = {"admin123", "cashier123", "wallet123"}


def uses_default_password(user) -> bool:
    return any(verify_password(p, user.password_hash) for p in DEFAULT_PASSWORDS)


class LoginDialog(QDialog):
    """Authenticates a user. On accept, ``user_id`` holds the authenticated id."""

    def __init__(self, parent=None, locked: bool = False, username: str = ""):
        super().__init__(parent)
        self.user_id: int | None = None
        self.setWindowTitle(ar.APP_TITLE)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumWidth(380)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        title = QLabel(ar.LOCK_SCREEN_TITLE if locked else ar.LOGIN_TITLE)
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #0F172A;")
        title.setAlignment(Qt.AlignCenter)
        sub = QLabel(ar.LOGIN_SUBTITLE)
        sub.setStyleSheet("color: #64748B;")
        sub.setAlignment(Qt.AlignCenter)
        root.addWidget(title)
        root.addWidget(sub)

        form = QFormLayout()
        self.user_edit = QLineEdit(username)
        self.user_edit.setMinimumHeight(40)
        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.Password)
        self.pass_edit.setMinimumHeight(40)
        form.addRow(ar.USERNAME, self.user_edit)
        form.addRow(ar.PASSWORD, self.pass_edit)
        root.addLayout(form)

        self.error_lbl = QLabel("")
        self.error_lbl.setStyleSheet("color: #DC2626; font-weight: 600;")
        self.error_lbl.setWordWrap(True)
        self.error_lbl.setAlignment(Qt.AlignCenter)
        root.addWidget(self.error_lbl)

        self.btn = QPushButton(ar.LOGIN)
        self.btn.setObjectName("PrimaryBtn")
        self.btn.setMinimumHeight(42)
        self.btn.setDefault(True)
        self.btn.clicked.connect(self._attempt)
        root.addWidget(self.btn)

        self.pass_edit.returnPressed.connect(self._attempt)
        self.user_edit.returnPressed.connect(self.pass_edit.setFocus)
        (self.pass_edit if username else self.user_edit).setFocus()

    def _attempt(self) -> None:
        username = self.user_edit.text().strip()
        password = self.pass_edit.text()
        if not username or not password:
            self.error_lbl.setText(ar.LOGIN_FAILED)
            return
        session = get_session()
        try:
            user = auth_service.login(session, username, password)
            self.user_id = user.id
        except auth_service.AuthError as exc:
            self.error_lbl.setText(str(exc))
            self.pass_edit.clear()
            self.pass_edit.setFocus()
            return
        finally:
            session.close()
        self.accept()


class ForcePasswordDialog(QDialog):
    """Mandatory password change (cannot be dismissed without succeeding)."""

    def __init__(self, user_id: int, parent=None, mandatory: bool = True):
        super().__init__(parent)
        self.user_id = user_id
        self.mandatory = mandatory
        self.setWindowTitle(ar.FORCE_PASSWORD_TITLE)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumWidth(400)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(10)
        msg = QLabel(ar.FORCE_PASSWORD_MSG)
        msg.setWordWrap(True)
        root.addWidget(msg)

        form = QFormLayout()
        self.old_edit = QLineEdit()
        self.new_edit = QLineEdit()
        self.confirm_edit = QLineEdit()
        for e in (self.old_edit, self.new_edit, self.confirm_edit):
            e.setEchoMode(QLineEdit.Password)
            e.setMinimumHeight(38)
        form.addRow(ar.OLD_PASSWORD, self.old_edit)
        form.addRow(ar.NEW_PASSWORD, self.new_edit)
        form.addRow(ar.CONFIRM_PASSWORD, self.confirm_edit)
        root.addLayout(form)

        self.error_lbl = QLabel("")
        self.error_lbl.setStyleSheet("color: #DC2626; font-weight: 600;")
        self.error_lbl.setWordWrap(True)
        root.addWidget(self.error_lbl)

        btn = QPushButton(ar.SAVE)
        btn.setObjectName("PrimaryBtn")
        btn.setMinimumHeight(40)
        btn.clicked.connect(self._save)
        root.addWidget(btn)

    def reject(self) -> None:  # a mandatory change cannot be skipped with Esc / close
        if not self.mandatory:
            super().reject()

    def _save(self) -> None:
        old, new, confirm = self.old_edit.text(), self.new_edit.text(), self.confirm_edit.text()
        if len(new) < 6:
            self.error_lbl.setText(ar.PASSWORD_TOO_SHORT)
            return
        if new in DEFAULT_PASSWORDS:
            self.error_lbl.setText(ar.PASSWORD_IS_DEFAULT)
            return
        if new != confirm:
            self.error_lbl.setText(ar.PASSWORD_MISMATCH)
            return
        session = get_session()
        try:
            from app.models.user import User
            user = session.get(User, self.user_id)
            auth_service.change_password(session, user, old, new)
        except auth_service.AuthError as exc:
            self.error_lbl.setText(str(exc))
            return
        finally:
            session.close()
        super().accept()
