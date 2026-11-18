"""Repair tickets: intake, status flow, deposits / payments into the drawer, delivery. Audited.

Money is integer piasters. Cash taken goes into the drawer under the user's open shift, so the
shift close and the daily close see it. Repair profit (final price - parts cost) counts on delivery.
"""
from __future__ import annotations

import re
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.core import clock
from app.core.audit import log_action
from app.core.permissions import (PERM_COST_VIEW, PERM_SALES_CREATE, PERM_SALES_RETURN, require_permission)
from app.i18n import ar
from app.models.accounting import CashAccount, CashTransaction
from app.models.repair import REPAIR_STATUSES, RepairTicket
from app.models.user import User
from app.services import shift_service


class RepairError(Exception):
    """Business error with an Arabic message."""


_ACTIVE = ("received", "diagnosing", "waiting_parts", "ready")
_FLOW = {  # allowed manual moves; delivery and cancelling have their own functions
    "received": {"diagnosing", "waiting_parts", "ready"},
    "diagnosing": {"received", "waiting_parts", "ready"},
    "waiting_parts": {"diagnosing", "ready"},
    "ready": {"diagnosing", "waiting_parts"},
}


def _next_ticket_no(session: Session) -> str:
    prefix = f"REP-{clock.local_now().strftime('%Y%m%d')}-"
    last = (session.query(RepairTicket.ticket_no).filter(RepairTicket.ticket_no.like(f"{prefix}%"))
            .order_by(RepairTicket.id.desc()).first())
    try:
        seq = int(last[0].split("-")[-1]) + 1 if last else 1
    except ValueError:
        seq = 1
    return f"{prefix}{seq:04d}"


def _drawer_in_out(session: Session, user: User, amount: int, kind: str, ticket: RepairTicket, note: str) -> None:
    shift = shift_service.get_active_shift(session, user.id)
    if shift is None:
        raise RepairError(ar.REPAIR_NEEDS_SHIFT)
    drawer = session.query(CashAccount).filter_by(type="drawer").first()
    if drawer is None:
        return
    drawer.balance += amount if kind == "in" else -amount
    session.add(CashTransaction(account_id=drawer.id, type=kind, amount=amount, category="repair",
                                ref_type="repair", ref_id=ticket.id, shift_id=shift.id, user_id=user.id, note=note))


def create_ticket(session: Session, user: User, data: dict, deposit: int = 0) -> RepairTicket:
    """data: customer_name, customer_phone, customer_id?, device_desc, imei?, issue, estimate?, notes?"""
    require_permission(user.permission_codes(), PERM_SALES_CREATE, user.username)
    name = (data.get("customer_name") or "").strip()
    device = (data.get("device_desc") or "").strip()
    issue = (data.get("issue") or "").strip()
    if not name:
        raise RepairError(ar.REPAIR_NAME_REQUIRED)
    if not device:
        raise RepairError(ar.REPAIR_DEVICE_REQUIRED)
    if not issue:
        raise RepairError(ar.REPAIR_ISSUE_REQUIRED)
    estimate = int(data.get("estimate") or 0)
    if estimate < 0 or deposit < 0:
        raise RepairError(ar.REPAIR_BAD_AMOUNT)
    ticket = RepairTicket(
        ticket_no=_next_ticket_no(session), customer_id=data.get("customer_id"), customer_name=name,
        customer_phone=(data.get("customer_phone") or "").strip() or None, device_desc=device,
        imei=(data.get("imei") or "").strip() or None, issue=issue, estimate=estimate, final_price=estimate,
        notes=(data.get("notes") or "").strip() or None, received_by=user.id)
    session.add(ticket)
    session.flush()
    if deposit:
        _take_payment(session, user, ticket, deposit)
    log_action(session, "repair_create", user_id=user.id, table_name="repair_tickets", record_id=ticket.id,
               new_value={"ticket_no": ticket.ticket_no, "deposit": deposit})
    return ticket


def _take_payment(session: Session, user: User, ticket: RepairTicket, amount: int) -> None:
    _drawer_in_out(session, user, amount, "in", ticket, f"{ar.REPAIR_CASH_NOTE} {ticket.ticket_no}")
    ticket.paid += amount


def add_payment(session: Session, user: User, ticket_id: int, amount: int) -> RepairTicket:
    require_permission(user.permission_codes(), PERM_SALES_CREATE, user.username)
    ticket = _get(session, ticket_id)
    if ticket.status not in _ACTIVE:
        raise RepairError(ar.REPAIR_CLOSED)
    if amount <= 0:
        raise RepairError(ar.REPAIR_BAD_AMOUNT)
    _take_payment(session, user, ticket, amount)
    log_action(session, "repair_payment", user_id=user.id, table_name="repair_tickets", record_id=ticket.id,
               new_value={"amount": amount})
    return ticket


def set_status(session: Session, user: User, ticket_id: int, status: str) -> RepairTicket:
    require_permission(user.permission_codes(), PERM_SALES_CREATE, user.username)
    ticket = _get(session, ticket_id)
    if ticket.status not in _ACTIVE:
        raise RepairError(ar.REPAIR_CLOSED)
    if status not in _FLOW.get(ticket.status, set()):
        raise RepairError(ar.REPAIR_BAD_STATUS)
    old = ticket.status
    ticket.status = status
    if status == "ready":
        ticket.ready_at = clock.utcnow()
    log_action(session, "repair_status", user_id=user.id, table_name="repair_tickets", record_id=ticket.id,
               old_value={"status": old}, new_value={"status": status})
    return ticket


