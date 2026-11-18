"""Helpers for the property-driven styling used by the global QSS."""
from __future__ import annotations

from PySide6.QtWidgets import QWidget


def set_prop(w: QWidget, name: str, value) -> QWidget:
    """Set a dynamic property and re-evaluate the stylesheet for the widget."""
    w.setProperty(name, value)
    st = w.style()
    st.unpolish(w)
    st.polish(w)
    w.update()
    return w


def variant(w: QWidget, name: str) -> QWidget:
    return set_prop(w, "variant", name)


def text_role(w: QWidget, name: str) -> QWidget:
    return set_prop(w, "text_role", name)


def tone(w: QWidget, name: str) -> QWidget:
    return set_prop(w, "tone", name)


def style_label(w: QWidget, size: str | None = None, tone: str | None = None, bold: bool = False) -> QWidget:
    """Typed replacement for inline label styles: size role + colour tone + bold."""
    if size:
        w.setProperty("size", size)
    if tone:
        w.setProperty("tone", tone)
    if bold:
        w.setProperty("bold", True)
    st = w.style()
    st.unpolish(w)
    st.polish(w)
    return w
