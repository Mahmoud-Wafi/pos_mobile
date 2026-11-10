"""Single source of truth for time.

Rule (D-009): the database stores *naive UTC* datetimes. Anything that shows a
time to the user, or decides which calendar day a record belongs to, goes
through the shop's local timezone (Africa/Cairo by default).
"""
from __future__ import annotations

import datetime
import os
from zoneinfo import ZoneInfo

SHOP_TZ = ZoneInfo(os.environ.get("POS_TIMEZONE", "Africa/Cairo"))
_UTC = datetime.timezone.utc


def utcnow() -> datetime.datetime:
    """Current time as a naive UTC datetime (the storage format)."""
    return datetime.datetime.now(_UTC).replace(tzinfo=None)


def to_local(dt: datetime.datetime) -> datetime.datetime:
    """Convert a stored naive-UTC datetime to naive local shop time."""
    return dt.replace(tzinfo=_UTC).astimezone(SHOP_TZ).replace(tzinfo=None)


def local_now() -> datetime.datetime:
    return to_local(utcnow())


def local_today() -> datetime.date:
    return local_now().date()


def day_bounds_utc(start: datetime.date, end: datetime.date | None = None):
    """Return (start_utc, end_utc) naive datetimes covering local dates start..end inclusive.

    The end bound is exclusive-style: the last microsecond of the end day.
    """
    end = end or start

    def _to_utc(local_naive: datetime.datetime) -> datetime.datetime:
        return local_naive.replace(tzinfo=SHOP_TZ).astimezone(_UTC).replace(tzinfo=None)

    s = _to_utc(datetime.datetime.combine(start, datetime.time.min))
    e = _to_utc(datetime.datetime.combine(end, datetime.time.max))
    return s, e


def fmt_local(dt: datetime.datetime | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    return to_local(dt).strftime(fmt) if dt else "—"
