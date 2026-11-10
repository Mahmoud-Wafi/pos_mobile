"""Timezone / day-boundary behaviour (Africa/Cairo vs stored UTC)."""
import datetime

import pytest

from app.core import clock
from app.core.money import parse_egp_input, piasters_to_input, parse_percent_to_bp
from app.models.sale import Sale
from app.services import report_service
from app.core.permissions import ROLE_MANAGER
from app.models.user import User, Role


def test_day_bounds_cairo_winter():
    s, e = clock.day_bounds_utc(datetime.date(2026, 1, 15))
    assert s == datetime.datetime(2026, 1, 14, 22, 0)          # UTC+2
    assert e.date() == datetime.date(2026, 1, 15) and e.hour == 21


def test_day_bounds_cairo_summer():
    s, _ = clock.day_bounds_utc(datetime.date(2026, 7, 15))
    assert s == datetime.datetime(2026, 7, 14, 21, 0)          # UTC+3 (DST)


def test_to_local_roundtrip():
    assert clock.to_local(datetime.datetime(2026, 1, 14, 22, 30)) == datetime.datetime(2026, 1, 15, 0, 30)


def test_sale_at_0030_cairo_counts_for_that_local_day(db_session):
    manager = db_session.query(User).join(Role).filter(Role.name == ROLE_MANAGER).first()
    # 00:30 Cairo on 15 Jan == 22:30 UTC on 14 Jan
    sale = Sale(invoice_no="T-1", user_id=manager.id, customer_id=1, status="posted",
                subtotal=1000, discount=0, total=1000, paid=1000, remaining=0,
                created_at=datetime.datetime(2026, 1, 14, 22, 30))
    db_session.add(sale)
    db_session.flush()
    rep = report_service.sales_report(db_session, manager,
                                      datetime.date(2026, 1, 15), datetime.date(2026, 1, 15))
    assert any(r["invoice_no"] == "T-1" for r in rep["rows"])
    rep_prev = report_service.sales_report(db_session, manager,
                                           datetime.date(2026, 1, 14), datetime.date(2026, 1, 14))
    assert not any(r["invoice_no"] == "T-1" for r in rep_prev["rows"])


@pytest.mark.parametrize("text,expected", [
    ("10", 1000), ("10.5", 1050), ("1,234.50", 123450), ("١٢٫٥٠", 1250), ("0.005", 1),
])
def test_parse_egp_input(text, expected):
    assert parse_egp_input(text) == expected


@pytest.mark.parametrize("bad", ["", "abc", "-5", "NaN"])
def test_parse_egp_input_rejects(bad):
    with pytest.raises(ValueError):
        parse_egp_input(bad)


def test_piasters_to_input_and_percent():
    assert piasters_to_input(123450) == "1234.50"
    assert parse_percent_to_bp("2.5") == 250
