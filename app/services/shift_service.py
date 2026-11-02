"""Shift service — cashier shift open/close and drawer cash reconciliation."""
from __future__ import annotations

import datetime
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.models.shift import Shift
from app.models.accounting import CashAccount, CashTransaction
from app.models.user import User


class ShiftAlreadyOpenError(Exception):
    pass


class NoActiveShiftError(Exception):
    pass


def get_active_shift(session: Session, user_id: int) -> Optional[Shift]:
    """Return the currently open shift for *user_id*, or None."""
    return session.query(Shift).filter_by(user_id=user_id, status="open").first()


def open_shift(
    session: Session,
    user: User,
    opening_cash: int = 0,
    notes: Optional[str] = None,
) -> Shift:
    """Open a new shift for the cashier.

    Raises ShiftAlreadyOpenError if user already has an open shift.
    """
    existing = get_active_shift(session, user.id)
    if existing:
        raise ShiftAlreadyOpenError(f"يوجد وردية مفتوحة بالفعل للمستخدم {user.username}")

    shift = Shift(
        user_id=user.id,
        opened_at=datetime.datetime.utcnow(),
        opening_cash=opening_cash,
        expected_cash=opening_cash,
        actual_cash=0,
        diff=0,
        status="open",
        notes=notes,
    )
    session.add(shift)
    session.flush()

    # Update or sync drawer opening balance if specified
    drawer = session.query(CashAccount).filter_by(type="drawer").first()
    if drawer and opening_cash > 0 and drawer.balance == 0:
        drawer.balance = opening_cash
        session.add(CashTransaction(
            account_id=drawer.id,
            type="in",
            amount=opening_cash,
            category="shift_open",
            ref_type="shift",
            ref_id=shift.id,
            shift_id=shift.id,
            user_id=user.id,
            note="رصيد بداية الوردية",
        ))

    session.flush()
    log_action(session, "open_shift", user_id=user.id,
               table_name="shifts", record_id=shift.id,
               new_value={"opening_cash": opening_cash})
    return shift


def calculate_expected_cash(session: Session, shift_id: int) -> int:
    """Calculate expected cash at shift close: opening_cash + cash in - cash out."""
    shift = session.get(Shift, shift_id)
    if not shift:
        return 0

    cash_in = session.query(func.coalesce(func.sum(CashTransaction.amount), 0)).filter(
        CashTransaction.shift_id == shift_id,
        CashTransaction.type == "in",
    ).scalar() or 0

    cash_out = session.query(func.coalesce(func.sum(CashTransaction.amount), 0)).filter(
        CashTransaction.shift_id == shift_id,
        CashTransaction.type == "out",
    ).scalar() or 0

    return shift.opening_cash + cash_in - cash_out


def close_shift(
    session: Session,
    user: User,
    shift_id: int,
    actual_cash: int,
    notes: Optional[str] = None,
) -> Shift:
    """Close an active shift, reconcile expected vs actual cash, and record the diff."""
    shift = session.get(Shift, shift_id)
    if not shift or shift.status != "open":
        raise NoActiveShiftError("الوردية غير موجودة أو مغلقة بالفعل")

    expected = calculate_expected_cash(session, shift_id)
    diff = actual_cash - expected  # negative = shortage, positive = overage

    shift.closed_at = datetime.datetime.utcnow()
    shift.expected_cash = expected
    shift.actual_cash = actual_cash
    shift.diff = diff
    shift.status = "closed"
    if notes:
        shift.notes = f"{shift.notes or ''} | {notes}".strip(" |")

    session.flush()
    log_action(session, "close_shift", user_id=user.id,
               table_name="shifts", record_id=shift.id,
               new_value={"expected": expected, "actual": actual_cash, "diff": diff})
    return shift

