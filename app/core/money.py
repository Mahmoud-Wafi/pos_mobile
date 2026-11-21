"""Money utilities.

All monetary values are stored and passed as **integer piasters** (100 piasters = 1 EGP).
Never use float for money.
"""
import re
from decimal import Decimal, ROUND_HALF_UP


def egp_to_piasters(egp: Decimal | int | str) -> int:
    """Convert an EGP amount (Decimal/str) to integer piasters, rounding half-up."""
    d = Decimal(normalize_number_text(egp) if isinstance(egp, str) else str(egp))
    piasters = (d * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(piasters)


def piasters_to_egp(piasters: int) -> Decimal:
    """Convert integer piasters to a Decimal EGP value."""
    return Decimal(piasters) / Decimal(100)


def format_money(piasters: int) -> str:
    """Return a display string like '1,234.50 ج.م'."""
    egp = piasters_to_egp(piasters)
    # Always show 2 decimal places, with thousands separator
    formatted = f"{egp:,.2f}"
    return f"{formatted} ج.م"


def format_money_signed(piasters: int, always_sign: bool = False) -> str:
    """Display text with the sign kept on the LEFT of the digits even inside right-to-left text
    ('-200.00 ج.م', '+10,590.00 ج.م'). The number is isolated left-to-right so Qt/Arabic bidi
    cannot move the sign to the other side."""
    egp = piasters_to_egp(abs(piasters))
    sign = "-" if piasters < 0 else ("+" if always_sign and piasters > 0 else "")
    return f"\u2066{sign}{egp:,.2f}\u2069 ج.م"


def apply_percent_discount(amount_piasters: int, percent_bp: int) -> int:
    """Apply a discount given in basis points (1% = 100 bp) to an amount in piasters.

    Uses Decimal half-up rounding.  Returns the discounted amount.
    """
    if percent_bp == 0:
        return amount_piasters
    discount = (Decimal(amount_piasters) * Decimal(percent_bp) / Decimal(10000)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    return amount_piasters - int(discount)


def percent_of(amount_piasters: int, percent_bp: int) -> int:
    """Return percent_bp basis-points of amount_piasters (half-up rounded)."""
    result = (Decimal(amount_piasters) * Decimal(percent_bp) / Decimal(10000)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    return int(result)


def weighted_average_cost(old_qty: int, old_avg_piasters: int, new_qty: int, new_cost_piasters: int) -> int:
    """Compute new weighted-average unit cost after a purchase.

    Returns result in piasters, half-up rounded.
    """
    if old_qty + new_qty == 0:
        return new_cost_piasters
    numerator = Decimal(old_qty) * Decimal(old_avg_piasters) + Decimal(new_qty) * Decimal(new_cost_piasters)
    avg = (numerator / Decimal(old_qty + new_qty)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(avg)



_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬،", "0123456789.,,")


_GROUPED = re.compile(r"^\d{1,3}(,\d{3})+(\.\d+)?$")


def normalize_number_text(text: str) -> str:
    """Arabic digits/marks -> ASCII; ',' is a thousands mark only when it groups
    3 digits ('1,234'), otherwise a decimal mark ('500,5')."""
    cleaned = (text or "").strip().translate(_ARABIC_DIGITS).replace(" ", "")
    if "," in cleaned:
        cleaned = cleaned.replace(",", "") if _GROUPED.match(cleaned) else cleaned.replace(",", ".", 1).replace(",", "")
    return cleaned


def parse_int_input(text: str, default: int = 0) -> int:
    """Whole number from user text (Arabic digits ok); empty -> default."""
    cleaned = normalize_number_text(text)
    if not cleaned:
        return default
    if not re.fullmatch(r"\d+", cleaned):
        raise ValueError(f"invalid number: {text!r}")
    return int(cleaned)


def parse_egp_input(text: str) -> int:
    """Parse user-typed EGP text into integer piasters. Decimal only, never float.

    Accepts Arabic-Indic digits, ',' thousands separators and '٫' decimal marks.
    Raises ValueError on empty / invalid / negative input.
    """
    from decimal import InvalidOperation

    cleaned = normalize_number_text(text).replace("ج.م", "").replace("EGP", "")
    if not cleaned:
        raise ValueError("empty amount")
    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"invalid amount: {text!r}") from exc
    if not value.is_finite() or value < 0:
        raise ValueError(f"invalid amount: {text!r}")
    return egp_to_piasters(value)


def piasters_to_input(piasters: int) -> str:
    """Piasters -> plain editable text like '1234.50' (no float involved)."""
    return f"{piasters_to_egp(piasters):.2f}"


def parse_percent_to_bp(text: str) -> int:
    """'2.5' (percent) -> 250 basis points, via Decimal."""
    from decimal import InvalidOperation

    cleaned = normalize_number_text((text or "").replace("%", ""))
    try:
        value = Decimal(cleaned or "0")
    except InvalidOperation as exc:
        raise ValueError(f"invalid percent: {text!r}") from exc
    if value < 0:
        raise ValueError("negative percent")
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
