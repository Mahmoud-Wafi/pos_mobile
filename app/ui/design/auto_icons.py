"""Gives text buttons a Lucide icon from keywords in their label (icon is added when the button is shown)."""
from __future__ import annotations
from app.i18n import ar

from PySide6.QtCore import QEvent, QObject, QSize
from PySide6.QtWidgets import QPushButton

from app.ui.design import icons
from app.ui.design.tokens import COLORS as C

# first match wins
KEYWORDS: list[tuple[str, str]] = [
    (ar.DELETE, "trash-2"), (ar.AUTO_ICONS_EC2CE8, "trash-2"), (ar.AUTO_ICONS_399328, "trash-2"),
    (ar.AUTO_ICONS_88C5D1, "printer"), (ar.AUTO_ICONS_0D4DE2, "eye"), (ar.SEARCH, "search"),
    (ar.REFRESH, "rotate-cw"), (ar.EDIT, "pencil"), (ar.AUTO_ICONS_0215AF, "pause"), (ar.HELD_RESUME, "play"),
    (ar.CANCEL, "x"), (ar.CLOSE, "x"), (ar.SAVE, "save"), (ar.AUTO_ICONS_C9276C, "save"),
    (ar.CONFIRM, "check"), (ar.APPROVAL_GRANT, "check"), (ar.AUTO_ICONS_51CC4E, "check"), (ar.AUTO_ICONS_0B0845, "banknote"), (ar.CUSTOMERS_WINDOW_369D90, "banknote"),
    (ar.AUTO_ICONS_E4D731, "download"), (ar.AUTO_ICONS_37A021, "upload"), (ar.AUTO_ICONS_58F836, "database"),
    (ar.AUTO_ICONS_B9508A, "plus"), (ar.DEVICE_CONDITION_NEW, "plus"), ("+", "plus"),
]
_DARK_VARIANTS = {"primary", "success", "danger"}


def icon_for(text: str) -> str | None:
    for kw, name in KEYWORDS:
        if kw in text:
            return name
    return None


class AutoIcons(QObject):
    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Show and isinstance(obj, QPushButton) and obj.text() and not obj.toolTip():
            obj.setToolTip(obj.text().split("[")[0].strip())
        if ev.type() == QEvent.Show and isinstance(obj, QPushButton) and obj.icon().isNull() \
                and obj.text() and obj.property("nav") is None and obj.property("no_icon") is None:
            name = icon_for(obj.text())
            if name:
                dark = obj.property("variant") in _DARK_VARIANTS or obj.objectName() == "PrimaryBtn"
                obj.setIcon(icons.icon(name, C["text_inverse"] if dark else C["text_muted"]))
                obj.setIconSize(QSize(18, 18))
        return False
