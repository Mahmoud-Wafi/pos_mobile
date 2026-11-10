"""Manager approval: a cashier hits a limit, a manager enters credentials to allow it."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from app.core.permissions import PermissionDenied
from app.i18n import ar
from app.models.user import User
from app.services import auth_service


class ManagerApprovalDialog(QDialog):
    """On accept, ``manager`` holds the approving manager (already audited)."""

    def __init__(self, session, acting_user: User, permission_code: str, reason: str, parent=None):
        super().__init__(parent)
        self.session = session
        self.acting_user = acting_user
        self.permission_code = permission_code
        self.manager: Optional[User] = None
        self.setWindowTitle(ar.APPROVAL_TITLE)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumWidth(420)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(10)
        why = QLabel(reason)
        why.setWordWrap(True)
        why.setStyleSheet("font-weight: 600; color: #92400E; background: #FEF3C7; padding: 8px; border-radius: 6px;")
        root.addWidget(why)

        form = QFormLayout()
        self.user_edit = QLineEdit()
        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.Password)
        for e in (self.user_edit, self.pass_edit):
            e.setMinimumHeight(38)
        form.addRow(ar.APPROVAL_MANAGER_USERNAME, self.user_edit)
        form.addRow(ar.MANAGER_PASSWORD, self.pass_edit)
        root.addLayout(form)

        self.error_lbl = QLabel("")
        self.error_lbl.setStyleSheet("color: #DC2626; font-weight: 600;")
        self.error_lbl.setWordWrap(True)
        root.addWidget(self.error_lbl)

        btn = QPushButton(ar.APPROVAL_GRANT)
        btn.setObjectName("PrimaryBtn")
        btn.setMinimumHeight(40)
        btn.setDefault(True)
        btn.clicked.connect(self._grant)
        root.addWidget(btn)
        self.pass_edit.returnPressed.connect(self._grant)
        self.user_edit.setFocus()

    def _grant(self) -> None:
        try:
            self.manager = auth_service.require_override(
                self.session, self.acting_user, self.permission_code,
                self.user_edit.text().strip(), self.pass_edit.text(),
            )
        except PermissionDenied:
            self.error_lbl.setText(ar.APPROVAL_NOT_MANAGER)
            self.pass_edit.clear()
            return
        except auth_service.AuthError as exc:
            self.error_lbl.setText(str(exc))
            self.pass_edit.clear()
            return
        self.accept()


def request_manager_approval(parent, session, acting_user: User, permission_code: str, reason: str) -> Optional[User]:
    """Show the dialog; return the approving manager or None if cancelled."""
    dlg = ManagerApprovalDialog(session, acting_user, permission_code, reason, parent)
    if dlg.exec() == QDialog.Accepted:
        return dlg.manager
    return None
