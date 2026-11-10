"""Wallet service — electronic wallets (Vodafone, Orange, Etisalat, InstaPay),
commission calculation rules, limits enforcement, operations ledger, and audits.
"""
from __future__ import annotations

import datetime
from app.core.clock import utcnow
from decimal import Decimal
from typing import Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core import clock
from app.core.audit import log_action
from app.core.money import format_money
from app.core.permissions import (
    PERM_WALLET_AUDIT,
    PERM_WALLET_MANAGE,
    PERM_WALLET_USE,
    require_permission,
)
from app.models.accounting import CashAccount, CashTransaction
from app.models.user import User
from app.models.wallet import CommissionRule, Wallet, WalletAudit, WalletTransaction
from app.services import shift_service


class WalletError(Exception):
    """Base wallet operation error."""
    pass


class WalletNotFound(WalletError):
    pass


class DuplicateWalletPhone(WalletError):
    pass


class InsufficientWalletBalance(WalletError):
    pass


class InsufficientDrawerCash(WalletError):
    pass


class DailyLimitExceeded(WalletError):
    pass


class MonthlyLimitExceeded(WalletError):
    pass


class WalletShiftRequired(WalletError):
    pass


def _get_default_drawer(session: Session, account_id: Optional[int] = None) -> CashAccount:
    """Return drawer cash account."""
    if account_id:
        acc = session.get(CashAccount, account_id)
        if acc:
            return acc
    drawer = session.query(CashAccount).filter(CashAccount.type == "drawer").first()
    if not drawer:
        drawer = CashAccount(name="الدرج الرئيسي", type="drawer", balance=0)
        session.add(drawer)
        session.flush()
    return drawer


# ── Wallet Management ─────────────────────────────────────────────────────────

def create_wallet(
    session: Session,
    user: User,
    network: str,
    phone_number: str,
    label: str,
    initial_balance: int = 0,
    daily_limit: int = 0,
    monthly_limit: int = 0,
) -> Wallet:
    """Create a new electronic wallet line."""
    require_permission(user.permission_codes(), PERM_WALLET_MANAGE, user.username)

    clean_phone = phone_number.strip()
    clean_label = label.strip()
    clean_network = network.strip().lower()

    if not clean_phone or not clean_label:
        raise WalletError("رقم الهاتف واسم المحفظة مطلوبان")

    existing = session.query(Wallet).filter(Wallet.phone_number == clean_phone).first()
    if existing:
        raise DuplicateWalletPhone(f"رقم المحفظة '{clean_phone}' مسجل مسبقاً")

    wallet = Wallet(
        network=clean_network,
        phone_number=clean_phone,
        label=clean_label,
        balance=initial_balance,
        daily_limit=daily_limit,
        monthly_limit=monthly_limit,
        is_active=True,
    )
    session.add(wallet)
    session.flush()

    log_action(
        session,
        "create_wallet",
        user_id=user.id,
        table_name="wallets",
        record_id=wallet.id,
        new_value={
            "network": wallet.network,
            "phone": wallet.phone_number,
            "label": wallet.label,
            "balance": wallet.balance,
        },
    )
    return wallet


def update_wallet(
    session: Session,
    user: User,
    wallet_id: int,
    label: Optional[str] = None,
    daily_limit: Optional[int] = None,
    monthly_limit: Optional[int] = None,
    is_active: Optional[bool] = None,
) -> Wallet:
    require_permission(user.permission_codes(), PERM_WALLET_MANAGE, user.username)
    wallet = session.get(Wallet, wallet_id)
    if not wallet:
        raise WalletNotFound(f"المحفظة {wallet_id} غير موجودة")

    if label is not None:
        wallet.label = label.strip()
    if daily_limit is not None:
        wallet.daily_limit = daily_limit
    if monthly_limit is not None:
        wallet.monthly_limit = monthly_limit
    if is_active is not None:
        wallet.is_active = is_active

    session.flush()
    return wallet


def get_wallet(session: Session, user: User, wallet_id: int) -> Wallet:
    require_permission(user.permission_codes(), PERM_WALLET_USE, user.username)
    wallet = session.get(Wallet, wallet_id)
    if not wallet:
        raise WalletNotFound(f"المحفظة {wallet_id} غير موجودة")
    return wallet


