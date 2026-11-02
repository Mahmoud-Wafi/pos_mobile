"""Global modern theme, Cairo font loader, and styles for the Mobile Shop POS."""
from __future__ import annotations

from pathlib import Path
from PySide6.QtGui import QFont, QFontDatabase, QPalette, QColor
from PySide6.QtWidgets import QApplication

FONT_FAMILY = "Cairo"


def setup_theme(app: QApplication) -> None:
    """Apply the modern theme, load Cairo font, and set strict color palette."""
    app.setStyle("Fusion")

    # 1. Load Cairo font if available
    assets_dir = Path(__file__).resolve().parent.parent.parent / "assets"
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
    font = QFont(default_family, 10)
    font.setStyleHint(QFont.SansSerif)
    app.setFont(font)

    # 2. Force light palette so OS dark themes (like Ubuntu dark/Yaru-dark) don't create black backgrounds
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#F8FAFC"))
    palette.setColor(QPalette.WindowText, QColor("#0F172A"))
    palette.setColor(QPalette.Base, QColor("#FFFFFF"))
    palette.setColor(QPalette.AlternateBase, QColor("#F1F5F9"))
    palette.setColor(QPalette.ToolTipBase, QColor("#0F172A"))
    palette.setColor(QPalette.ToolTipText, QColor("#FFFFFF"))
    palette.setColor(QPalette.Text, QColor("#0F172A"))
    palette.setColor(QPalette.Button, QColor("#FFFFFF"))
    palette.setColor(QPalette.ButtonText, QColor("#0F172A"))
    palette.setColor(QPalette.BrightText, QColor("#EF4444"))
    palette.setColor(QPalette.Link, QColor("#2563EB"))
    palette.setColor(QPalette.Highlight, QColor("#2563EB"))
    palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    app.setPalette(palette)

    # 3. Comprehensive modern stylesheet
    app.setStyleSheet(MODERN_QSS)


