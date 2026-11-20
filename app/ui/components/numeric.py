"""Locale-independent numeric input validators.

Qt's QDoubleValidator follows the OS locale: on an Arabic (Egypt) Windows it
REJECTS '500.00' and the user cannot type a decimal point. These validators
accept ASCII and Arabic-Indic digits and '.', ',' or U+066B as decimal mark on
every machine, and are parsed later by app.core.money.
"""
from __future__ import annotations

from PySide6.QtCore import QObject
from PySide6.QtGui import QValidator


_AR = str.maketrans("\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669", "0123456789")  # Arabic-Indic digits


class NumberValidator(QValidator):
    def __init__(self, minimum: float, maximum: float, decimals: int, parent: QObject | None = None):
        super().__init__(parent)
        self.minimum, self.maximum, self.decimals = minimum, maximum, decimals

    def validate(self, text: str, pos: int):
        raw = (text or "").translate(_AR).replace("\u066b", ".").replace("\u066c", ",").replace("\u060c", ",")
        if raw == "":
            return QValidator.Intermediate, text, pos
        allowed = set("0123456789.,")
        if any(c not in allowed for c in raw):
            return QValidator.Invalid, text, pos
        if self.decimals == 0:
            if not raw.isdigit():
                return QValidator.Invalid, text, pos
        else:
            if raw.count(".") + raw.count(",") > 1:
                return QValidator.Invalid, text, pos
            parts = raw.replace(",", ".").split(".")
            if len(parts) == 2 and len(parts[1]) > self.decimals:
                return QValidator.Invalid, text, pos
        try:
            value = float(raw.replace(",", ".") or 0)
        except ValueError:
            return QValidator.Intermediate, text, pos
        if value > self.maximum:
            return QValidator.Invalid, text, pos
        if value < self.minimum:
            return QValidator.Intermediate, text, pos
        return QValidator.Acceptable, text, pos


def set_money_validator(edit, minimum: float = 0.0, maximum: float = 9999999.0, decimals: int = 2) -> None:
    edit.setValidator(NumberValidator(minimum, maximum, decimals, edit))


def set_int_validator(edit, minimum: int = 0, maximum: int = 999999) -> None:
    edit.setValidator(NumberValidator(minimum, maximum, 0, edit))
