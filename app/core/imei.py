"""IMEI helpers."""
from __future__ import annotations

_AR = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def normalize_imei(text: str) -> str:
    """Digits only (Arabic-Indic digits accepted, spaces and dashes dropped)."""
    return "".join(ch for ch in (text or "").translate(_AR) if ch.isdigit())


def luhn_valid(imei: str) -> bool:
    """True for a 15-digit IMEI whose Luhn check digit is correct."""
    digits = normalize_imei(imei)
    if len(digits) != 15:
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


class IMEIError(ValueError):
    """An IMEI that cannot be stored (message is Arabic, ready to show)."""


def clean_imei(raw, required: bool = False):
    """The ONE storage rule for an IMEI: digits only after normalising, 14-16 long (Luhn stays advisory)."""
    if raw is None or not str(raw).strip():
        if required:
            raise IMEIError("رقم IMEI مطلوب")
        return None
    digits = normalize_imei(str(raw))
    stripped = "".join(str(raw).split()).replace("-", "")
    if len(digits) != len(stripped.translate(_AR)) or not 14 <= len(digits) <= 16:
        raise IMEIError(f"رقم IMEI غير صحيح: {raw}")
    return digits


def clean_imei_pair(imei1, imei2=None):
    """(imei1, imei2) cleaned: IMEI 1 is required and the two must differ."""
    a = clean_imei(imei1, required=True)
    b = clean_imei(imei2)
    if b is not None and b == a:
        raise IMEIError("IMEI 1 و IMEI 2 متطابقان")
    return a, b
