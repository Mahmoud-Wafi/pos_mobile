"""Make every dialog fit the screen it is shown on (D-024).

A dialog taller than the screen (small laptop, scaled display, many fields) used to run off the top and
bottom, hiding its buttons. When a dialog does not fit, its content moves into a scroll area and its
action row (Save / Cancel buttons) stays pinned at the bottom, always visible. Dialogs that fit are only
clamped and centred, never changed.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QBoxLayout, QComboBox, QDialog, QDialogButtonBox, QFrame, QLabel, QLayout, QPushButton, QScrollArea,
                               QSpacerItem, QVBoxLayout, QWidget)

SCREEN_FRACTION_H = 0.92
SCREEN_FRACTION_W = 0.96
_SKIP_MODULES = ("PySide6.",)          # Qt's own dialogs (file chooser, message box...) size themselves


def _is_action_row(item) -> bool:
    w = item.widget()
    if w is not None:
        if isinstance(w, QDialogButtonBox):
            return True
        # a card / frame whose only content is a row of buttons
        inner = w.layout()
        return inner is not None and not isinstance(w, QPushButton) and _pure_buttons(inner)
    lay = item.layout()
    return lay is not None and _pure_buttons(lay)


def _pure_buttons(lay) -> bool:
    buttons = 0
    for i in range(lay.count()):
        sub = lay.itemAt(i)
        if isinstance(sub, QSpacerItem) or sub.spacerItem() is not None:
            continue
        sw = sub.widget()
        if sw is None or not isinstance(sw, (QPushButton, QLabel, QComboBox)):
            return False                       # a footer may also hold a label / account combo
        if isinstance(sw, QPushButton):
            buttons += 1
    return buttons > 0


def _available(dlg: QDialog):
    screen = dlg.screen() or QGuiApplication.primaryScreen()
    return screen.availableGeometry()


def fit_dialog(dlg: QDialog) -> None:
    """Idempotent. Call after the dialog is built (done automatically on first show)."""
    if dlg.property("_fit_done"):
        return
    dlg.setProperty("_fit_done", True)
    avail = _available(dlg)
    max_h, max_w = int(avail.height() * SCREEN_FRACTION_H), int(avail.width() * SCREEN_FRACTION_W)

    lay = dlg.layout()
    needed = dlg.minimumSizeHint().height()
    if lay is not None and (needed > max_h or dlg.minimumHeight() > max_h):
        need_w = _wrap_in_scroll(dlg, lay)          # width the content needs once a scrollbar is added
        dlg.setMinimumHeight(min(dlg.minimumHeight(), max_h))
        dlg.setMinimumWidth(min(max(dlg.minimumWidth(), need_w), max_w))
        dlg.resize(min(max(dlg.width(), need_w), max_w), max_h)
    else:
        dlg.resize(min(dlg.width(), max_w), min(dlg.height(), max_h))
    dlg.setMaximumHeight(max(max_h, dlg.minimumHeight()))

    # keep the whole dialog on screen
    frame = dlg.frameGeometry()
    if not avail.contains(frame):
        frame.moveCenter(avail.center())
        x = min(max(frame.left(), avail.left()), avail.right() - frame.width() + 1)
        y = min(max(frame.top(), avail.top()), avail.bottom() - frame.height() + 1)
        dlg.move(x, y)


def _wrap_in_scroll(dlg: QDialog, lay: QLayout) -> int:
    margins, spacing = lay.contentsMargins(), lay.spacing()
    # Re-parenting hides widgets; remember which ones were showing so they are shown again afterwards.
    was_visible = [w for w in dlg.findChildren(QWidget) if w.isVisibleTo(dlg)]

    # 1. the trailing action row (buttons) stays outside the scrolling part
    pinned = None
    if isinstance(lay, QBoxLayout):
        for i in range(lay.count() - 1, -1, -1):
            item = lay.itemAt(i)
            if item.spacerItem() is not None:
                continue
            if _is_action_row(item):
                pinned = lay.takeAt(i)
            break

    # 2. everything else moves, as it is, into a scroll area (the layout is stolen from the dialog)
    content = QWidget()
    content.setLayoutDirection(dlg.layoutDirection())
    content.setLayout(lay)
    scroll = QScrollArea(dlg)
    scroll.setObjectName("dialogFitScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setWidget(content)

    root = QVBoxLayout(dlg)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)
    root.addWidget(scroll, 1)
    if pinned is not None:
        bar = QWidget(dlg)
        bar_lay = QVBoxLayout(bar)
        bar_lay.setContentsMargins(margins.left(), max(spacing, 8), margins.right(), max(margins.bottom(), 10))
        if pinned.widget() is not None:          # addLayout / addWidget re-parent the buttons into the bar
            bar_lay.addWidget(pinned.widget())
        else:
            bar_lay.addLayout(pinned.layout())
        root.addWidget(bar, 0)
    scroll.show()
    if pinned is not None:
        bar.show()
    for w in was_visible:
        w.show()
    dlg._fit_scroll = scroll
    dlg._fit_pinned = pinned is not None
    width = content.minimumSizeHint().width() + scroll.verticalScrollBar().sizeHint().width() + 4
    if pinned is not None:
        width = max(width, bar.minimumSizeHint().width())
    return width


class DialogFit(QObject):
    def eventFilter(self, obj: QObject, ev: QEvent) -> bool:
        if ev.type() == QEvent.Show and isinstance(obj, QDialog) and not obj.property("_fit_done"):
            if not type(obj).__module__.startswith(_SKIP_MODULES):
                fit_dialog(obj)
        return False