def list_wallets(session: Session, user: User, active_only: bool = False) -> list[Wallet]:
    require_permission(user.permission_codes(), PERM_WALLET_USE, user.username)
    q = session.query(Wallet)
    if active_only:
        q = q.filter(Wallet.is_active == True)
    return q.order_by(Wallet.network.asc(), Wallet.label.asc()).all()


# ── Commission Rules ──────────────────────────────────────────────────────────

def create_commission_rule(
    session: Session,
    user: User,
    network: str,
    op_type: str,
    min_amount: int,
    max_amount: int,
    fixed_fee: int = 0,
    percent_bp: int = 0,
    network_fee: int = 0,
    paid_by: str = "customer",
) -> CommissionRule:
    """Create a new data-driven commission rule."""
    require_permission(user.permission_codes(), PERM_WALLET_MANAGE, user.username)

    rule = CommissionRule(
        network=network.strip().lower(),
        op_type=op_type.strip().lower(),
        min_amount=min_amount,
        max_amount=max_amount,
        fixed_fee=fixed_fee,
        percent_bp=percent_bp,
        network_fee=network_fee,
        paid_by=paid_by,
        is_active=True,
    )
    session.add(rule)
    session.flush()

    log_action(
        session,
        "create_commission_rule",
        user_id=user.id,
        table_name="commission_rules",
        record_id=rule.id,
        new_value={
            "network": rule.network,
            "op_type": rule.op_type,
            "min": rule.min_amount,
            "max": rule.max_amount,
            "fixed_fee": rule.fixed_fee,
            "percent_bp": rule.percent_bp,
        },
    )
    return rule


def list_commission_rules(
    session: Session,
    user: User,
    network: Optional[str] = None,
    op_type: Optional[str] = None,
) -> list[CommissionRule]:
    require_permission(user.permission_codes(), PERM_WALLET_USE, user.username)
    q = session.query(CommissionRule).filter(CommissionRule.is_active == True)
    if network:
        q = q.filter(CommissionRule.network == network.lower())
    if op_type:
        q = q.filter(CommissionRule.op_type == op_type.lower())
    return q.order_by(CommissionRule.network.asc(), CommissionRule.min_amount.asc()).all()


def compute_commission(
    session: Session,
    network: str,
    op_type: str,
    amount: int,
) -> Tuple[int, int]:
    """Find matching commission rule and compute (commission, network_fee) in piasters.

    Matches by network, op_type, and amount in range [min_amount, max_amount].
    Commission = fixed_fee + (amount * percent_bp) // 10000.
    """
    rule = (
        session.query(CommissionRule)
        .filter(
            CommissionRule.network == network.lower(),
            CommissionRule.op_type == op_type.lower(),
            CommissionRule.is_active == True,
            CommissionRule.min_amount <= amount,
            or_(CommissionRule.max_amount >= amount, CommissionRule.max_amount == 0),
        )
        .order_by(CommissionRule.min_amount.desc())
        .first()
    )

    if not rule:
        return 0, 0

    pct_commission = (amount * rule.percent_bp) // 10000
    total_commission = rule.fixed_fee + pct_commission
    return total_commission, rule.network_fee


# ── Wallet Limits & Usage ─────────────────────────────────────────────────────

def get_wallet_usage(
    session: Session,
    wallet_id: int,
    ref_date: Optional[datetime.datetime] = None,
) -> Tuple[int, int]:
    """Compute (used_today, used_month) in piasters from transactions without drifting."""
    # ref_date is a stored (naive UTC) moment; day/month are the shop's local ones
    local_ref = clock.to_local(ref_date) if ref_date is not None else clock.local_now()
    start_of_day, _ = clock.day_bounds_utc(local_ref.date())
    start_of_month, _ = clock.day_bounds_utc(local_ref.date().replace(day=1))

    # Operations consuming wallet transfer quota
    quota_ops = ["cash_in", "cash_out", "bill", "recharge"]

    used_today = (
        session.query(func.coalesce(func.sum(WalletTransaction.amount), 0))
        .filter(
            WalletTransaction.wallet_id == wallet_id,
            WalletTransaction.op_type.in_(quota_ops),
            WalletTransaction.created_at >= start_of_day,
        )
        .scalar()
        or 0
    )

    used_month = (
        session.query(func.coalesce(func.sum(WalletTransaction.amount), 0))
        .filter(
            WalletTransaction.wallet_id == wallet_id,
            WalletTransaction.op_type.in_(quota_ops),
            WalletTransaction.created_at >= start_of_month,
        )
        .scalar()
        or 0
    )

    return used_today, used_month


