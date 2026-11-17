"""Card, KpiCard, PageHeader, buttons, StatusPill, SearchField, FormRow, EmptyState."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from app.i18n import ar
from app.ui.design import icons
from app.ui.design.style import set_prop, text_role, variant
from app.ui.design.tokens import COLORS as C, SPACING as S


def button(text: str, kind: str = "secondary", icon: str | None = None, parent=None) -> QPushButton:
    """Button variants: primary / secondary / danger / success / ghost."""
    b = QPushButton(text, parent)
    variant(b, kind)
    if icon:
        on_dark = kind in ("primary", "danger", "success")
        b.setIcon(icons.icon(icon, C["text_inverse"] if on_dark else C["text_muted"]))
    b.setCursor(Qt.PointingHandCursor)
    return b


def icon_button(icon_name: str, tooltip: str, kind: str = "ghost", parent=None) -> QPushButton:
    """Icon-only button (needs a tooltip for accessibility)."""
    b = QPushButton(parent)
    variant(b, kind)
    b.setIcon(icons.icon(icon_name, C["danger"] if kind == "danger-soft" else C["text_muted"]))
    b.setToolTip(tooltip)
    b.setAccessibleName(tooltip)
    b.setFixedSize(36, 36)
    b.setCursor(Qt.PointingHandCursor)
    return b


class Card(QFrame):
    def __init__(self, parent=None, margins: int = S["lg"]):
        super().__init__(parent)
        set_prop(self, "card", True)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(margins, margins, margins, margins)
        self.body.setSpacing(S["md"])


class KpiCard(QFrame):
    """Label + big value (+ optional hint). Update with set_value()."""

    def __init__(self, title: str, value: str = "—", hint: str = "", parent=None):
        super().__init__(parent)
        set_prop(self, "kpi", True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(S["lg"], S["md"], S["lg"], S["md"])
        lay.setSpacing(S["xs"])
        self.title_lbl = QLabel(title)
        text_role(self.title_lbl, "caption")
        self.value_lbl = QLabel(value)
        text_role(self.value_lbl, "money")
        self.hint_lbl = QLabel(hint)
        text_role(self.hint_lbl, "caption")
        self.hint_lbl.setVisible(bool(hint))
        for w in (self.title_lbl, self.value_lbl, self.hint_lbl):
            lay.addWidget(w)

    def set_value(self, value: str, hint: str | None = None) -> None:
        self.value_lbl.setText(value)
        if hint is not None:
            self.hint_lbl.setText(hint)
            self.hint_lbl.setVisible(bool(hint))


class PageHeader(QWidget):
    """Screen title + optional subtitle on one side, action buttons on the other."""

    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, S["sm"])
        col = QVBoxLayout()
        col.setSpacing(0)
        self.title_lbl = QLabel(title)
        text_role(self.title_lbl, "h2")
        col.addWidget(self.title_lbl)
        if subtitle:
            sub = QLabel(subtitle)
            text_role(sub, "caption")
            col.addWidget(sub)
        row.addLayout(col)
        row.addStretch()
        self.actions = QHBoxLayout()
        self.actions.setSpacing(S["sm"])
        row.addLayout(self.actions)

    def add_action(self, btn: QPushButton) -> QPushButton:
        self.actions.addWidget(btn)
        return btn


class StatusPill(QLabel):
    """Small coloured status label: success / warning / danger / info / neutral."""

    def __init__(self, text: str = "", kind: str = "neutral", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        set_prop(self, "pill", kind)

    def set_status(self, text: str, kind: str) -> None:
        self.setText(text)
        set_prop(self, "pill", kind)


class SearchField(QLineEdit):
    """Search box with a leading icon, clear button and a debounced-friendly `search` signal on Enter."""

    search = Signal(str)

    def __init__(self, placeholder: str = ar.SEARCH, parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self.addAction(icons.icon("search", C["text_muted"]), QLineEdit.LeadingPosition)
        self.returnPressed.connect(lambda: self.search.emit(self.text().strip()))


class FormRow(QWidget):
    """Label above a field, with optional error text under it."""

    def __init__(self, label: str, field: QWidget, hint: str = "", parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(S["xs"])
        self.label = QLabel(label)
        self.label.setBuddy(field)
        self.field = field
        self.error = QLabel("")
        set_prop(self.error, "tone", "danger")
        self.error.setVisible(False)
        lay.addWidget(self.label)
        lay.addWidget(field)
        if hint:
            h = QLabel(hint)
            text_role(h, "caption")
            lay.addWidget(h)
        lay.addWidget(self.error)

    def set_error(self, message: str = "") -> None:
        self.error.setText(message)
        self.error.setVisible(bool(message))


class EmptyState(QWidget):
    """Centered icon + message (+ optional action button) shown instead of an empty list."""

    def __init__(self, message: str, icon_name: str = "info", action: QPushButton | None = None, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(S["md"])
        pic = QLabel()
        pic.setPixmap(icons.pixmap(icon_name, C["text_disabled"], 40))
        pic.setAlignment(Qt.AlignCenter)
        self.message = QLabel(message)
        self.message.setAlignment(Qt.AlignCenter)
        text_role(self.message, "muted")
        lay.addWidget(pic)
        lay.addWidget(self.message)
        if action is not None:
            lay.addWidget(action, 0, Qt.AlignCenter)
