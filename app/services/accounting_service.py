"""Accounting service — cash drawers, safes, expenses, owner draws,
account-to-account transfers, shift reconciliation, and daily close reports.
"""
from __future__ import annotations

import datetime
from app.core.clock import utcnow
from typing import Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core import clock
from app.core.audit import log_action
from app.core.money import format_money
from app.core.permissions import (
    PERM_CASH_CLOSE_DAY,
    PERM_CASH_EXPENSE,
    PERM_CASH_VIEW,
    require_permission,
)
from app.models.accounting import (
    CashAccount,
    CashTransaction,
    Expense,
    ExpenseCategory,
    OwnerDraw,
)
from app.models.purchase import Purchase
from app.models.sale import Sale
from app.models.shift import Shift
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction
from app.services import shift_service


class AccountingError(Exception):
    """Base accounting service error."""
    pass


class InsufficientFunds(AccountingError):
    pass


class AccountNotFound(AccountingError):
    pass


# ── Account Management ────────────────────────────────────────────────────────

def create_account(
    session: Session,
    user: User,
    name: str,
    account_type: str = "safe",
    initial_balance: int = 0,
) -> CashAccount:
    """Create a new cash account (safe, bank, drawer)."""
    require_permission(user.permission_codes(), PERM_CASH_CLOSE_DAY, user.username)

    clean_name = name.strip()
    if not clean_name:
        raise AccountingError("اسم الحساب مطلوب")

    existing = session.query(CashAccount).filter(CashAccount.name == clean_name).first()
    if existing:
        raise AccountingError(f"الحساب '{clean_name}' مسجل مسبقاً")

    acc = CashAccount(
        name=clean_name,
        type=account_type.strip().lower(),
        balance=initial_balance,
    )
    session.add(acc)
    session.flush()

    if initial_balance > 0:
        tx = CashTransaction(
            account_id=acc.id,
            type="in",
            amount=initial_balance,
            category="initial_balance",
            ref_type="account",
            ref_id=acc.id,
            user_id=user.id,
            note="رصيد افتتاحي للحساب",
        )
        session.add(tx)
        session.flush()

    log_action(
        session,
        "create_cash_account",
        user_id=user.id,
        table_name="cash_accounts",
        record_id=acc.id,
        new_value={"name": acc.name, "type": acc.type, "balance": acc.balance},
    )
    return acc


def list_accounts(session: Session, user: User) -> list[CashAccount]:
    require_permission(user.permission_codes(), PERM_CASH_VIEW, user.username)
    return session.query(CashAccount).order_by(CashAccount.type.asc(), CashAccount.id.asc()).all()


def get_account(session: Session, user: User, account_id: int) -> CashAccount:
    require_permission(user.permission_codes(), PERM_CASH_VIEW, user.username)
    acc = session.get(CashAccount, account_id)
    if not acc:
        raise AccountNotFound(f"الحساب {account_id} غير موجود")
    return acc


# ── Expense Categories & Expenses ─────────────────────────────────────────────

def create_expense_category(session: Session, user: User, name: str) -> ExpenseCategory:
    require_permission(user.permission_codes(), PERM_CASH_EXPENSE, user.username)
    clean_name = name.strip()
    if not clean_name:
        raise AccountingError("اسم بند المصروف مطلوب")

    existing = session.query(ExpenseCategory).filter(ExpenseCategory.name == clean_name).first()
    if existing:
        return existing

    cat = ExpenseCategory(name=clean_name)
    session.add(cat)
    session.flush()
    return cat


def list_expense_categories(session: Session, user: User) -> list[ExpenseCategory]:
    require_permission(user.permission_codes(), PERM_CASH_VIEW, user.username)
    return session.query(ExpenseCategory).order_by(ExpenseCategory.name.asc()).all()


def add_expense(
    session: Session,
    user: User,
    category_id: int,
    amount: int,
    account_id: int,
    note: Optional[str] = None,
) -> Expense:
    """Record a shop operating expense, reducing account cash and logging a transaction."""
    require_permission(user.permission_codes(), PERM_CASH_EXPENSE, user.username)

    if amount <= 0:
        raise AccountingError("مبلغ المصروف يجب أن يكون أكبر من الصفر")

    cat = session.get(ExpenseCategory, category_id)
    if not cat:
        raise AccountingError(f"بند المصروف {category_id} غير موجود")

    acc = session.get(CashAccount, account_id)
    if not acc:
        raise AccountNotFound(f"الحساب {account_id} غير موجود")

    if acc.balance < amount:
        raise InsufficientFunds(
            f"الرصيد في {acc.name} غير كافٍ. المتاح: {format_money(acc.balance)}، المطلوب: {format_money(amount)}"
        )

    # Get active shift if user has one
    shift = shift_service.get_active_shift(session, user.id)

    # Deduct from account
    acc.balance -= amount

    # Record CashTransaction
    cash_tx = CashTransaction(
        account_id=acc.id,
        type="out",
        amount=amount,
        category="expense",
        ref_type="expense",
        shift_id=shift.id if shift else None,
        user_id=user.id,
        note=f"مصروف: {cat.name} — {note or ''}".strip(),
    )
    session.add(cash_tx)
    session.flush()

    # Record Expense
    expense = Expense(
        category_id=cat.id,
        amount=amount,
        account_id=acc.id,
        note=note.strip() if note else None,
        cash_transaction_id=cash_tx.id,
        user_id=user.id,
        created_at=utcnow(),
    )
    session.add(expense)
    session.flush()

    log_action(
        session,
        "add_expense",
        user_id=user.id,
        table_name="expenses",
        record_id=expense.id,
        new_value={
            "category": cat.name,
            "amount": amount,
            "account": acc.name,
            "new_balance": acc.balance,
        },
    )
    return expense


