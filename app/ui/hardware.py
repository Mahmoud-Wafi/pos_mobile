"""Printers and barcode reader helpers shared by the POS, inventory labels and the hardware settings tab."""
from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QSizeF

from app.i18n import ar
from PySide6.QtGui import QImage, QPainter
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo


def list_printers() -> list[str]:
    return list(QPrinterInfo.availablePrinterNames())


def default_printer() -> str:
    return QPrinterInfo.defaultPrinterName() or ""


def make_printer(name: str = "") -> QPrinter:
    """A QPrinter bound to ``name`` when that printer is installed, else the system default."""
    if name and name in list_printers():
        return QPrinter(QPrinterInfo.printerInfo(name), QPrinter.HighResolution)
    return QPrinter(QPrinter.HighResolution)


def print_pdf(pdf_path: Path | str, printer: QPrinter, width_mm: float, height_mm: float) -> int:
    """Print every page of a PDF (one label per page) on ``printer``. Returns the number of pages."""
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtCore import QMarginsF
    from PySide6.QtGui import QPageLayout, QPageSize

    doc = QPdfDocument()
    if doc.load(str(pdf_path)) != QPdfDocument.Error.None_:
        raise RuntimeError(ar.HW_ERR_PDF)
    printer.setPageSize(QPageSize(QSizeF(width_mm, height_mm), QPageSize.Millimeter))
    printer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Millimeter)
    dpi = printer.resolution() or 300
    px_w, px_h = int(width_mm / 25.4 * dpi), int(height_mm / 25.4 * dpi)
    painter = QPainter()
    if not painter.begin(printer):
        raise RuntimeError(ar.HW_ERR_PRINTER)
    try:
        for page in range(doc.pageCount()):
            if page:
                printer.newPage()
            img: QImage = doc.render(page, QSizeF(px_w, px_h).toSize())
            painter.drawImage(0, 0, img)
    finally:
        painter.end()
    return doc.pageCount()


def print_labels(specs, cfg: dict[str, str]) -> int:
    """Render the labels at the configured size and send them to the configured label printer."""
    from app.printing.labels import make_labels_pdf

    w, h = float(cfg.get("label_width_mm") or 50), float(cfg.get("label_height_mm") or 30)
    tmp = Path(tempfile.gettempdir()) / "pos_labels_print.pdf"
    make_labels_pdf(specs, tmp, w, h)
    return print_pdf(tmp, make_printer(cfg.get("label_printer", "")), w, h)


def output_labels(parent, session, specs) -> None:
    """Print labels directly when a label printer is set to 'direct'; otherwise ask where to save the PDF."""
    from PySide6.QtWidgets import QFileDialog

    from app.i18n import ar
    from app.printing.labels import make_labels_pdf
    from app.services import settings_service
    from app.ui.components import show_error, show_toast

    cfg = settings_service.get_all(session)
    try:
        if cfg.get("label_direct") == "1" and cfg.get("label_printer"):
            n = print_labels(specs, cfg)
            show_toast(parent, ar.LABEL_PRINTED.format(n))
            return
        dest, _ = QFileDialog.getSaveFileName(parent, ar.LABEL_SAVE_TITLE, "labels.pdf", "PDF (*.pdf)")
        if not dest:
            return
        make_labels_pdf(specs, dest, float(cfg.get("label_width_mm") or 50), float(cfg.get("label_height_mm") or 30))
        show_toast(parent, ar.LABEL_SAVED)
    except Exception as exc:  # noqa: BLE001 - shown as an Arabic message
        show_error(parent, exc)
