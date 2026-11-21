"""Settings tab: receipt printer, label printer and barcode reader — each set up on its own."""
from __future__ import annotations

from PySide6.QtCore import QMarginsF, QSizeF, Qt
from PySide6.QtGui import QFont, QPageLayout, QPageSize, QPainter
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from app.i18n import ar
from app.printing.labels import LabelSpec
from app.services import settings_service
from app.ui import hardware
from app.ui.components import show_error, show_toast
from app.ui.components.numeric import set_int_validator
from app.ui.design.style import style_label, variant


class HardwareTab(QWidget):
    KEYS = ("receipt_printer", "receipt_direct", "receipt_width_mm", "label_printer", "label_direct",
            "label_width_mm", "label_height_mm")

    def __init__(self, session, user, parent=None):
        super().__init__(parent)
        self.session, self.user = session, user
        self.setLayoutDirection(Qt.RightToLeft)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(16)

        self.lbl_printers = QLabel("")
        style_label(self.lbl_printers, size="caption", tone="muted")
        root.addWidget(self.lbl_printers)

        # receipt printer
        g1 = QGroupBox(ar.HW_RECEIPT_GROUP)
        f1 = QFormLayout(g1)
        self.receipt_printer = QComboBox()
        self.receipt_direct = QCheckBox(ar.HW_DIRECT)
        self.receipt_width = QComboBox()
        self.receipt_width.addItem("80 mm", "80")
        self.receipt_width.addItem("58 mm", "58")
        self.btn_test_receipt = QPushButton(ar.HW_TEST_PRINT)
        self.btn_test_receipt.clicked.connect(self.test_receipt)
        f1.addRow(ar.HW_PRINTER, self.receipt_printer)
        f1.addRow(ar.HW_PAPER_WIDTH, self.receipt_width)
        f1.addRow("", self.receipt_direct)
        f1.addRow("", self.btn_test_receipt)
        root.addWidget(g1)

        # label printer
        g2 = QGroupBox(ar.HW_LABEL_GROUP)
        f2 = QFormLayout(g2)
        self.label_printer = QComboBox()
        self.label_direct = QCheckBox(ar.HW_DIRECT)
        self.label_w, self.label_h = QLineEdit(), QLineEdit()
        for e in (self.label_w, self.label_h):
            e.setFixedHeight(38)
            set_int_validator(e, 15, 120)
        self.btn_test_label = QPushButton(ar.HW_TEST_PRINT)
        self.btn_test_label.clicked.connect(self.test_label)
        f2.addRow(ar.HW_PRINTER, self.label_printer)
        f2.addRow(ar.HW_LABEL_WIDTH, self.label_w)
        f2.addRow(ar.HW_LABEL_HEIGHT, self.label_h)
        f2.addRow("", self.label_direct)
        f2.addRow("", self.btn_test_label)
        root.addWidget(g2)

        # barcode reader
        g3 = QGroupBox(ar.HW_SCANNER_GROUP)
        v3 = QVBoxLayout(g3)
        help_lbl = QLabel(ar.HW_SCANNER_HELP)
        help_lbl.setWordWrap(True)
        style_label(help_lbl, size="caption", tone="muted")
        v3.addWidget(help_lbl)
        self.scanner_test = QLineEdit()
        self.scanner_test.setFixedHeight(42)
        self.scanner_test.setPlaceholderText(ar.HW_SCANNER_PLACEHOLDER)
        self.scanner_test.returnPressed.connect(self._scanner_read)
        self.scanner_result = QLabel(ar.HW_SCANNER_EMPTY)
        style_label(self.scanner_result, tone="muted", bold=True)
        v3.addWidget(self.scanner_test)
        v3.addWidget(self.scanner_result)
        root.addWidget(g3)

        for form in (f1, f2):
            form.setVerticalSpacing(14)
            form.setLabelAlignment(Qt.AlignRight)
        for w in (self.receipt_printer, self.receipt_width, self.label_printer, self.label_w, self.label_h):
            w.setFixedHeight(42)
        for w in (self.receipt_direct, self.label_direct):
            w.setMinimumHeight(30)
        for w in (self.btn_test_receipt, self.btn_test_label):
            w.setFixedHeight(42)

        bar = QHBoxLayout()
        self.btn_refresh = QPushButton(ar.HW_REFRESH)
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_save = QPushButton(ar.HW_SAVE)
        variant(self.btn_save, "primary")
        self.btn_save.setMinimumHeight(42)
        self.btn_save.clicked.connect(self.save)
        bar.addWidget(self.btn_save)
        bar.addWidget(self.btn_refresh)
        bar.addStretch()
        root.addLayout(bar)
        root.addStretch()
        self.refresh()

    # ── data ──
    def _fill(self, combo: QComboBox, names: list[str], current: str) -> None:
        combo.clear()
        combo.addItem(ar.HW_ASK_EVERY_TIME, "")
        for n in names:
            combo.addItem(n, n)
        idx = combo.findData(current)
        if idx < 0 and current:                      # saved printer is currently not installed: keep it visible
            combo.addItem(ar.HW_OFFLINE.format(current), current)
            idx = combo.count() - 1
        combo.setCurrentIndex(max(idx, 0))

    def refresh(self) -> None:
        cfg = settings_service.get_all(self.session)
        names = hardware.list_printers()
        self.lbl_printers.setText("" if names else ar.HW_NO_PRINTERS)
        self._fill(self.receipt_printer, names, cfg["receipt_printer"])
        self._fill(self.label_printer, names, cfg["label_printer"])
        self.receipt_direct.setChecked(cfg["receipt_direct"] == "1")
        self.label_direct.setChecked(cfg["label_direct"] == "1")
        self.receipt_width.setCurrentIndex(max(0, self.receipt_width.findData(cfg["receipt_width_mm"])))
        self.label_w.setText(cfg["label_width_mm"])
        self.label_h.setText(cfg["label_height_mm"])

    def values(self) -> dict[str, str]:
        return {
            "receipt_printer": self.receipt_printer.currentData() or "",
            "receipt_direct": "1" if self.receipt_direct.isChecked() else "0",
            "receipt_width_mm": self.receipt_width.currentData() or "80",
            "label_printer": self.label_printer.currentData() or "",
            "label_direct": "1" if self.label_direct.isChecked() else "0",
            "label_width_mm": self.label_w.text() or "50",
            "label_height_mm": self.label_h.text() or "30",
        }

    def save(self) -> None:
        try:
            settings_service.update(self.session, self.user, self.values())
            self.session.commit()
        except Exception as exc:  # noqa: BLE001
            self.session.rollback()
            show_error(self, exc)
            return
        show_toast(self, ar.HW_SAVED)

    # ── tests ──
    def test_receipt(self) -> None:
        cfg = {**settings_service.get_all(self.session), **self.values()}
        try:
            printer = hardware.make_printer(cfg["receipt_printer"])
            width = float(cfg["receipt_width_mm"])
            printer.setPageSize(QPageSize(QSizeF(width, 60), QPageSize.Millimeter))
            printer.setPageMargins(QMarginsF(3, 3, 3, 3), QPageLayout.Millimeter)
            painter = QPainter(printer)
            try:
                painter.setFont(QFont("Cairo", 11))
                rect = painter.viewport()
                painter.drawText(rect, Qt.AlignHCenter | Qt.TextWordWrap,
                                 ar.HW_TEST_RECEIPT_TEXT.format(cfg['shop_name'], width))
            finally:
                painter.end()
        except Exception as exc:  # noqa: BLE001
            show_error(self, exc)
            return
        show_toast(self, ar.HW_TEST_DONE)

    def test_label(self) -> None:
        cfg = {**settings_service.get_all(self.session), **self.values()}
        try:
            hardware.print_labels([LabelSpec(ar.HW_TEST_LABEL_NAME, "123456789012", ar.HW_TEST_LABEL_PRICE)], cfg)
        except Exception as exc:  # noqa: BLE001
            show_error(self, exc)
            return
        show_toast(self, ar.HW_TEST_DONE)

    def _scanner_read(self) -> None:
        code = self.scanner_test.text().strip()
        self.scanner_result.setText(ar.HW_SCANNER_OK.format(code, len(code)) if code else ar.HW_SCANNER_EMPTY)
        self.scanner_test.clear()
