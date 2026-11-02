"""Main application window shell.

Phase 1: RTL layout, Arabic font fallback, login gate, basic navigation skeleton.
UI code is kept thin — all logic lives in services.
"""
from __future__ import annotations

try:
    from PySide6.QtWidgets import (
        QMainWindow, QWidget, QVBoxLayout, QLabel, QStatusBar,
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont

    HAS_QT = True
except ImportError:
    HAS_QT = False

from app.i18n import ar


if HAS_QT:
    class MainWindow(QMainWindow):
        """Application shell window."""

        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle(ar.APP_TITLE)
            self.setMinimumSize(1024, 768)
            self.setLayoutDirection(Qt.RightToLeft)

            # Arabic font (falls back to system default gracefully)
            font = QFont("Tajawal", 12)
            font.setStyleHint(QFont.SansSerif)
            self.setFont(font)

            # Central placeholder
            central = QWidget()
            layout = QVBoxLayout(central)
            layout.setAlignment(Qt.AlignCenter)

            title_label = QLabel(ar.APP_TITLE)
            title_font = QFont("Tajawal", 22, QFont.Bold)
            title_label.setFont(title_font)
            title_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(title_label)

            self.setCentralWidget(central)

            # Status bar
            status = QStatusBar()
            self.setStatusBar(status)
            status.showMessage(ar.APP_TITLE)

else:
    class MainWindow:  # type: ignore[no-redef]
        """Stub when PySide6 is unavailable (headless / test environment)."""

        def show(self) -> None:
            pass
