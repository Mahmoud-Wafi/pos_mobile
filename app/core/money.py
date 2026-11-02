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
