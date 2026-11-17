"""ConfirmDialog for destructive actions and show_error (short Arabic text, never raw Python errors)."""
from __future__ import annotations

import logging
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout

from app.i18n import ar
from app.ui.components.basic import button
from app.ui.design import icons
from app.ui.design.style import text_role
from app.ui.design.tokens import COLORS as C

log = logging.getLogger(__name__)
_ARABIC = re.compile(r"[؀-ۿ]")
GENERIC_ERROR = "حدث خطأ غير متوقع. تم تسجيل التفاصيل في ملف السجل."
DETAILS = "التفاصيل"


class ConfirmDialog(QDialog):
    """Yes/No confirmation. For destructive actions the safe button has the default focus."""

    def __init__(self, parent, title: str, message: str, confirm_text: str = ar.YES if hasattr(ar, "YES") else "تأكيد",
                 destructive: bool = False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumWidth(380)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(16)
        head = QHBoxLayout()
        pic = QLabel()
        pic.setPixmap(icons.pixmap("triangle-alert" if destructive else "info",
                                   C["danger"] if destructive else C["primary"], 28))
        head.addWidget(pic)
        t = QLabel(title)
        text_role(t, "title")
        head.addWidget(t, 1)
        lay.addLayout(head)
        msg = QLabel(message)
        msg.setWordWrap(True)
        lay.addWidget(msg)
        row = QHBoxLayout()
        row.addStretch()
        self.btn_cancel = button(ar.CANCEL, "secondary")
        self.btn_ok = button(confirm_text, "danger" if destructive else "primary")
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        row.addWidget(self.btn_cancel)
        row.addWidget(self.btn_ok)
        lay.addLayout(row)
        (self.btn_cancel if destructive else self.btn_ok).setDefault(True)
        (self.btn_cancel if destructive else self.btn_ok).setFocus()


def confirm(parent, title: str, message: str, confirm_text: str = "تأكيد", destructive: bool = False) -> bool:
    return ConfirmDialog(parent, title, message, confirm_text, destructive).exec() == QDialog.Accepted


def friendly_message(exc: BaseException | str | None) -> str:
    """Arabic business messages pass through; anything else becomes the generic text."""
    text = str(exc) if exc is not None else ""
    return text if _ARABIC.search(text) else GENERIC_ERROR


def show_error(parent, exc: BaseException | str | None = None, message: str | None = None,
               details: str | None = None) -> None:
    """Short Arabic error dialog. Unexpected exceptions are logged, not shown."""
    if isinstance(exc, BaseException) and not _ARABIC.search(str(exc)):
        log.error("unexpected error", exc_info=exc)
    text = message or friendly_message(exc)
    dlg = QDialog(parent)
    dlg.setWindowTitle(ar.ERROR)
    dlg.setLayoutDirection(Qt.RightToLeft)
    dlg.setMinimumWidth(380)
    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(24, 20, 24, 20)
    head = QHBoxLayout()
    pic = QLabel()
    pic.setPixmap(icons.pixmap("circle-alert", C["danger"], 28))
    head.addWidget(pic)
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    head.addWidget(lbl, 1)
    lay.addLayout(head)
    if details:
        box = QPlainTextEdit(details)
        box.setReadOnly(True)
        box.setVisible(False)
        toggle = button(DETAILS, "ghost")
        toggle.clicked.connect(lambda: box.setVisible(not box.isVisible()))
        lay.addWidget(toggle)
        lay.addWidget(box)
    ok = button(ar.OK if hasattr(ar, "OK") else "حسناً", "primary")
    ok.setDefault(True)
    ok.clicked.connect(dlg.accept)
    lay.addWidget(ok, 0, Qt.AlignLeft)
    dlg.exec()
