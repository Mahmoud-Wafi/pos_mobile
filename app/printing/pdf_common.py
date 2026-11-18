"""Shared helpers for Arabic (RTL) PDFs: Cairo font, letter shaping, bidi, wrapping."""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from xml.sax.saxutils import escape

from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph

from app.config import BASE_DIR

FONT = "Cairo"
FONT_BOLD = "Cairo-Bold"
_ARABIC_RE = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")

TEXT_ALIGN_RIGHT = 2
TEXT_ALIGN_CENTER = 1
TEXT_ALIGN_LEFT = 0


@lru_cache(maxsize=1)
def register_fonts() -> None:
    assets = BASE_DIR / "assets"
    pdfmetrics.registerFont(TTFont(FONT, str(assets / "Cairo-Regular.ttf")))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(assets / "Cairo-Bold.ttf")))
    pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT_BOLD, italic=FONT, boldItalic=FONT_BOLD)


def has_arabic(text: str) -> bool:
    return bool(_ARABIC_RE.search(text or ""))


def _supported_codepoints() -> set[int]:
    register_fonts()
    return set(pdfmetrics.getFont(FONT).face.charToGlyph)


@lru_cache(maxsize=1)
def _supported() -> frozenset[int]:
    return frozenset(_supported_codepoints())


def _fill_missing_forms(text: str) -> str:
    """Cairo has no glyph for a few isolated presentation forms (e.g. U+FE8D alef);
    the plain base letter looks identical, so fall back to it instead of printing a blank box."""
    have = _supported()
    out = []
    for ch in text:
        if ord(ch) in have or ch.isspace():
            out.append(ch)
            continue
        base = unicodedata.normalize("NFKC", ch)
        out.append(base if base != ch and all(ord(c) in have for c in base) else ch)
    return "".join(out)


def shape(text: str) -> str:
    """Join Arabic letters and put the line in visual (RTL) order. Latin-only text is unchanged."""
    text = text or ""
    if not has_arabic(text):
        return text
    import arabic_reshaper
    from bidi.algorithm import get_display

    return get_display(_fill_missing_forms(arabic_reshaper.reshape(text)))


def style(name: str = "base", size: float = 10, bold: bool = False, align: int = TEXT_ALIGN_RIGHT,
          color: str = "#1E293B", leading: float | None = None) -> ParagraphStyle:
    register_fonts()
    return ParagraphStyle(
        name, fontName=FONT_BOLD if bold else FONT, fontSize=size,
        leading=leading or size * 1.7, alignment=align, textColor=color,
    )


def para(text: str, st: ParagraphStyle, width: float | None = None) -> Paragraph:
    """RTL-correct paragraph. Long text is wrapped logically first, then each line is shaped,
    so lines break in the right places (shaping a whole paragraph would reverse line order)."""
    register_fonts()
    text = str(text if text is not None else "")
    if width and has_arabic(text):
        lines = []
        for chunk in text.split("\n"):
            lines.extend(simpleSplit(chunk, st.fontName, st.fontSize, width * 0.96) or [""])
        body = "<br/>".join(escape(shape(line)) for line in lines)
    else:
        body = "<br/>".join(escape(shape(line)) for line in text.split("\n"))
    return Paragraph(body, st)


def rtl_row(cells: list) -> list:
    """Tables are laid out left-to-right; an RTL row lists its first logical column on the right."""
    return list(reversed(cells))


def ltr(text: str) -> str:
    """Keep dates/times in left-to-right order inside an Arabic line (the bidi step strips the markers)."""
    return "\u202a" + text + "\u202c"