MODERN_QSS = """
/* ─── Global Reset & Typography ─── */
* {
    font-family: "Cairo", "Segoe UI", "Tajawal", "Tahoma", sans-serif;
    outline: none;
}

QMainWindow, QDialog {
    background-color: #F8FAFC;
    color: #0F172A;
}

QWidget {
    color: #1E293B;
}

/* ─── Header ─── */
QFrame#Header {
    background-color: #0F172A;
    border-bottom: 2px solid #2563EB;
    min-height: 60px;
    max-height: 60px;
}
QLabel#AppTitle {
    color: #FFFFFF;
    font-size: 19px;
    font-weight: 700;
}
QLabel#AppSubtitle {
    color: #94A3B8;
    font-size: 11px;
}
QLabel#HeaderClock {
    color: #E2E8F0;
    font-size: 13px;
    font-weight: 600;
    background-color: #1E293B;
    border-radius: 6px;
    padding: 6px 12px;
}
QLabel#UserPill {
    color: #F8FAFC;
    font-size: 13px;
    font-weight: 600;
}
QLabel#RolePill {
    background-color: #2563EB;
    color: #FFFFFF;
    font-size: 11px;
    font-weight: 700;
    border-radius: 6px;
    padding: 4px 10px;
}

/* ─── Sidebar ─── */
QFrame#Sidebar {
    background-color: #FFFFFF;
    border-left: 1px solid #E2E8F0;
    min-width: 230px;
    max-width: 230px;
}
QLabel#SidebarCategory {
    color: #94A3B8;
    font-size: 11px;
    font-weight: 700;
    padding: 8px 16px 2px 16px;
}
QPushButton.NavBtn {
    text-align: right;
    padding: 10px 16px;
    border: none;
    border-radius: 8px;
    margin: 2px 8px;
    font-size: 13px;
    font-weight: 600;
    background-color: transparent;
    color: #475569;
}
QPushButton.NavBtn:hover {
    background-color: #F1F5F9;
    color: #0F172A;
}
QPushButton.NavBtnActive {
    background-color: #EFF6FF;
    color: #2563EB;
    font-weight: 700;
    border-right: 4px solid #2563EB;
}

/* ─── Card Container ─── */
QFrame.Card {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
}

/* ─── Buttons ─── */
QPushButton {
    background-color: #FFFFFF;
    color: #1E293B;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #F8FAFC;
    border-color: #94A3B8;
}
QPushButton:pressed {
    background-color: #F1F5F9;
}

/* Primary Button */
QPushButton.PrimaryBtn, QPushButton#PrimaryBtn, QPushButton[class="PrimaryBtn"] {
    background-color: #2563EB;
    color: #FFFFFF;
    border: 1px solid #1D4ED8;
    font-weight: 700;
    padding: 8px 18px;
}
QPushButton.PrimaryBtn:hover, QPushButton#PrimaryBtn:hover, QPushButton[class="PrimaryBtn"]:hover {
    background-color: #1D4ED8;
    color: #FFFFFF;
}
QPushButton.PrimaryBtn:pressed, QPushButton#PrimaryBtn:pressed, QPushButton[class="PrimaryBtn"]:pressed {
    background-color: #1E40AF;
    color: #FFFFFF;
}

/* Success Button */
QPushButton.SuccessBtn {
    background-color: #059669;
    color: #FFFFFF;
    border: 1px solid #047857;
    font-weight: 700;
}
QPushButton.SuccessBtn:hover {
    background-color: #047857;
}

/* Danger Button */
QPushButton.DangerBtn {
    background-color: #DC2626;
    color: #FFFFFF;
    border: 1px solid #B91C1C;
    font-weight: 700;
}
QPushButton.DangerBtn:hover {
    background-color: #B91C1C;
}

/* ─── Inputs ─── */
QLineEdit, QSpinBox, QComboBox, QTextEdit {
    background-color: #FFFFFF;
    color: #0F172A;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    selection-background-color: #2563EB;
    selection-color: #FFFFFF;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {
    border: 2px solid #2563EB;
    background-color: #FFFFFF;
}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {
    background-color: #F1F5F9;
    color: #94A3B8;
}

/* ComboBox dropdown */
QComboBox::drop-down {
    border: none;
    width: 24px;
    padding-left: 4px;
}
QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    color: #0F172A;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
    selection-background-color: #EFF6FF;
    selection-color: #2563EB;
    padding: 4px;
}

/* ─── Tabs ─── */
QTabWidget::pane {
    border: 1px solid #E2E8F0;
    background-color: #FFFFFF;
    border-radius: 12px;
    top: -1px;
}
QTabBar::tab {
    background-color: #F1F5F9;
    color: #64748B;
    padding: 10px 24px;
    margin-left: 4px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-size: 13px;
    font-weight: 700;
    border: 1px solid transparent;
}
QTabBar::tab:hover {
    background-color: #E2E8F0;
    color: #0F172A;
}
QTabBar::tab:selected {
    background-color: #FFFFFF;
    color: #2563EB;
    border: 1px solid #E2E8F0;
    border-bottom: 2px solid #FFFFFF;
}

/* ─── Table Styling (Crucial fix for dark mode artifacts) ─── */
QTableWidget {
    background-color: #FFFFFF;
    alternate-background-color: #F8FAFC;
    color: #0F172A;
    gridline-color: #F1F5F9;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    selection-background-color: #EFF6FF;
    selection-color: #1E40AF;
}
QTableWidget::item {
    padding: 8px 12px;
    border-bottom: 1px solid #F1F5F9;
    color: #0F172A;
}
QTableWidget::item:selected {
    background-color: #EFF6FF;
    color: #1E40AF;
    font-weight: 600;
}
QHeaderView::section {
    background-color: #F8FAFC;
    color: #475569;
    font-size: 12px;
    font-weight: 700;
    padding: 10px 12px;
    border: none;
    border-bottom: 2px solid #E2E8F0;
    border-left: 1px solid #F1F5F9;
}
QTableCornerButton::section {
    background-color: #F8FAFC;
    border: none;
    border-bottom: 2px solid #E2E8F0;
}

/* ─── Scrollbars ─── */
QScrollBar:vertical {
    border: none;
    background-color: #F1F5F9;
    width: 8px;
    border-radius: 4px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background-color: #CBD5E1;
    min-height: 24px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background-color: #94A3B8;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    border: none;
    background-color: #F1F5F9;
    height: 8px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal {
    background-color: #CBD5E1;
    min-width: 24px;
    border-radius: 4px;
}

/* ─── Dialogs ─── */
QDialog {
    background-color: #FFFFFF;
    color: #0F172A;
}
QLabel {
    color: #1E293B;
}
QCheckBox {
    color: #1E293B;
    font-weight: 600;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #CBD5E1;
    background-color: #FFFFFF;
}
QCheckBox::indicator:checked {
    background-color: #2563EB;
    border-color: #2563EB;
}

/* ─── Status Bar ─── */
QStatusBar {
    background-color: #FFFFFF;
    color: #64748B;
    border-top: 1px solid #E2E8F0;
    font-size: 12px;
    padding: 4px 12px;
}
"""
