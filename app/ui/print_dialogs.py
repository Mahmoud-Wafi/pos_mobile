"""Qt printing for the POS: 80 mm receipt (preview/print/PDF) and the post-sale panel."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QMarginsF, QSizeF, Qt
from PySide6.QtGui import QGuiApplication, QPageLayout, QPageSize, QPainter, QTextDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrintPreviewDialog, QPrinter
from PySide6.QtWidgets import QDialog, QLabel, QMessageBox, QPushButton, QVBoxLayout

from app.ui.components import show_error
from app.config import DATA_DIR
from app.core.money import format_money
from app.i18n import ar
from app.printing.receipt import generate_warranty_invoice_pdf
from app.printing.thermal import MARGIN_MM, RECEIPT_WIDTH_MM, receipt_html
from app.services import settings_service
from app.ui.design.style import style_label


def _document(sale, cfg) -> QTextDocument:
    doc = QTextDocument()
    doc.setDocumentMargin(0)
    doc.setHtml(receipt_html(sale, cfg))
    return doc


def paint_receipt(printer: QPrinter, sale, cfg) -> None:
    """Lay the receipt out for an 80 mm roll: fixed width, height follows the content.

    QTextDocument works in screen pixels and is scaled to the printer when printing, so the
    layout is computed with the screen's DPI, never the printer's.
    """
    screen = QGuiApplication.primaryScreen()
    dpi = (screen.logicalDotsPerInchY() if screen else 0) or 96.0
    width_mm = int((cfg or {}).get("receipt_width_mm") or RECEIPT_WIDTH_MM)
    printable_mm = width_mm - 2 * MARGIN_MM

    doc = _document(sale, cfg)
    doc.setTextWidth(printable_mm / 25.4 * dpi)
    content_mm = doc.size().height() / dpi * 25.4
    page_mm = max(60.0, content_mm + 2 * MARGIN_MM + 4)

    printer.setPageSize(QPageSize(QSizeF(width_mm, page_mm), QPageSize.Millimeter))
    printer.setPageMargins(QMarginsF(MARGIN_MM, MARGIN_MM, MARGIN_MM, MARGIN_MM), QPageLayout.Millimeter)

    # Draw by hand onto the single page: doc.print_() re-paginates with its own scaling.
    painter = QPainter(printer)
    try:
        scale = printer.resolution() / dpi
        painter.scale(scale, scale)
        doc.drawContents(painter)
    finally:
        painter.end()


def render_receipt_pdf(sale, cfg, path: Path | str) -> Path:
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(str(path))
    paint_receipt(printer, sale, cfg)
    return Path(path)


def preview_receipt(sale, cfg, parent=None) -> None:
    printer = QPrinter(QPrinter.HighResolution)
    dlg = QPrintPreviewDialog(printer, parent)
    dlg.paintRequested.connect(lambda p: paint_receipt(p, sale, cfg))
    dlg.exec()


def print_receipt(sale, cfg, parent=None) -> bool:
    """Straight to the configured receipt printer when 'print directly' is on; otherwise the system dialog
    (pre-selected on the configured printer)."""
    from app.ui import hardware

    printer = hardware.make_printer(cfg.get("receipt_printer", ""))
    if cfg.get("receipt_direct") == "1" and cfg.get("receipt_printer"):
        paint_receipt(printer, sale, cfg)
        return True
    dlg = QPrintDialog(printer, parent)
    if dlg.exec() != QDialog.Accepted:
        return False
    paint_receipt(printer, sale, cfg)
    return True


def open_file(path: Path | str) -> None:
    if sys.platform.startswith("win"):
        os.startfile(str(path))          # noqa: S606 - local file the app just created
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def make_invoice_pdf(session, sale) -> Path:
    cfg = settings_service.get_all(session)
    dest = DATA_DIR / "invoices" / f"{sale.invoice_no}.pdf"
    return generate_warranty_invoice_pdf(
        sale, dest, shop_name=cfg["shop_name"], warranty_text=cfg["warranty_text"],
        shop_phone=cfg["shop_phone"], shop_address=cfg["shop_address"], footer=cfg["invoice_footer"])


class SaleCompleteDialog(QDialog):
    """Shown after a sale is posted. Enter = new sale; buttons print / preview / A4 PDF."""

    def __init__(self, session, sale, parent=None):
        super().__init__(parent)
        self.session, self.sale = session, sale
        self.cfg = settings_service.get_all(session)
        self.setWindowTitle(ar.SALE_DONE_TITLE)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumWidth(400)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(10)
        title = QLabel(f"{ar.SALE_DONE_TITLE}\n{ar.SALE_DONE_INVOICE}: {sale.invoice_no}")
        title.setAlignment(Qt.AlignCenter)
        style_label(title, size="title", tone="success", bold=True)
        total = QLabel(f"{ar.SALE_DONE_TOTAL}: {format_money(sale.total)}   |   {ar.SALE_DONE_CHANGE_NOTE}: {format_money(sale.paid)}")
        total.setAlignment(Qt.AlignCenter)
        root.addWidget(title)
        root.addWidget(total)

        for text, slot in ((ar.PRINT_RECEIPT, self.print_receipt), (ar.PRINT_PREVIEW, self.preview),
                           (ar.PRINT_A4, self.open_a4)):
            b = QPushButton(text)
            b.setMinimumHeight(40)
            b.setAutoDefault(False)
            b.clicked.connect(slot)
            root.addWidget(b)
        done = QPushButton(ar.PRINT_NEW_SALE + "  [Enter]")
        done.setObjectName("PrimaryBtn")
        done.setMinimumHeight(44)
        done.setDefault(True)
        done.clicked.connect(self.accept)
        root.addWidget(done)

    def _safe(self, fn) -> None:
        try:
            fn()
        except Exception as exc:
            show_error(self, exc)

    def print_receipt(self) -> None:
        self._safe(lambda: print_receipt(self.sale, self.cfg, self))

    def preview(self) -> None:
        self._safe(lambda: preview_receipt(self.sale, self.cfg, self))

    def open_a4(self) -> None:
        self._safe(lambda: open_file(make_invoice_pdf(self.session, self.sale)))
