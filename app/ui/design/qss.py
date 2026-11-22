"""Builds the application stylesheet from the design tokens.

Widgets opt in through dynamic properties instead of inline styles:
  QPushButton[variant="primary|secondary|danger|success|ghost"]
  QPushButton[nav="true"] with [active="true"]
  QFrame[card="true"], QFrame[kpi="true"]
  QLabel[text_role="muted|title|h1|h2|caption"], QLabel[pill="success|warning|danger|info|neutral"]
"""
from __future__ import annotations

from app.core.paths import resource_dir
from app.ui.design.tokens import COLORS as C, CONTROL_HEIGHT, FONT_FAMILY, FONT_SIZES as F, RADII as R, SPACING as S


def build_qss() -> str:
    check = (resource_dir() / "assets" / "icons" / "check-white.svg").as_posix()
    return f"""
* {{ font-family: {FONT_FAMILY}; }}
QMainWindow, QDialog {{ background-color: {C['bg']}; color: {C['text']}; }}
QWidget {{ color: {C['text_body']}; font-size: {F['body']}px; }}
QToolTip {{ background: {C['header_bg']}; color: {C['text_inverse']}; border: none; padding: 4px 8px; }}

/* focus ring (2px) on every interactive control */
QPushButton:focus {{ border: 2px solid {C['focus']}; }}
QTabBar::tab:focus {{ border: 2px solid {C['focus']}; }}
QCheckBox:focus {{ color: {C['primary']}; }}

/* shell */
QFrame#Header {{ background-color: {C['header_bg']}; border-bottom: 1px solid {C['header_chip']}; min-height: 64px; max-height: 64px; }}
QFrame#Header QLabel {{ color: {C['header_text']}; }}
QLabel#AppTitle {{ color: {C['text_inverse']}; font-size: {F['h2']}px; font-weight: 700; }}
QLabel#AppSubtitle {{ color: {C['header_muted']}; font-size: {F['caption']}px; }}
QLabel#HeaderClock {{ color: {C['header_text']}; font-weight: 600; background-color: {C['header_chip']}; border-radius: {R['md']}px; padding: 6px 12px; }}
QLabel#UserPill {{ color: {C['bg']}; font-weight: 600; }}
QLabel#RolePill {{ background-color: {C['primary']}; color: {C['text_inverse']}; font-size: {F['caption']}px; font-weight: 700; border-radius: {R['md']}px; padding: 4px 10px; }}
QLabel#ShiftPill {{ background-color: {C['header_chip']}; border-radius: {R['md']}px; padding: 6px 12px; font-weight: 700; }}
QLabel#ShiftPill[state="open"] {{ color: #6EE7B7; }}
QLabel#ShiftPill[state="closed"] {{ color: #FCA5A5; }}
QFrame#Sidebar {{ background-color: {C['header_bg']}; border: none; min-width: 244px; max-width: 244px; }}
QFrame#Sidebar[compact="true"] {{ min-width: 84px; max-width: 84px; }}
QFrame#Sidebar[compact="true"] QPushButton[nav="true"] {{ padding: 10px 0; margin: 2px 12px; }}
QLabel#SidebarCategory {{ color: {C['sidebar_category']}; font-size: {F['caption']}px; font-weight: 700; padding: 8px 16px 2px 16px; background: transparent; }}
QFrame#ShiftCard {{ background-color: {C['header_chip']}; border: none; border-radius: {R['lg']}px; margin: 6px; }}
QFrame#ShiftCard QLabel {{ color: {C['header_text']}; background: transparent; }}
QPushButton[nav="true"] {{ text-align: right; padding: 10px 16px; border: none; border-radius: {R['lg']}px; margin: 2px 8px;
    font-weight: 600; background-color: transparent; color: {C['header_muted']}; min-height: 24px; }}
QPushButton[nav="true"]:hover {{ background-color: {C['sidebar_hover']}; color: {C['text_inverse']}; }}
QPushButton[nav="true"][active="true"] {{ background-color: {C['primary']}; color: {C['text_inverse']}; font-weight: 700; }}
QPushButton[nav="true"]:focus {{ border: 2px solid {C['text_inverse']}; }}

/* surfaces */
QFrame[card="true"] {{ background-color: {C['surface']}; border: 1px solid {C['border']}; border-radius: {R['xl']}px; }}
QFrame[kpi="true"] {{ background-color: {C['surface']}; border: 1px solid {C['border']}; border-radius: {R['xl']}px; }}
QFrame[banner="warning"] {{ background-color: {C['warning_soft']}; border: 1px solid #F2D08A; border-radius: {R['md']}px; }}
QFrame[banner="info"] {{ background-color: {C['info_soft']}; border: 1px solid #BFDDF0; border-radius: {R['md']}px; }}
QFrame[banner="success"] {{ background-color: {C['success_soft']}; border: 1px solid #A8DEC5; border-radius: {R['md']}px; }}
QFrame[banner="danger"] {{ background-color: {C['danger_soft']}; border: 1px solid #F3C7C3; border-radius: {R['md']}px; }}
QFrame[total_box="true"] {{ background-color: {C['header_bg']}; border-radius: {R['xl']}px; }}
QFrame[toast="true"] {{ background-color: {C['header_bg']}; border-radius: {R['md']}px; }}
QFrame[toast="true"] QLabel {{ color: {C['text_inverse']}; font-weight: 600; }}

/* text roles */
QLabel {{ color: {C['text_body']}; }}
QLabel[text_role="muted"] {{ color: {C['text_muted']}; }}
QLabel[text_role="caption"] {{ color: {C['text_muted']}; font-size: {F['caption']}px; }}
QLabel[text_role="title"] {{ color: {C['text']}; font-size: {F['title']}px; font-weight: 700; }}
QLabel[text_role="h2"] {{ color: {C['text']}; font-size: {F['h2']}px; font-weight: 700; }}
QLabel[text_role="h1"] {{ color: {C['text']}; font-size: {F['h1']}px; font-weight: 800; }}
QLabel[text_role="money"] {{ color: {C['text']}; font-size: {F['h2']}px; font-weight: 800; }}
QLabel[text_role="total"] {{ color: #8CA6FF; font-size: {F['h1']}px; font-weight: 800; }}
QLabel[text_role="total_caption"] {{ color: {C['header_muted']}; font-weight: 700; }}
QLabel[pill] {{ border-radius: 999px; padding: 3px 10px; font-size: {F['caption']}px; font-weight: 700; }}
QLabel[pill="success"] {{ background: {C['success_soft']}; color: {C['success']}; }}
QLabel[pill="warning"] {{ background: {C['warning_soft']}; color: {C['warning']}; }}
QLabel[pill="danger"]  {{ background: {C['danger_soft']};  color: {C['danger']}; }}
QLabel[pill="info"]    {{ background: {C['info_soft']};    color: {C['info']}; }}
QLabel[pill="neutral"] {{ background: {C['surface_alt']};  color: {C['text_muted']}; }}
QLabel[tone="text"] {{ color: {C['text']}; }}
QLabel[tone="muted"] {{ color: {C['text_muted']}; }}
QLabel[tone="success"] {{ color: {C['success']}; }}
QLabel[tone="danger"] {{ color: {C['danger']}; }}
QLabel[tone="warning"] {{ color: {C['warning']}; }}
QLabel[tone="info"] {{ color: {C['info']}; }}
QLabel[tone="primary"] {{ color: {C['primary']}; }}
QLabel[tone="total"] {{ color: #8CA6FF; }}
QLabel[tone="inverse_muted"] {{ color: {C['header_muted']}; }}
QLabel[size="caption"] {{ font-size: {F['caption']}px; }}
QLabel[size="body"] {{ font-size: {F['body']}px; }}
QLabel[size="label"] {{ font-size: {F['label']}px; }}
QLabel[size="title"] {{ font-size: {F['title']}px; }}
QLabel[size="h2"] {{ font-size: {F['h2']}px; }}
QLabel[size="h1"] {{ font-size: {F['h1']}px; }}
QLabel[size="icon"] {{ font-size: 28px; }}
QLabel[bold="true"] {{ font-weight: 700; }}
QFrame[hline="true"] {{ color: {C['border']}; }}
QFrame[banner] {{ padding: 8px; }}
QFrame[kpi="true"] {{ padding: 4px; }}
QScrollArea[transparent="true"], QWidget[transparent="true"] {{ background: transparent; }}

/* buttons */
QPushButton {{ background-color: {C['surface']}; color: {C['text_body']}; border: 1px solid {C['border_strong']};
    border-radius: {R['lg']}px; padding: 8px 18px; font-weight: 600; min-height: {CONTROL_HEIGHT - 18}px; }}
QPushButton:hover {{ background-color: {C['primary_soft']}; border-color: {C['primary']}; }}
QPushButton:pressed {{ background-color: {C['surface_alt']}; }}
QPushButton:disabled {{ background-color: {C['surface_alt']}; color: {C['text_disabled']}; border-color: {C['border']}; }}
QPushButton[variant="primary"], QPushButton#PrimaryBtn {{ background-color: {C['primary']}; color: {C['text_inverse']}; border: 1px solid {C['primary_hover']}; font-weight: 700; }}
QPushButton[variant="primary"]:hover, QPushButton#PrimaryBtn:hover {{ background-color: {C['primary_hover']}; }}
QPushButton[variant="primary"]:pressed {{ background-color: {C['primary_pressed']}; }}
QPushButton[variant="success"] {{ background-color: {C['success']}; color: {C['text_inverse']}; border: 1px solid {C['success_hover']}; font-weight: 800; }}
QPushButton[variant="success"]:hover {{ background-color: {C['success_hover']}; }}
QPushButton[variant="danger"] {{ background-color: {C['danger']}; color: {C['text_inverse']}; border: 1px solid {C['danger_hover']}; font-weight: 700; }}
QPushButton[variant="danger"]:hover {{ background-color: {C['danger_hover']}; }}
QPushButton[variant="danger-soft"] {{ background-color: {C['danger_soft']}; color: {C['danger']}; border: 1px solid {C['danger_soft']}; }}
QPushButton[variant="ghost"] {{ background-color: transparent; border: 1px solid transparent; color: {C['text_muted']}; }}
QPushButton[variant="ghost"]:hover {{ background-color: {C['surface_alt']}; color: {C['text']}; }}
QPushButton[variant="primary"]:disabled, QPushButton[variant="success"]:disabled, QPushButton[variant="danger"]:disabled {{
    background-color: {C['border_strong']}; color: {C['text_disabled']}; border-color: {C['border_strong']}; }}
QPushButton[variant="big"] {{ font-size: {F['title']}px; min-height: 36px; }}

/* inputs */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QDateEdit {{ background-color: {C['surface']}; color: {C['text']};
    border: 1px solid {C['border_strong']}; border-radius: {R['lg']}px; padding: 6px 12px; min-height: {CONTROL_HEIGHT - 14}px;
    selection-background-color: {C['primary']}; selection-color: {C['text_inverse']}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QTextEdit:focus, QDateEdit:focus {{ border: 2px solid {C['focus']}; }}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{ background-color: {C['surface_alt']}; color: {C['text_disabled']}; }}
QLineEdit[invalid="true"] {{ border: 2px solid {C['danger']}; }}
QLineEdit[size="big"] {{ font-size: {F['title']}px; font-weight: 700; min-height: 30px; }}
QLineEdit[align="center"] {{ qproperty-alignment: AlignCenter; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background-color: {C['surface']}; color: {C['text']}; border: 1px solid {C['border_strong']};
    selection-background-color: {C['primary_soft']}; selection-color: {C['primary']}; padding: 4px; }}

/* tabs */
QTabWidget::pane {{ border: 1px solid {C['border']}; background-color: {C['surface']}; border-radius: {R['xl']}px; top: -1px; }}
QTabBar::tab {{ background-color: transparent; color: {C['text_muted']}; padding: 10px 22px; margin: 4px 3px;
    border-radius: {R['lg']}px; font-weight: 700; border: 1px solid transparent; }}
QTabBar::tab:hover {{ background-color: {C['surface_alt']}; color: {C['text']}; }}
QTabBar::tab:selected {{ background-color: {C['primary']}; color: {C['text_inverse']}; }}

/* tables */
QTableWidget, QTableView {{ background-color: {C['surface']}; alternate-background-color: {C['bg']}; color: {C['text']};
    gridline-color: {C['surface_alt']}; border: 1px solid {C['border']}; border-radius: {R['md']}px;
    selection-background-color: {C['primary_soft']}; selection-color: {C['primary_pressed']}; }}
QTableWidget::item {{ padding: 8px 12px; border-bottom: 1px solid {C['surface_alt']}; }}
QTableWidget::item:selected {{ background-color: {C['primary_soft']}; color: {C['primary_pressed']}; font-weight: 600; }}
QHeaderView::section {{ background-color: {C['bg']}; color: {C['text_muted']}; font-size: {F['caption']}px; font-weight: 700; padding: 10px 12px;
    border: none; border-bottom: 2px solid {C['border']}; border-left: 1px solid {C['surface_alt']}; }}
QTableCornerButton::section {{ background-color: {C['bg']}; border: none; border-bottom: 2px solid {C['border']}; }}

/* scrollbars */
QScrollBar:vertical {{ border: none; background-color: {C['surface_alt']}; width: 10px; border-radius: 5px; margin: 0; }}
QScrollBar::handle:vertical {{ background-color: {C['border_strong']}; min-height: 24px; border-radius: 5px; }}
QScrollBar::handle:vertical:hover {{ background-color: {C['text_disabled']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ border: none; background-color: {C['surface_alt']}; height: 10px; border-radius: 5px; }}
QScrollBar::handle:horizontal {{ background-color: {C['border_strong']}; min-width: 24px; border-radius: 5px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* misc */
QGroupBox {{ font-weight: 700; color: {C['text']}; border: 1px solid {C['border']}; border-radius: {R['md']}px; margin-top: 26px; padding: 22px 12px 12px 12px; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top right; right: 14px; top: 2px; padding: 2px 10px; color: {C['text']}; }}
/* buttons placed inside table cells must fit the row (they were clipped at 44px rows) */
QTableView QPushButton {{ padding: 2px 12px; min-height: 26px; max-height: 36px; font-size: {F['caption']}px; }}
QDialog {{ background-color: {C['surface']}; color: {C['text']}; }}
QCheckBox {{ font-weight: 600; spacing: 8px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 4px; border: 1px solid {C['border_strong']}; background-color: {C['surface']}; }}
QCheckBox::indicator:checked {{ background-color: {C['primary']}; border-color: {C['primary']}; image: url({check}); }}
QStatusBar {{ background-color: {C['surface']}; color: {C['text_muted']}; border-top: 1px solid {C['border']}; font-size: {F['caption']}px; padding: 4px 12px; }}
QStatusBar QLabel {{ color: {C['text_muted']}; font-size: {F['caption']}px; }}
"""
