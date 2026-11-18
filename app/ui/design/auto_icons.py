"""Gives text buttons a Lucide icon from keywords in their label (icon is added when the button is shown)."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QSize
from PySide6.QtWidgets import QPushButton

from app.ui.design import icons
from app.ui.design.tokens import COLORS as C

# first match wins
KEYWORDS: list[tuple[str, str]] = [
    ("حذف", "trash-2"), ("مسح", "trash-2"), ("تفريغ", "trash-2"),
    ("طباعة", "printer"), ("معاينة", "eye"), ("بحث", "search"),
    ("تحديث", "rotate-cw"), ("تعديل", "pencil"), ("تعليق", "pause"), ("استرجاع", "play"),
    ("إلغاء", "x"), ("إغلاق", "x"), ("حفظ", "save"), ("تسجيل", "save"),
    ("تأكيد", "check"), ("موافقة", "check"), ("اعتماد", "check"), ("دفع", "banknote"), ("تحصيل", "banknote"),
    ("تصدير", "download"), ("استيراد", "upload"), ("نسخة", "database"),
    ("إضافة", "plus"), ("جديد", "plus"), ("+", "plus"),
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
