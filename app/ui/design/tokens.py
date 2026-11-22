"""Design tokens: the single source for colors, spacing, radii and type sizes.

The global QSS (``qss.py``) is generated from these values; widgets reference
semantic names, never raw hex codes.
"""
from __future__ import annotations

COLORS: dict[str, str] = {
    # surfaces (cool, slightly blue-tinted greys)
    "bg": "#F4F6FB", "surface": "#FFFFFF", "surface_alt": "#EEF1F8",
    "border": "#E6E9F2", "border_strong": "#CBD2E3",
    # text (secondary text >= #5B6683 on white keeps WCAG AA)
    "text": "#0E1630", "text_body": "#1E2744", "text_muted": "#5B6683", "text_disabled": "#8F99B5",
    "text_inverse": "#FFFFFF",
    # brand / semantic
    "primary": "#3558F0", "primary_hover": "#2A47D0", "primary_pressed": "#2139B0", "primary_soft": "#E7EEFF",
    "success": "#0B7A4B", "success_hover": "#096039", "success_soft": "#E3F6EE",
    "warning": "#9A5B00", "warning_soft": "#FFF4E5",
    "danger": "#C62828", "danger_hover": "#A91F1F", "danger_soft": "#FDECEC",
    "info": "#0369A1", "info_soft": "#E8F4FB",
    # dark shell (header + sidebar)
    "header_bg": "#0E1630", "header_text": "#E6EAF8", "header_muted": "#A9B4D0", "header_chip": "#18224A",
    "sidebar_hover": "#18224A", "sidebar_category": "#8F9BC0",
    "focus": "#3558F0",
}

SPACING = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24}
RADII = {"md": 8, "lg": 12, "xl": 16}
FONT_SIZES = {"caption": 12, "body": 13, "label": 14, "title": 16, "h2": 20, "h1": 28}
CONTROL_HEIGHT = 44
FONT_FAMILY = '"Cairo", "Segoe UI", "Tajawal", "Tahoma", sans-serif'


def c(name: str) -> str:
    return COLORS[name]