# ── Execute Operations Matrix ─────────────────────────────────────────────────

def execute_wallet_transaction(
    session: Session,
    user: User,
    wallet_id: int,
    op_type: str,
    amount: int,
    customer_phone: Optional[str] = None,
    custom_commission: Optional[int] = None,
    cost_price: Optional[int] = None,  # for recharge
    reference: Optional[str] = None,
    note: Optional[str] = None,
    account_id: Optional[int] = None,
) -> WalletTransaction:
    """Execute a wallet operation atomically following the exact AGENTS.md §6 matrix.

    | op_type  | cash_effect            | wallet_effect | profit                  |
    |----------|------------------------|---------------|-------------------------|
    | cash_in  | +(amount + commission) | -amount       | commission - network_fee |
    | cash_out | -amount                | +amount       | commission - network_fee|
    | recharge | +sale_price            | -cost_price   | sale_price - cost_price |
    | bill     | +(amount + commission) | -amount       | commission - network_fee |
    | fund     | -amount                | +amount       | 0                       |
    | withdraw | +amount                | -amount       | 0                       |
    """
    require_permission(user.permission_codes(), PERM_WALLET_USE, user.username)

    if amount <= 0:
        raise WalletError("المبلغ يجب أن يكون أكبر من الصفر")

    wallet = session.get(Wallet, wallet_id)
    if not wallet or not wallet.is_active:
        raise WalletNotFound(f"المحفظة {wallet_id} غير موجودة أو معطلة")

    # Shift requirement for cashiers
    shift = shift_service.get_active_shift(session, user.id)
    if not shift and user.role and user.role.name != "manager":
        raise WalletShiftRequired("لا يمكن إجراء عمليات المحافظ بدون وردية مفتوحة للمستخدم")

    # Commission & Network Fee
    rule_comm, network_fee = compute_commission(session, wallet.network, op_type, amount)
    if custom_commission is not None and custom_commission != rule_comm:
        # User manually overrode commission
        if PERM_WALLET_MANAGE not in user.permission_codes():
            require_permission(user.permission_codes(), PERM_WALLET_MANAGE, user.username)
        commission = custom_commission
    else:
        commission = rule_comm

    # Compute effects per operation type (§6 matrix)
    if op_type == "cash_in":
        cash_effect = amount + commission
        wallet_effect = -amount
        profit = commission - network_fee

    elif op_type == "cash_out":
        cash_effect = -amount
        wallet_effect = amount
        profit = commission - network_fee if commission else 0

    elif op_type == "recharge":
        # amount is the sale_price paid by customer
        recharge_cost = cost_price if cost_price is not None else (amount - commission)
        cash_effect = amount
        wallet_effect = -recharge_cost
        profit = amount - recharge_cost

    elif op_type == "bill":
        cash_effect = amount + commission
        wallet_effect = -amount
        profit = commission - network_fee

    elif op_type == "fund":  # shop funds wallet from drawer
        cash_effect = -amount
        wallet_effect = amount
        profit = 0

    elif op_type == "withdraw":  # shop withdraws wallet balance to drawer
        cash_effect = amount
        wallet_effect = -amount
        profit = 0

    else:
        raise WalletError(f"نوع العملية '{op_type}' غير مدعوم")

    # ── Checks ──
    # 1. Daily & Monthly Limit Checks (for customer operations)
    if op_type in ("cash_in", "cash_out", "bill", "recharge"):
        used_today, used_month = get_wallet_usage(session, wallet.id)
        if wallet.daily_limit > 0 and (used_today + amount) > wallet.daily_limit:
            raise DailyLimitExceeded(
                f"تجاوز الحد اليومي للمحفظة ({format_money(wallet.daily_limit)}). تم استخدام: {format_money(used_today)}"
            )
        if wallet.monthly_limit > 0 and (used_month + amount) > wallet.monthly_limit:
            raise MonthlyLimitExceeded(
                f"تجاوز الحد الشهري للمحفظة ({format_money(wallet.monthly_limit)}). تم استخدام: {format_money(used_month)}"
            )

    # 2. Wallet balance check (when wallet_effect < 0)
    if wallet_effect < 0 and wallet.balance < abs(wallet_effect):
        raise InsufficientWalletBalance(
            f"رصيد المحفظة غير كافٍ. الرصيد الحالي: {format_money(wallet.balance)}، المطلوب: {format_money(abs(wallet_effect))}"
        )

    # 3. Cash Drawer balance check (when cash_effect < 0)
    cash_acc = _get_default_drawer(session, account_id)
    if cash_effect < 0 and cash_acc.balance < abs(cash_effect):
        raise InsufficientDrawerCash(
            f"رصيد الدرج غير كافٍ لصرف النقدية. الرصيد بالدرج: {format_money(cash_acc.balance)}، المطلوب: {format_money(abs(cash_effect))}"
        )

    # Apply wallet balance change
    wallet.balance += wallet_effect

    # Apply drawer cash balance change & ledger transaction
    if cash_effect != 0:
        cash_acc.balance += cash_effect
        tx_type = "in" if cash_effect > 0 else "out"
        cash_tx = CashTransaction(
            account_id=cash_acc.id,
            type=tx_type,
            amount=abs(cash_effect),
            category=f"wallet_{op_type}",
            ref_type="wallet_transaction",
            shift_id=shift.id if shift else None,
            user_id=user.id,
            note=f"عملية محفظة: {wallet.label} ({op_type}) - هاتف: {customer_phone or '—'}",
        )
        session.add(cash_tx)

    # Record wallet transaction
    tx = WalletTransaction(
        wallet_id=wallet.id,
        op_type=op_type,
        customer_phone=customer_phone.strip() if customer_phone else None,
        amount=amount,
        commission=commission,
        network_fee=network_fee,
        profit=profit,
        cash_effect=cash_effect,
        wallet_effect=wallet_effect,
        reference=reference.strip() if reference else None,
        user_id=user.id,
        shift_id=shift.id if shift else None,
        note=note.strip() if note else None,
        created_at=utcnow(),
    )
    session.add(tx)
    session.flush()

    log_action(
        session,
        "execute_wallet_op",
        user_id=user.id,
        table_name="wallet_transactions",
        record_id=tx.id,
        new_value={
            "wallet_id": wallet.id,
            "op_type": op_type,
            "amount": amount,
            "profit": profit,
            "cash_effect": cash_effect,
            "wallet_effect": wallet_effect,
            "new_wallet_balance": wallet.balance,
        },
    )
    return tx


