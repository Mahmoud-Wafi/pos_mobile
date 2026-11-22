"""Dialogs taller than the screen scroll, and their buttons stay visible (D-024)."""
import pytest
from PySide6.QtCore import QRect
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
                               QVBoxLayout)

from app.ui.design.dialog_fit import DialogFit


@pytest.fixture
def fit(qapp):
    f = DialogFit(qapp)
    qapp.installEventFilter(f)
    yield f
    qapp.removeEventFilter(f)


SMALL = QRect(0, 0, 1280, 640)          # a laptop screen after the taskbar


@pytest.fixture(autouse=True)
def small_screen(monkeypatch):
    from app.ui.design import dialog_fit
    monkeypatch.setattr(dialog_fit, "_available", lambda dlg: SMALL)


def _avail(w):
    return SMALL


class Tall(QDialog):
    def __init__(self, rows=40):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("title"))
        for i in range(rows):
            lay.addWidget(QLineEdit(f"field {i}"))
        row = QHBoxLayout()
        self.ok, self.cancel = QPushButton("save"), QPushButton("cancel")
        self.ok.clicked.connect(self.accept)
        row.addWidget(self.ok); row.addWidget(self.cancel)
        lay.addLayout(row)


def _button_inside(dlg, btn):
    top = btn.mapTo(dlg, btn.rect().topLeft()).y()
    return btn.isVisible() and top >= 0 and top + btn.height() <= dlg.height()


def test_tall_dialog_fits_the_screen_and_keeps_buttons_visible(qtbot, fit):
    d = Tall()
    qtbot.addWidget(d)
    d.show()
    qtbot.wait(50)
    assert d.height() <= _avail(d).height()
    assert d.findChild(QScrollArea) is not None
    assert _button_inside(d, d.ok) and _button_inside(d, d.cancel)
    with qtbot.waitSignal(d.accepted, timeout=1000):
        d.ok.click()


def test_small_dialog_is_left_alone(qtbot, fit):
    d = Tall(rows=2)
    qtbot.addWidget(d)
    d.show()
    assert d.findChild(QScrollArea) is None
    assert _button_inside(d, d.ok)


def test_fixed_big_size_is_clamped_to_the_screen(qtbot, fit):
    d = Tall(rows=2)
    d.resize(5000, 5000)
    qtbot.addWidget(d)
    d.show()
    assert d.height() <= _avail(d).height() and d.width() <= _avail(d).width()


def test_real_dialogs_fit_a_small_screen(qtbot, fit, db_session):
    """The add-product dialog from the bug report, plus the other tall ones."""
    from app.core.permissions import ROLE_MANAGER
    from app.models.user import Role, User
    from app.core.security import hash_password
    from app.ui.inventory.product_list import ProductDialog
    from app.ui.purchases.purchase_invoice_dialog import PurchaseInvoiceDialog
    from app.ui.purchases.used_device_dialog import UsedDeviceDialog
    from app.ui.wallets.commission_rules_dialog import CommissionRulesDialog
    from app.ui.settings.hardware_tab import HardwareTab  # noqa: F401  (tab, not a dialog)

    role = db_session.query(Role).filter_by(name=ROLE_MANAGER).first()
    mgr = User(username="m", password_hash=hash_password("x"), full_name="m", role_id=role.id)
    db_session.add(mgr); db_session.commit()
    wrapped = []
    for make in (lambda: ProductDialog(db_session, mgr), lambda: ProductDialog(db_session, mgr, allow_opening=False),
                 lambda: PurchaseInvoiceDialog(db_session, mgr), lambda: UsedDeviceDialog(db_session, mgr),
                 lambda: CommissionRulesDialog(db_session, mgr)):
        d = make()
        qtbot.addWidget(d)
        d.show()
        qtbot.wait(30)
        assert d.height() <= SMALL.height(), type(d).__name__
        assert d.frameGeometry().top() >= SMALL.top() - 1, type(d).__name__
        wrapped.append((type(d).__name__, d.findChild(QScrollArea, 'dialogFitScroll') is not None))
        sa = d.findChild(QScrollArea, "dialogFitScroll")
        inner = set(sa.widget().findChildren(QPushButton)) if sa is not None else set()
        buttons = [b for b in d.findChildren(QPushButton) if b.isVisible() and b not in inner]
        assert buttons, type(d).__name__
        # the bottom-most button row must be reachable without scrolling
        lowest = max(buttons, key=lambda b: b.mapTo(d, b.rect().bottomLeft()).y())
        assert _button_inside(d, lowest), type(d).__name__
    assert any(w for _, w in wrapped)        # at least the tall ones really needed the scroll area
