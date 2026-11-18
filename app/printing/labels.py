"""Barcode label sheets (one label per page) for a label printer, as PDF.

Default size 50 x 30 mm. Code 128 barcodes come from reportlab itself (works offline).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from reportlab.graphics.barcode import code128
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from app.printing.pdf_common import FONT, FONT_BOLD, register_fonts, shape


@dataclass(frozen=True)
class LabelSpec:
    name: str            # product name (Arabic or Latin)
    code: str            # what the barcode encodes (barcode, or IMEI)
    price_text: str = ""  # already formatted, e.g. "1,500.00 ج.م"; empty on IMEI labels
    caption: str = ""    # small extra line (e.g. condition)


def _fit(text: str, font: str, size: float, max_width: float) -> float:
    while size > 5 and pdfmetrics.stringWidth(text, font, size) > max_width:
        size -= 0.5
    return size


def make_labels_pdf(specs: list[LabelSpec], path: Path | str, width_mm: float = 50, height_mm: float = 30) -> Path:
    """Write one page per label. Raises ValueError for an empty list or an empty barcode value."""
    if not specs:
        raise ValueError("no labels")
    register_fonts()
    w, h = width_mm * mm, height_mm * mm
    c = canvas.Canvas(str(path), pagesize=(w, h))
    pad = 2 * mm
    for spec in specs:
        if not spec.code.strip():
            raise ValueError("empty barcode value")
        y = h - pad
        name = shape(spec.name)
        size = _fit(name, FONT_BOLD, 8, w - 2 * pad)
        c.setFont(FONT_BOLD, size)
        c.drawCentredString(w / 2, y - size, name)
        y -= size * 1.35
        if spec.price_text:
            price = shape(spec.price_text)
            c.setFont(FONT_BOLD, 9)
            c.drawCentredString(w / 2, y - 9, price)
            y -= 11
        if spec.caption:
            cap = shape(spec.caption)
            c.setFont(FONT, 6)
            c.drawCentredString(w / 2, y - 6, cap)
            y -= 7
        bar_h = max(5 * mm, y - pad - 8 - 4)
        bc = code128.Code128(spec.code, barHeight=bar_h, barWidth=0.33 * mm, quiet=False)
        if bc.width > w - 2 * pad:                      # long codes (IMEI): narrow the bars
            bc = code128.Code128(spec.code, barHeight=bar_h, barWidth=(w - 2 * pad) / bc.width * 0.33 * mm,
                                 quiet=False)
        bc.drawOn(c, (w - bc.width) / 2, pad + 8)
        c.setFont(FONT, 6.5)
        c.drawCentredString(w / 2, pad + 1, spec.code)
        c.showPage()
    c.save()
    return Path(path)