# ── Owner Draws ───────────────────────────────────────────────────────────────

def owner_draw(
    session: Session,
    user: User,
    amount: int,
    account_id: int,
    note: Optional[str] = None,
) -> OwnerDraw:
    """Record an owner cash drawing, kept strictly separate from operational expenses."""
    require_permission(user.permission_codes(), PERM_CASH_CLOSE_DAY, user.username)

    if amount <= 0:
        raise AccountingError("مبلغ سحوبات المالك يجب أن يكون أكبر من الصفر")

    acc = session.get(CashAccount, account_id)
    if not acc:
        raise AccountNotFound(f"الحساب {account_id} غير موجود")

    if acc.balance < amount:
        raise InsufficientFunds(
            f"الرصيد في {acc.name} غير كافٍ. المتاح: {format_money(acc.balance)}، المطلوب: {format_money(amount)}"
        )

    shift = shift_service.get_active_shift(session, user.id)

    acc.balance -= amount

    cash_tx = CashTransaction(
        account_id=acc.id,
        type="out",
        amount=amount,
        category="owner_draw",
        ref_type="owner_draw",
        shift_id=shift.id if shift else None,
        user_id=user.id,
        note=f"مسحوبات مالك: {note or ''}".strip(),
    )
    session.add(cash_tx)
    session.flush()

    draw = OwnerDraw(
        amount=amount,
        account_id=acc.id,
        note=note.strip() if note else None,
        user_id=user.id,
        created_at=utcnow(),
    )
    session.add(draw)
    session.flush()

    log_action(
        session,
        "owner_draw",
        user_id=user.id,
        table_name="owner_draws",
        record_id=draw.id,
        new_value={"amount": amount, "account": acc.name, "new_balance": acc.balance},
    )
    return draw


# ── Internal Transfers ────────────────────────────────────────────────────────

def transfer(
    session: Session,
    user: User,
    from_account_id: int,
    to_account_id: int,
    amount: int,
    note: Optional[str] = None,
) -> Tuple[CashTransaction, CashTransaction]:
    """Transfer cash between accounts (e.g. Drawer -> Safe, Safe -> Bank) atomically."""
    require_permission(user.permission_codes(), PERM_CASH_VIEW, user.username)

    if from_account_id == to_account_id:
        raise AccountingError("لا يمكن التحويل لنفس الحساب")

    if amount <= 0:
        raise AccountingError("مبلغ التحويل يجب أن يكون أكبر من الصفر")

    acc_from = session.get(CashAccount, from_account_id)
    acc_to = session.get(CashAccount, to_account_id)

    if not acc_from or not acc_to:
        raise AccountNotFound("أحد حسابات التحويل غير موجود")

    if acc_from.balance < amount:
        raise InsufficientFunds(
            f"الرصيد في {acc_from.name} غير كافٍ للتحويل. المتاح: {format_money(acc_from.balance)}، المطلوب: {format_money(amount)}"
        )

    shift = shift_service.get_active_shift(session, user.id)

    # Balance changes
    acc_from.balance -= amount
    acc_to.balance += amount

    # Transaction 1: Outflow from source
    tx_out = CashTransaction(
        account_id=acc_from.id,
        type="transfer_out",
        amount=amount,
        category="transfer",
        ref_type="cash_account",
        ref_id=acc_to.id,
        shift_id=shift.id if shift else None,
        user_id=user.id,
        note=f"تحويل إلى {acc_to.name}: {note or ''}".strip(),
    )
    session.add(tx_out)

    # Transaction 2: Inflow to destination
    tx_in = CashTransaction(
        account_id=acc_to.id,
        type="transfer_in",
        amount=amount,
        category="transfer",
        ref_type="cash_account",
        ref_id=acc_from.id,
        shift_id=shift.id if shift else None,
        user_id=user.id,
        note=f"تحويل وارد من {acc_from.name}: {note or ''}".strip(),
    )
    session.add(tx_in)
    session.flush()

    log_action(
        session,
        "transfer_cash",
        user_id=user.id,
        table_name="cash_transactions",
        record_id=tx_out.id,
        new_value={
            "from": acc_from.name,
            "to": acc_to.name,
            "amount": amount,
            "from_balance": acc_from.balance,
            "to_balance": acc_to.balance,
        },
    )
    return tx_out, tx_in


# ── Balance Integrity Verification ───────────────────────────────────────────

