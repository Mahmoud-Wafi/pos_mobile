"""DataTable: a QTableWidget with the project defaults and an empty-state message."""
from __future__ import annotations

from typing import Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHeaderView, QLabel, QTableWidget, QTableWidgetItem

from app.ui.design.style import text_role


class DataTable(QTableWidget):
    def __init__(self, headers: Sequence[str], empty_text: str = "", parent=None):
        super().__init__(0, len(headers), parent)
        self.setHorizontalHeaderLabels(list(headers))
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(44)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.SingleSelection)
        self.setAlternatingRowColors(True)
        self.setLayoutDirection(Qt.RightToLeft)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._empty = QLabel(empty_text, self)
        self._empty.setAlignment(Qt.AlignCenter)
        text_role(self._empty, "muted")
        self._empty.setVisible(False)
        self._empty_text = empty_text

    def set_rows(self, rows: Sequence[Sequence[str]], aligns: Sequence[Qt.AlignmentFlag] | None = None) -> None:
        self.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                it = QTableWidgetItem(str(val))
                it.setTextAlignment(aligns[c] if aligns else Qt.AlignCenter)
                self.setItem(r, c, it)
        self._empty.setVisible(not rows and bool(self._empty_text))
        self._place_empty()

    def selected_row(self) -> int:
        rows = self.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place_empty()

    def _place_empty(self) -> None:
        self._empty.setGeometry(0, self.horizontalHeader().height(), self.viewport().width(), 80)
