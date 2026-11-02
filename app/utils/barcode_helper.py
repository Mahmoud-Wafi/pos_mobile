"""Barcode generation helper.

Wraps python-barcode. Falls back gracefully if library is unavailable.
Saves barcode as SVG (vector, printable) or PNG (with Pillow).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


def generate_barcode_svg(value: str, dest_dir: Path, filename: Optional[str] = None) -> Path:
    """Generate a Code128 barcode SVG for *value*.

    Returns path to the saved file.
    """
    try:
        import barcode
        from barcode.writer import SVGWriter

        dest_dir.mkdir(parents=True, exist_ok=True)
        fname = filename or f"barcode_{value}"
        code = barcode.get("code128", value, writer=SVGWriter())
        full_path = dest_dir / fname
        saved = code.save(str(full_path))
        return Path(saved)
    except ImportError:
        raise RuntimeError("python-barcode غير مثبت. قم بتثبيته: pip install python-barcode")


def generate_barcode_png(value: str, dest_dir: Path, filename: Optional[str] = None) -> Path:
    """Generate a Code128 barcode PNG (requires Pillow)."""
    try:
        import barcode
        from barcode.writer import ImageWriter

        dest_dir.mkdir(parents=True, exist_ok=True)
        fname = filename or f"barcode_{value}"
        code = barcode.get("code128", value, writer=ImageWriter())
        full_path = dest_dir / fname
        saved = code.save(str(full_path))
        return Path(saved)
    except ImportError:
        raise RuntimeError("python-barcode أو Pillow غير مثبت")

