"""Money utilities.

All monetary values are stored and passed as **integer piasters** (100 piasters = 1 EGP).
Never use float for money.
"""
from decimal import Decimal, ROUND_HALF_UP


def egp_to_piasters(egp: Decimal | int | str) -> int:
    """Convert an EGP amount (Decimal/str) to integer piasters, rounding half-up."""
    d = Decimal(str(egp))
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


def parse_egp_input(text: str) -> int:
    """Parse user-typed EGP text into integer piasters. Decimal only, never float.

    Accepts Arabic-Indic digits, ',' thousands separators and '٫' decimal marks.
    Raises ValueError on empty / invalid / negative input.
    """
    from decimal import InvalidOperation

    cleaned = (text or "").strip().translate(_ARABIC_DIGITS).replace(",", "").replace(" ", "")
    cleaned = cleaned.replace("ج.م", "").replace("EGP", "")
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

    cleaned = (text or "").strip().translate(_ARABIC_DIGITS).replace("%", "").replace(",", "")
    try:
        value = Decimal(cleaned or "0")
    except InvalidOperation as exc:
        raise ValueError(f"invalid percent: {text!r}") from exc
    if value < 0:
        raise ValueError("negative percent")
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
