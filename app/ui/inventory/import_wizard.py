"""Import wizard: choose what to import and the file -> preview with per-row errors -> confirm."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget,
)

from app.i18n import ar
from app.services import import_export_service as ie
from app.ui.components import DataTable, button, show_error, show_toast
from app.ui.design.style import text_role

KINDS = [("products", ar.IMPORT_KIND_PRODUCTS), ("devices", ar.IMPORT_KIND_DEVICES)]


class ImportWizard(QDialog):
    def __init__(self, session, user, kind: str = "products", parent=None):
        super().__init__(parent)
        self.session, self.user = session, user
        self.preview: ie.ImportPreview | None = None
        self.imported = 0
        self.setWindowTitle(ar.IMPORT_TITLE)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumSize(760, 520)
        root = QVBoxLayout(self)
        self.steps = QStackedWidget()
        root.addWidget(self.steps, 1)
        self._build_pick(kind)
        self._build_preview()
        self.steps.setCurrentIndex(0)

    # step 1 ────────────────────────────────────────────────────────────
    def _build_pick(self, kind: str) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        title = QLabel(ar.IMPORT_STEP1)
        text_role(title, "title")
        lay.addWidget(title)
        self.kind_combo = QComboBox()
        for key, label in KINDS:
            self.kind_combo.addItem(label, key)
        self.kind_combo.setCurrentIndex(max(0, [k for k, _ in KINDS].index(kind)))
        lay.addWidget(self.kind_combo)
        hint = QLabel(ar.IMPORT_HINT)
        hint.setWordWrap(True)
        text_role(hint, "muted")
        lay.addWidget(hint)
        row = QHBoxLayout()
        self.btn_template = button(ar.IMPORT_TEMPLATE, "secondary", "download")
        self.btn_template.clicked.connect(self.save_template)
        self.btn_file = button(ar.IMPORT_CHOOSE_FILE, "primary", "upload")
        self.btn_file.clicked.connect(self.choose_file)
        row.addWidget(self.btn_template)
        row.addWidget(self.btn_file)
        row.addStretch()
        lay.addLayout(row)
        lay.addStretch()
        self.steps.addWidget(w)

    def save_template(self) -> None:
        kind = self.kind_combo.currentData()
        dest, _ = QFileDialog.getSaveFileName(self, ar.IMPORT_TEMPLATE, f"template_{kind}.xlsx", "Excel (*.xlsx)")
        if dest:
            try:
                ie.write_template(kind, dest)
                show_toast(self, ar.EXPORT_DONE)
            except Exception as exc:
                show_error(self, exc)

    def choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, ar.IMPORT_CHOOSE_FILE, "", "Excel / CSV (*.xlsx *.csv)")
        if path:
            self.load_file(path)

    def load_file(self, path: str | Path) -> None:
        kind = self.kind_combo.currentData()
        try:
            fn = ie.preview_products if kind == "products" else ie.preview_devices
            self.preview = fn(self.session, self.user, path)
        except Exception as exc:
            show_error(self, exc)
            return
        self._fill_preview()
        self.steps.setCurrentIndex(1)

    # step 2 ────────────────────────────────────────────────────────────
    def _build_preview(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.summary = QLabel()
        text_role(self.summary, "title")
        lay.addWidget(self.summary)
        self.table = DataTable([ar.IMPORT_COL_ROW, ar.IMPORT_COL_NAME, ar.IMPORT_COL_STATUS], ar.IMPORT_EMPTY)
        self.table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.btn_back = button(ar.BACK, "secondary")
        self.btn_back.clicked.connect(lambda: self.steps.setCurrentIndex(0))
        self.btn_confirm = button("", "primary", "check")
        self.btn_confirm.clicked.connect(self.confirm)
        row.addWidget(self.btn_back)
        row.addStretch()
        row.addWidget(self.btn_confirm)
        lay.addLayout(row)
        self.steps.addWidget(w)

    def _fill_preview(self) -> None:
        p = self.preview
        self.summary.setText(ar.IMPORT_SUMMARY.format(ok=len(p.valid), bad=len(p.invalid)))
        rows = []
        for r in p.rows:
            label = r.data.get("name") or r.data.get("imei1") or "—"
            if r.errors:
                status = "✗ " + " • ".join(r.errors)
            elif r.warnings:
                status = "! " + " • ".join(r.warnings)
            else:
                status = "✓"
            rows.append([r.row_no, label, status])
        self.table.set_rows(rows, [Qt.AlignCenter, Qt.AlignRight | Qt.AlignVCenter, Qt.AlignRight | Qt.AlignVCenter])
        self.btn_confirm.setText(ar.IMPORT_CONFIRM.format(n=len(p.valid)))
        self.btn_confirm.setEnabled(bool(p.valid))

    def confirm(self) -> None:
        if not self.preview or not self.preview.valid:
            return
        fn = ie.commit_products if self.preview.kind == "products" else ie.commit_devices
        try:
            self.imported = fn(self.session, self.user, self.preview)
            self.session.commit()
        except Exception as exc:
            self.session.rollback()
            show_error(self, exc)
            return
        show_toast(self, ar.IMPORT_DONE.format(n=self.imported))
        self.accept()
