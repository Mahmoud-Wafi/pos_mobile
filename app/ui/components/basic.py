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
    """Label + big value (+ optional hint). Update with set_value().

    ``icon`` (a Lucide name) adds a tinted chip; ``tone`` colours it: primary|success|warning|violet|info.
    """

    _TONE_COLOR = {"primary": "primary", "success": "success", "warning": "warning", "violet": "violet", "info": "info"}

    def __init__(self, title: str, value: str = "—", hint: str = "", parent=None, icon: str | None = None, tone: str = "primary"):
        super().__init__(parent)
        set_prop(self, "kpi", True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(S["lg"], S["lg"], S["lg"], S["lg"])
        lay.setSpacing(S["sm"])
        self.title_lbl = QLabel(title)
        text_role(self.title_lbl, "muted")
        self.value_lbl = QLabel(value)
        text_role(self.value_lbl, "money")
        self.hint_lbl = QLabel(hint)
        text_role(self.hint_lbl, "caption")
        self.hint_lbl.setVisible(bool(hint))
        top = QHBoxLayout()
        top.addWidget(self.title_lbl, 1)
        if icon:
            from app.ui.design import icons
            chip = QLabel()
            chip.setAlignment(Qt.AlignCenter)
            chip.setProperty("chip", tone)
            chip.setPixmap(icons.pixmap(icon, C[self._TONE_COLOR.get(tone, "primary")], 20))
            top.addWidget(chip)
        lay.addLayout(top)
        lay.addWidget(self.value_lbl)
        lay.addWidget(self.hint_lbl)

    def set_value(self, value: str, hint: str | None = None, trend: str | None = None) -> None:
        """``trend``: "up" (green), "down" (red) or None (muted) colours the hint line."""
        self.value_lbl.setText(value)
        if hint is not None:
            self.hint_lbl.setText(hint)
            self.hint_lbl.setVisible(bool(hint))
        tone = {"up": "success", "down": "danger"}.get(trend or "", "muted")
        self.hint_lbl.setProperty("text_role", None)
        self.hint_lbl.setProperty("tone", tone)
        self.hint_lbl.setProperty("size", "caption")
        self.hint_lbl.setProperty("bold", True)
        st = self.hint_lbl.style()
        st.unpolish(self.hint_lbl)
        st.polish(self.hint_lbl)


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


def attach_imei_check(edit: QLineEdit, required: bool = True) -> None:
    """On blur: show ✓ (valid Luhn) or ✗ with a red border and tooltip. Never blocks typing."""
    from PySide6.QtGui import QAction, QIcon

    from app.core.imei import luhn_valid, normalize_imei

    action = QAction(edit)
    good, bad = icons.icon("circle-check", C["success"]), icons.icon("x", C["danger"])
    edit.addAction(action, QLineEdit.TrailingPosition)

    def check() -> None:
        raw = edit.text().strip()
        if not raw:
            ok, mark, tip = (not required), None, ""
            if required:
                tip = ar.VALID_REQUIRED
        else:
            try:
                ok = luhn_valid(normalize_imei(raw))
            except Exception:  # noqa: BLE001 - malformed input is simply invalid
                ok = False
            mark, tip = (good, "") if ok else (bad, ar.VALID_IMEI)
        action.setIcon(mark if mark is not None else QIcon())
        edit.setToolTip(tip)
        set_prop(edit, "invalid", "false" if ok else "true")

    edit.editingFinished.connect(check)
    edit.textEdited.connect(lambda _t: set_prop(edit, "invalid", "false"))