# ── Wallet Audit ──────────────────────────────────────────────────────────────

def audit_wallet(
    session: Session,
    user: User,
    wallet_id: int,
    actual_balance: int,
    note: Optional[str] = None,
) -> WalletAudit:
    """Record end-of-day or shift physical wallet audit comparing system vs actual."""
    require_permission(user.permission_codes(), PERM_WALLET_AUDIT, user.username)

    wallet = session.get(Wallet, wallet_id)
    if not wallet:
        raise WalletNotFound(f"المحفظة {wallet_id} غير موجودة")

    diff = actual_balance - wallet.balance

    audit = WalletAudit(
        wallet_id=wallet.id,
        system_balance=wallet.balance,
        actual_balance=actual_balance,
        diff=diff,
        user_id=user.id,
        note=note.strip() if note else None,
        created_at=utcnow(),
    )
    session.add(audit)
    session.flush()

    log_action(
        session,
        "audit_wallet",
        user_id=user.id,
        table_name="wallet_audits",
        record_id=audit.id,
        new_value={
            "wallet_id": wallet.id,
            "system_balance": audit.system_balance,
            "actual_balance": audit.actual_balance,
            "diff": audit.diff,
        },
    )
    return audit


def list_wallet_transactions(
    session: Session,
    user: User,
    wallet_id: Optional[int] = None,
    op_type: Optional[str] = None,
    limit: int = 100,
) -> list[WalletTransaction]:
    require_permission(user.permission_codes(), PERM_WALLET_USE, user.username)
    q = session.query(WalletTransaction)
    if wallet_id:
        q = q.filter(WalletTransaction.wallet_id == wallet_id)
    if op_type:
        q = q.filter(WalletTransaction.op_type == op_type)
    return q.order_by(WalletTransaction.created_at.desc()).limit(limit).all()
