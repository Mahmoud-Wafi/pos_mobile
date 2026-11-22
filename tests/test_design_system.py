"""Design system: tokens, generated QSS, components, and guard-rails against style regressions."""
import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from app.ui.design.qss import build_qss
from app.ui.design.tokens import COLORS, FONT_SIZES, RADII, SPACING

UI_DIR = Path(__file__).resolve().parent.parent / "app" / "ui"


def _lum(hex_color: str) -> float:
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_token_scales():
    assert sorted(SPACING.values()) == [4, 8, 12, 16, 24]
    assert sorted(RADII.values()) == [8, 12, 16]
    assert sorted(FONT_SIZES.values()) == [12, 13, 14, 16, 20, 28]


@pytest.mark.parametrize("fg,bg", [
    ("text", "surface"), ("text_body", "surface"), ("text_muted", "surface"), ("text_muted", "bg"),
    ("primary", "surface"), ("success", "surface"), ("danger", "surface"), ("warning", "surface"),
    ("text_inverse", "primary"), ("text_inverse", "danger"), ("text_inverse", "success"),
    ("header_text", "header_bg"), ("header_muted", "header_bg"),
])
def test_wcag_aa_contrast(fg, bg):
    assert contrast(COLORS[fg], COLORS[bg]) >= 4.5, (fg, bg)


def test_qss_is_generated_from_tokens_and_keeps_focus_ring():
    qss = build_qss()
    assert COLORS["primary"] in qss and "outline: none" not in qss
    assert "QLineEdit:focus" in qss and "2px solid" in qss
    assert not re.search(r"font-size:\s*(?:[0-9]|1[01])px", qss)


def test_inline_stylesheets_are_rare():
    count = sum(
        len(re.findall(r"\.setStyleSheet\(", f.read_text(encoding="utf-8")))
        for f in UI_DIR.rglob("*.py") if "design" not in f.parts
    )
    assert count <= 15, f"{count} inline setStyleSheet calls (limit 15)"


def test_no_emoji_icons_in_ui_strings():
    emoji = re.compile("[\U0001F300-\U0001FAFF☀-⛿✀-➿]")
    offenders = []
    for f in UI_DIR.rglob("*.py"):
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if emoji.search(line) and not line.lstrip().startswith("#"):
                offenders.append(f"{f.name}:{n}")
    assert len(offenders) <= 6, offenders


def test_icons_exist_and_license_bundled():
    from app.core.paths import resource_dir
    from app.ui.design.icons import pixmap
    from app.ui.main_window import NAV_ICONS

    icons_dir = resource_dir() / "assets" / "icons"
    assert (icons_dir / "LICENSE-lucide.txt").exists()
    for name in set(NAV_ICONS.values()) | {"trash-2", "search", "circle-check", "circle-alert", "info", "triangle-alert"}:
        assert (icons_dir / f"{name}.svg").exists(), name


def test_components_smoke(qtbot):
    from PySide6.QtWidgets import QPushButton
    from app.ui.components import (Card, DataTable, EmptyState, FormRow, KpiCard, MoneyLineEdit, PageHeader,
                                   SearchField, StatusPill, button)
    from app.ui.theme import setup_theme
    from PySide6.QtWidgets import QApplication

    setup_theme(QApplication.instance())
    k = KpiCard("مبيعات اليوم", "0.00 ج.م", "hint")
    qtbot.addWidget(k)
    k.set_value("5.00 ج.م")
    assert k.value_lbl.text() == "5.00 ج.م"
    for kind in ("primary", "secondary", "danger", "ghost", "success"):
        assert button("x", kind).property("variant") == kind
    pill = StatusPill("ok", "success")
    assert pill.property("pill") == "success"
    pill.set_status("late", "danger")
    assert pill.property("pill") == "danger"
    hdr = PageHeader("عنوان", "فرعي")
    hdr.add_action(button("اضافة", "primary"))
    t = DataTable(["a", "b"], empty_text="لا يوجد")
    qtbot.addWidget(t)
    t.set_rows([])
    t.set_rows([["1", "2"]])
    assert t.rowCount() == 1
    fr = FormRow("اسم", SearchField())
    fr.set_error("خطأ")
    assert not fr.error.isHidden()
    for w in (Card(), EmptyState("فارغ"), hdr, fr):
        qtbot.addWidget(w)


def test_money_line_edit():
    from PySide6.QtWidgets import QApplication
    from app.ui.components import MoneyLineEdit

    QApplication.instance() or QApplication([])
    m = MoneyLineEdit(12550)
    assert m.text() in ("125.50", "125.5") and m.piasters() == 12550
    m.setText("١٢٫٥")
    assert m.is_valid() and m.piasters() == 1250
    m.setText("abc")
    assert not m.is_valid()


def test_error_helper_hides_python_errors():
    from app.ui.components.dialogs import GENERIC_ERROR, friendly_message

    assert friendly_message(KeyError("'x'")) == GENERIC_ERROR
    assert friendly_message(ValueError("الكمية غير كافية")) == "الكمية غير كافية"


def test_auto_icon_keywords():
    from app.ui.design.auto_icons import icon_for

    assert icon_for("حفظ الصنف") == "save" and icon_for("طباعة الإيصال") == "printer"
    assert icon_for("xyz") is None


def test_main_window_shell(qtbot, db_session):
    from app.core.permissions import ROLE_MANAGER
    from app.models.user import Role, User
    from app.ui.main_window import MainWindow

    u = db_session.query(User).join(Role).filter(Role.name == ROLE_MANAGER).first()
    win = MainWindow(user_id=u.id)
    qtbot.addWidget(win)
    assert win.title_label.text()
    assert win.shift_val.objectName() == "ShiftPill"
    assert win.sb_version.text().startswith("v") and win.sb_user.text()
    win._show_pos()
    assert win._nav_by_key["pos"].property("active") is True
    assert win._nav_by_key["dashboard"].property("active") is False
    assert win.nav_buttons[0].toolTip() == "Ctrl+1"


def test_ui_arabic_text_lives_in_i18n():
    """Ratchet (5.1): remaining hard-coded Arabic lines in app/ui (mostly f-strings) must not grow."""
    import pathlib
    import re

    ar_re = re.compile("[؀-ۿ]")
    root = pathlib.Path(__file__).resolve().parents[1] / "app" / "ui"
    count = sum(
        1
        for f in root.rglob("*.py")
        for line in f.read_text(encoding="utf-8").splitlines()
        if ar_re.search(line) and not line.strip().startswith("#") and '"""' not in line
    )
    assert count <= 125, count
