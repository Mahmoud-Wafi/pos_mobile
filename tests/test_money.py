"""Tests for app/core/money.py — all money calculations.

Rule: never use float; test half-up rounding explicitly.
"""
import pytest
from decimal import Decimal

from app.core.money import (
    egp_to_piasters,
    piasters_to_egp,
    format_money,
    apply_percent_discount,
    percent_of,
    weighted_average_cost,
)


class TestEgpToPiasters:
    def test_whole_pounds(self):
        assert egp_to_piasters("10") == 1000

    def test_fractional(self):
        assert egp_to_piasters("10.50") == 1050

    def test_third_decimal_rounds_half_up(self):
        # 10.005 EGP → 1000.5 piasters → rounds to 1001
        assert egp_to_piasters("10.005") == 1001

    def test_decimal_input(self):
        assert egp_to_piasters(Decimal("123.99")) == 12399

    def test_zero(self):
        assert egp_to_piasters("0") == 0

    def test_large_amount(self):
        assert egp_to_piasters("100000") == 10_000_000


class TestPiastersToEgp:
    def test_basic(self):
        assert piasters_to_egp(1050) == Decimal("10.50")

    def test_zero(self):
        assert piasters_to_egp(0) == Decimal("0")

    def test_one_piaster(self):
        assert piasters_to_egp(1) == Decimal("0.01")


class TestFormatMoney:
    def test_format_basic(self):
        assert format_money(1000) == "10.00 ج.م"

    def test_format_large(self):
        result = format_money(123450)
        # 1234.50 EGP with thousands separator
        assert "1,234.50" in result
        assert "ج.م" in result

    def test_format_zero(self):
        assert format_money(0) == "0.00 ج.م"

    def test_format_fractional(self):
        assert format_money(150) == "1.50 ج.م"


class TestApplyPercentDiscount:
    def test_no_discount(self):
        assert apply_percent_discount(1000, 0) == 1000

    def test_ten_percent(self):
        # 10% of 1000 piasters = 100; 1000 - 100 = 900
        assert apply_percent_discount(1000, 1000) == 900  # 1000 bp = 10%

    def test_five_percent(self):
        # 5% of 200 = 10; 200 - 10 = 190
        assert apply_percent_discount(200, 500) == 190

    def test_rounding_half_up(self):
        # 3% of 101 = 3.03 → rounds to 3; 101 - 3 = 98
        result = apply_percent_discount(101, 300)
        assert result == 98

    def test_full_discount(self):
        assert apply_percent_discount(500, 10000) == 0  # 100%


class TestPercentOf:
    def test_10_percent_of_100(self):
        assert percent_of(10000, 1000) == 1000  # 10% of 10000 piasters

    def test_zero(self):
        assert percent_of(1000, 0) == 0

    def test_half_up_rounding(self):
        # 1% of 1 piaster = 0.01 → rounds to 0
        assert percent_of(1, 100) == 0
        # 1% of 50 = 0.5 → rounds up to 1
        assert percent_of(50, 100) == 1


class TestWeightedAverageCost:
    def test_first_purchase(self):
        # No existing stock — new cost is the average
        result = weighted_average_cost(0, 0, 10, 500)
        assert result == 500

    def test_same_cost(self):
        result = weighted_average_cost(5, 1000, 5, 1000)
        assert result == 1000

    def test_mixed_costs(self):
        # 10 items @ 1000p + 10 items @ 2000p = 20 items @ 1500p avg
        result = weighted_average_cost(10, 1000, 10, 2000)
        assert result == 1500

    def test_rounding(self):
        # 1 item @ 100p + 2 items @ 101p = (100 + 202) / 3 = 302/3 = 100.666... → 101
        result = weighted_average_cost(1, 100, 2, 101)
        assert result == 101

    def test_large_quantities(self):
        result = weighted_average_cost(1000, 5000, 500, 6000)
        # (1000*5000 + 500*6000) / 1500 = (5000000 + 3000000) / 1500 = 5333.33 → 5333
        assert result == 5333

