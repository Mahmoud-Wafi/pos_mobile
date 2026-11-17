"""Auto-dismissing toast shown at the bottom of the window."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QTimer, Qt
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QWidget

from app.ui.design import icons
from app.ui.design.style import set_prop
from app.ui.design.tokens import COLORS as C

_ICONS = {"success": "circle-check", "error": "circle-alert", "info": "info", "warning": "triangle-alert"}


class Toast(QFrame):
    def __init__(self, parent: QWidget, text: str, kind: str = "success", msec: int = 3000):
        super().__init__(parent)
        set_prop(self, "toast", True)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 10)
        pic = QLabel()
        pic.setPixmap(icons.pixmap(_ICONS.get(kind, "info"), C["text_inverse"], 18))
        lay.addWidget(pic)
        self.label = QLabel(text)
        lay.addWidget(self.label)
        self.adjustSize()
        self._reposition()
        parent.installEventFilter(self)
        self.show()
        self.raise_()
        QTimer.singleShot(msec, self.close_toast)

    def _reposition(self) -> None:
        p = self.parentWidget()
        self.move((p.width() - self.width()) // 2, p.height() - self.height() - 48)

    def eventFilter(self, obj: QObject, ev: QEvent) -> bool:
        if ev.type() == QEvent.Resize:
            self._reposition()
        return False

    def close_toast(self) -> None:
        self.hide()
        self.deleteLater()


def show_toast(parent: QWidget | None, text: str, kind: str = "success", msec: int = 3000) -> Toast | None:
    """Show a non-blocking message on the parent's top-level window."""
    if parent is None:
        return None
    win = parent.window()
    while isinstance(win, QDialog) and win.parentWidget() is not None:   # outlive the dialog that spawned it
        win = win.parentWidget().window()
    return Toast(win, text, kind, msec)
