"""Design tokens: the single source for colors, spacing, radii and type sizes.

The global QSS (``qss.py``) is generated from these values; widgets reference
semantic names, never raw hex codes.
"""
from __future__ import annotations

COLORS: dict[str, str] = {
    # surfaces
    "bg": "#F8FAFC", "surface": "#FFFFFF", "surface_alt": "#F1F5F9",
    "border": "#E2E8F0", "border_strong": "#CBD5E1",
    # text (secondary text >= #64748B on white keeps WCAG AA)
    "text": "#0F172A", "text_body": "#1E293B", "text_muted": "#64748B", "text_disabled": "#94A3B8",
    "text_inverse": "#FFFFFF",
    # brand / semantic
    "primary": "#2563EB", "primary_hover": "#1D4ED8", "primary_pressed": "#1E40AF", "primary_soft": "#EFF6FF",
    "success": "#047857", "success_hover": "#065F46", "success_soft": "#ECFDF5",
    "warning": "#B45309", "warning_soft": "#FFFBEB",
    "danger": "#DC2626", "danger_hover": "#B91C1C", "danger_soft": "#FEF2F2",
    "info": "#0369A1", "info_soft": "#F0F9FF",
    # shell
    "header_bg": "#0F172A", "header_text": "#E2E8F0", "header_muted": "#94A3B8", "header_chip": "#1E293B",
    "focus": "#2563EB",
}

SPACING = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24}
RADII = {"md": 8, "lg": 12}
FONT_SIZES = {"caption": 12, "body": 13, "label": 14, "title": 16, "h2": 20, "h1": 28}
CONTROL_HEIGHT = 40
FONT_FAMILY = '"Cairo", "Segoe UI", "Tajawal", "Tahoma", sans-serif'


def c(name: str) -> str:
    return COLORS[name]
