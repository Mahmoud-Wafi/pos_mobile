"""Applies the shared table conventions to every QTableWidget when it is first shown.

* rows at least 40 px high, alternating colours
* column widths remembered per table (stored in DATA_DIR/ui.ini)
* sortable headers when the table opts in (``setProperty("sortable", True)``)
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QSettings, Qt
from PySide6.QtWidgets import QHeaderView, QTableWidget, QWidget

from app.config import DATA_DIR

MIN_ROW_HEIGHT = 44


def _settings() -> QSettings:
    return QSettings(str(DATA_DIR / "ui.ini"), QSettings.IniFormat)


def table_key(table: QTableWidget) -> str:
    owner = table.window().__class__.__name__ if table.window() is not table else "root"
    parent = table.parentWidget().__class__.__name__ if table.parentWidget() else "none"
    return f"tables/{owner}.{parent}.{table.objectName() or table.columnCount()}"


def apply_defaults(table: QTableWidget) -> None:
    vh = table.verticalHeader()
    vh.setMinimumSectionSize(40)
    if vh.defaultSectionSize() < 40:
        vh.setDefaultSectionSize(MIN_ROW_HEIGHT)
    table.setAlternatingRowColors(True)
    hh = table.horizontalHeader()
    if table.property("sortable"):
        table.setSortingEnabled(True)
        hh.setSortIndicatorShown(True)
        hh.setSectionsClickable(True)
    _restore_widths(table)
    hh.sectionResized.connect(lambda *_: _save_widths(table))


def _restore_widths(table: QTableWidget) -> None:
    st, key = _settings(), table_key(table)
    hh = table.horizontalHeader()
    for col in range(table.columnCount()):
        w = st.value(f"{key}/{col}")
        if w and hh.sectionResizeMode(col) in (QHeaderView.Interactive, QHeaderView.Fixed):
            try:
                table.setColumnWidth(col, int(w))
            except (TypeError, ValueError):
                pass


def _save_widths(table: QTableWidget) -> None:
    if not table.isVisible():
        return
    st, key = _settings(), table_key(table)
    hh = table.horizontalHeader()
    for col in range(table.columnCount()):
        if hh.sectionResizeMode(col) in (QHeaderView.Interactive, QHeaderView.Fixed):
            st.setValue(f"{key}/{col}", table.columnWidth(col))


class TableDefaults(QObject):
    def eventFilter(self, obj: QObject, ev: QEvent) -> bool:
        if ev.type() == QEvent.Show and isinstance(obj, QTableWidget) and not obj.property("_defaults_done"):
            obj.setProperty("_defaults_done", True)
            apply_defaults(obj)
        return False