def set_pricing(session: Session, user: User, ticket_id: int, final_price: int, parts_cost: int | None = None) -> RepairTicket:
    """Final price the customer pays. Parts cost can only be entered by someone who may see costs."""
    require_permission(user.permission_codes(), PERM_SALES_CREATE, user.username)
    ticket = _get(session, ticket_id)
    if ticket.status not in _ACTIVE:
        raise RepairError(ar.REPAIR_CLOSED)
    if final_price < 0 or (parts_cost is not None and parts_cost < 0):
        raise RepairError(ar.REPAIR_BAD_AMOUNT)
    ticket.final_price = final_price
    if parts_cost is not None:
        require_permission(user.permission_codes(), PERM_COST_VIEW, user.username)
        ticket.parts_cost = parts_cost
    log_action(session, "repair_pricing", user_id=user.id, table_name="repair_tickets", record_id=ticket.id,
               new_value={"final_price": final_price})
    return ticket


def deliver(session: Session, user: User, ticket_id: int) -> RepairTicket:
    """Hand the device back. The ticket must be ready and fully paid (take the balance first)."""
    require_permission(user.permission_codes(), PERM_SALES_CREATE, user.username)
    ticket = _get(session, ticket_id)
    if ticket.status != "ready":
        raise RepairError(ar.REPAIR_NOT_READY)
    if ticket.balance > 0:
        raise RepairError(ar.REPAIR_BALANCE_DUE)
    ticket.status = "delivered"
    ticket.delivered_at = clock.utcnow()
    log_action(session, "repair_deliver", user_id=user.id, table_name="repair_tickets", record_id=ticket.id)
    return ticket


def cancel(session: Session, user: User, ticket_id: int, reason: str) -> RepairTicket:
    """Cancel an open ticket and give back whatever was paid (needs the return permission)."""
    require_permission(user.permission_codes(), PERM_SALES_RETURN, user.username)
    ticket = _get(session, ticket_id)
    if ticket.status not in _ACTIVE:
        raise RepairError(ar.REPAIR_CLOSED)
    if not (reason or "").strip():
        raise RepairError(ar.REPAIR_REASON_REQUIRED)
    refund = ticket.paid
    if refund:
        _drawer_in_out(session, user, refund, "out", ticket, f"{ar.REPAIR_REFUND_NOTE} {ticket.ticket_no}")
        ticket.paid = 0
    ticket.status = "cancelled"
    ticket.notes = ((ticket.notes + "\n") if ticket.notes else "") + f"{ar.REPAIR_CANCELLED_NOTE}: {reason.strip()}"
    log_action(session, "repair_cancel", user_id=user.id, table_name="repair_tickets", record_id=ticket.id,
               new_value={"refund": refund, "reason": reason.strip()})
    return ticket


def list_tickets(session: Session, user: User, status: str | None = None, text: str = "",
                 limit: int = 200) -> list[RepairTicket]:
    require_permission(user.permission_codes(), PERM_SALES_CREATE, user.username)
    q = session.query(RepairTicket)
    if status == "active":
        q = q.filter(RepairTicket.status.in_(_ACTIVE))
    elif status in REPAIR_STATUSES:
        q = q.filter(RepairTicket.status == status)
    text = (text or "").strip()
    if text:
        like = f"%{text}%"
        q = q.filter(RepairTicket.ticket_no.ilike(like) | RepairTicket.customer_name.ilike(like)
                     | RepairTicket.customer_phone.ilike(like) | RepairTicket.imei.ilike(like)
                     | RepairTicket.device_desc.ilike(like))
    return q.order_by(RepairTicket.id.desc()).limit(limit).all()


def _get(session: Session, ticket_id: int) -> RepairTicket:
    ticket = session.get(RepairTicket, ticket_id)
    if ticket is None:
        raise RepairError(ar.REPAIR_NOT_FOUND)
    return ticket


# ── customer message ─────────────────────────────────────────────────────────

def egypt_phone(raw: str | None) -> str | None:
    """Digits in international form for WhatsApp (01012345678 -> 201012345678). None if unusable."""
    digits = re.sub(r"\D", "", (raw or "").translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")))
    if digits.startswith("0020"):
        digits = digits[2:]
    if digits.startswith("20") and len(digits) == 12:
        return digits
    if digits.startswith("0") and len(digits) == 11:
        return "2" + digits
    return None


def ready_message(ticket: RepairTicket, shop_name: str, money_text: str) -> str:
    return ar.REPAIR_READY_MESSAGE.format(name=ticket.customer_name, device=ticket.device_desc,
                                          ticket=ticket.ticket_no, balance=money_text, shop=shop_name)


def whatsapp_link(phone: str | None, text: str) -> str | None:
    number = egypt_phone(phone)
    return f"https://wa.me/{number}?text={quote(text)}" if number else None
