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
