"""Shift service — cashier shift open/close and drawer cash reconciliation."""
from __future__ import annotations

import datetime
from app.core.clock import utcnow
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core import clock
from app.core.audit import log_action
from app.core.permissions import ROLE_MANAGER, PermissionDenied
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


def get_open_shift_for(session: Session, user: User) -> Optional[Shift]:
    """The user's own open shift, else the shop's most recent open shift (e.g. a manager acting during a cashier's shift)."""
    return get_active_shift(session, user.id) or (
        session.query(Shift).filter_by(status="open").order_by(Shift.id.desc()).first())


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
        opened_at=utcnow(),
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

    # Only DRAWER movements count (an expense paid from a bank account never touches the drawer), and a
    # transfer from/to the drawer moves physical cash. The closing adjustment itself is not part of "expected".
    base = (session.query(func.coalesce(func.sum(CashTransaction.amount), 0))
            .join(CashAccount, CashAccount.id == CashTransaction.account_id)
            .filter(CashTransaction.shift_id == shift_id, CashAccount.type == "drawer",
                    CashTransaction.category.notin_(("shift_open", "shift_diff"))))
    cash_in = base.filter(CashTransaction.type.in_(("in", "transfer_in"))).scalar() or 0
    cash_out = base.filter(CashTransaction.type.in_(("out", "transfer_out"))).scalar() or 0

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
    if shift.user_id != user.id and user.role.name != ROLE_MANAGER:
        raise PermissionDenied("shift.close_other", user.username)
    if actual_cash < 0:
        raise ValueError("المبلغ الفعلي لا يمكن أن يكون سالباً")

    expected = calculate_expected_cash(session, shift_id)
    diff = actual_cash - expected  # negative = shortage, positive = overage

    shift.closed_at = utcnow()
    shift.expected_cash = expected
    shift.actual_cash = actual_cash
    shift.diff = diff
    shift.status = "closed"
    if notes:
        shift.notes = f"{shift.notes or ''} | {notes}".strip(" |")

    # Bring the drawer's book balance to what was really counted, so the treasury shows the physical cash.
    # The shortage/overage itself is reported through Shift.diff (P&L), never as a second profit entry.
    if diff != 0:
        drawer = session.query(CashAccount).filter_by(type="drawer").first()
        if drawer is not None:
            drawer.balance += diff
            session.add(CashTransaction(
                account_id=drawer.id, type="in" if diff > 0 else "out", amount=abs(diff), category="shift_diff",
                ref_type="shift", ref_id=shift.id, shift_id=shift.id, user_id=user.id,
                note="فرق جرد الوردية (زيادة)" if diff > 0 else "فرق جرد الوردية (عجز)"))

    session.flush()
    log_action(session, "close_shift", user_id=user.id,
               table_name="shifts", record_id=shift.id,
               new_value={"expected": expected, "actual": actual_cash, "diff": diff})
    return shift



def shift_status(session: Session, user: User) -> dict:
    """Small dict describing the user's current shift, for headers/sidebar cards."""
    shift = get_active_shift(session, user.id)
    if shift is None:
        return {"is_open": False, "id": None, "opened_at": None, "user_name": user.full_name}
    return {
        "is_open": True,
        "id": shift.id,
        "opened_at": clock.fmt_local(shift.opened_at, "%Y-%m-%d %H:%M"),
        "user_name": user.full_name,
    }
