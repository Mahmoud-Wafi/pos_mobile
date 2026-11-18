"""Global modern theme, Cairo font loader, and styles for the Mobile Shop POS."""
from __future__ import annotations

from pathlib import Path
from PySide6.QtGui import QFont, QFontDatabase, QPalette, QColor
from PySide6.QtWidgets import QApplication

from app.ui.design.qss import build_qss
from app.ui.design.tokens import COLORS as C

FONT_FAMILY = "Cairo"


def setup_theme(app: QApplication) -> None:
    """Apply the modern theme, load Cairo font, and set strict color palette."""
    app.setStyle("Fusion")

    # 1. Load Cairo font if available
    from app.core.paths import resource_dir
    assets_dir = resource_dir() / "assets"
    regular_font = assets_dir / "Cairo-Regular.ttf"
    bold_font = assets_dir / "Cairo-Bold.ttf"

    font_loaded = False
    if regular_font.exists():
        id1 = QFontDatabase.addApplicationFont(str(regular_font))
        if id1 >= 0:
            font_loaded = True
    if bold_font.exists():
        QFontDatabase.addApplicationFont(str(bold_font))

    default_family = FONT_FAMILY if font_loaded else "Segoe UI, Tajawal, Tahoma, sans-serif"
    font = QFont(default_family)
    font.setPixelSize(13)
    font.setStyleHint(QFont.SansSerif)
    app.setFont(font)

    # 2. Force light palette so OS dark themes (like Ubuntu dark/Yaru-dark) don't create black backgrounds
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(C['bg']))
    palette.setColor(QPalette.WindowText, QColor(C['text']))
    palette.setColor(QPalette.Base, QColor(C['surface']))
    palette.setColor(QPalette.AlternateBase, QColor(C['surface_alt']))
    palette.setColor(QPalette.ToolTipBase, QColor(C['text']))
    palette.setColor(QPalette.ToolTipText, QColor(C['surface']))
    palette.setColor(QPalette.Text, QColor(C['text']))
    palette.setColor(QPalette.Button, QColor(C['surface']))
    palette.setColor(QPalette.ButtonText, QColor(C['text']))
    palette.setColor(QPalette.BrightText, QColor(C['danger']))
    palette.setColor(QPalette.Link, QColor(C['primary']))
    palette.setColor(QPalette.Highlight, QColor(C['primary']))
    palette.setColor(QPalette.HighlightedText, QColor(C['surface']))
    palette.setColor(QPalette.PlaceholderText, QColor(C['text_muted']))
    app.setPalette(palette)

    # 3. Comprehensive modern stylesheet
    app.setStyleSheet(build_qss())

    # 4. Icons on text buttons (Lucide), added when a button is first shown
    from app.ui.design.auto_icons import AutoIcons
    app._auto_icons = AutoIcons(app)
    app.installEventFilter(app._auto_icons)
    from app.ui.design.table_defaults import TableDefaults
    app._table_defaults = TableDefaults(app)
    app.installEventFilter(app._table_defaults)
