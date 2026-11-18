"""MoneyLineEdit: EGP input that stores integer piasters (Arabic digits accepted)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit

from app.core.money import parse_egp_input, piasters_to_input
from app.ui.design.style import set_prop


class MoneyLineEdit(QLineEdit):
    def __init__(self, piasters: int = 0, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setPlaceholderText("0.00")
        self.set_piasters(piasters)
        self.editingFinished.connect(self._normalize)

    def piasters(self) -> int:
        """Value in piasters; raises ValueError for invalid text."""
        return parse_egp_input(self.text() or "0")

    def is_valid(self) -> bool:
        try:
            self.piasters()
            return True
        except (ValueError, ArithmeticError):
            return False

    def set_piasters(self, value: int) -> None:
        self.setText(piasters_to_input(value))

    def _normalize(self) -> None:
        ok = self.is_valid()
        set_prop(self, "invalid", not ok)
        if ok:
            self.set_piasters(self.piasters())