def verify_drawer_balance_integrity(session: Session, account_id: int) -> bool:
    """Acceptance test criterion: drawer balance equals sum of its transactions at all times."""
    acc = session.get(CashAccount, account_id)
    if not acc:
        return False

    in_sum = (
        session.query(func.coalesce(func.sum(CashTransaction.amount), 0))
        .filter(
            CashTransaction.account_id == account_id,
            CashTransaction.type.in_(["in", "transfer_in"]),
        )
        .scalar()
        or 0
    )

    out_sum = (
        session.query(func.coalesce(func.sum(CashTransaction.amount), 0))
        .filter(
            CashTransaction.account_id == account_id,
            CashTransaction.type.in_(["out", "transfer_out"]),
        )
        .scalar()
        or 0
    )

    computed_balance = in_sum - out_sum
    return acc.balance == computed_balance


# ── Daily Close Report ────────────────────────────────────────────────────────

def daily_close(
    session: Session,
    user: User,
    ref_date: Optional[datetime.date] = None,
) -> dict:
    """Generate consolidated manager daily financial close report."""
    require_permission(user.permission_codes(), PERM_CASH_CLOSE_DAY, user.username)

    if ref_date is None:
        ref_date = clock.local_today()

    start_dt, end_dt = clock.day_bounds_utc(ref_date)

    # 1. Sales
    sales_q = session.query(Sale).filter(Sale.created_at >= start_dt, Sale.created_at <= end_dt, Sale.status == "posted")
    sales_list = sales_q.all()
    sales_count = len(sales_list)
    sales_total = sum(s.total for s in sales_list)
    sales_paid = sum(s.paid for s in sales_list)
    sales_profit = sum(s.total_profit for s in sales_list)

    # 2. Purchases
    pur_q = session.query(Purchase).filter(Purchase.created_at >= start_dt, Purchase.created_at <= end_dt, Purchase.status == "posted")
    pur_count = pur_q.count()
    pur_total = pur_q.with_entities(func.coalesce(func.sum(Purchase.total), 0)).scalar() or 0
    pur_paid = pur_q.with_entities(func.coalesce(func.sum(Purchase.paid), 0)).scalar() or 0

    # 3. Expenses
    exp_q = session.query(Expense).filter(Expense.created_at >= start_dt, Expense.created_at <= end_dt)
    exp_total = exp_q.with_entities(func.coalesce(func.sum(Expense.amount), 0)).scalar() or 0

    # 4. Owner Draws
    draw_q = session.query(OwnerDraw).filter(OwnerDraw.created_at >= start_dt, OwnerDraw.created_at <= end_dt)
    draw_total = draw_q.with_entities(func.coalesce(func.sum(OwnerDraw.amount), 0)).scalar() or 0

    # 5. Wallets
    w_q = session.query(WalletTransaction).filter(WalletTransaction.created_at >= start_dt, WalletTransaction.created_at <= end_dt)
    wallet_comm = w_q.with_entities(func.coalesce(func.sum(WalletTransaction.commission), 0)).scalar() or 0
    wallet_profit = w_q.with_entities(func.coalesce(func.sum(WalletTransaction.profit), 0)).scalar() or 0

    # 6. Shifts
    shifts_q = session.query(Shift).filter(
        Shift.opened_at >= start_dt,
        Shift.opened_at <= end_dt,
        Shift.status == "closed",
    )
    shift_diff_total = shifts_q.with_entities(func.coalesce(func.sum(Shift.diff), 0)).scalar() or 0

    # Net Profit = Sales profit + Wallet profit - Expenses + Shift diff
    net_profit = sales_profit + wallet_profit - exp_total + shift_diff_total

    # 7. Current Balances Snapshot
    accounts = session.query(CashAccount).all()
    wallets = session.query(Wallet).all()

    account_balances = {acc.name: acc.balance for acc in accounts}
    wallet_balances = {w.label: w.balance for w in wallets}

    report = {
        "date": ref_date.strftime("%Y-%m-%d"),
        "sales": {
            "count": sales_count,
            "total": sales_total,
            "paid": sales_paid,
            "profit": sales_profit,
        },
        "purchases": {
            "count": pur_count,
            "total": pur_total,
            "paid": pur_paid,
        },
        "expenses": exp_total,
        "owner_draws": draw_total,
        "wallets": {
            "commission": wallet_comm,
            "profit": wallet_profit,
        },
        "shift_diff": shift_diff_total,
        "net_profit": net_profit,
        "balances": {
            "accounts": account_balances,
            "wallets": wallet_balances,
            "total_cash": sum(account_balances.values()),
            "total_wallets": sum(wallet_balances.values()),
        },
    }

    log_action(
        session,
        "daily_close_report",
        user_id=user.id,
        table_name="shifts",
        record_id=0,
        new_value={"date": report["date"], "net_profit": net_profit},
    )
    return report


# Re-export shift functions for clean unified accounting API
open_shift = shift_service.open_shift
close_shift = shift_service.close_shift
get_active_shift = shift_service.get_active_shift
