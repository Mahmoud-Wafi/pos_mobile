"""Reporting service — sales, profits, inventory, wallets, debts, and cash ledger reports.

Provides data aggregation and exports to structured dictionaries and Excel/PDF.
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core import clock
from app.core.money import format_money
from app.core.money import piasters_to_input
from app.core.permissions import (
    PERM_PROFIT_VIEW,
    PERM_REPORTS_PROFIT,
    PERM_REPORTS_VIEW,
    require_permission,
)
from app.models.accounting import CashAccount, CashTransaction, Expense, OwnerDraw
from app.models.customer import Customer, CustomerPayment
from app.models.product import Category, Product
from app.models.purchase import Purchase, Supplier, SupplierPayment
from app.models.sale import Sale, SaleItem
from app.models.shift import Shift
from app.models.stock import Device, Stock
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction


def _date_bounds(
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
) -> tuple[datetime.datetime, datetime.datetime]:
    today = clock.local_today()
    s = start_date or today
    e = end_date or today
    return clock.day_bounds_utc(s, e)


# ── 1. Sales Report ───────────────────────────────────────────────────────────

def sales_report(
    session: Session,
    user: User,
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
) -> dict[str, Any]:
    """Detailed sales report for a specified date range."""
    require_permission(user.permission_codes(), PERM_REPORTS_VIEW, user.username)
    start_dt, end_dt = _date_bounds(start_date, end_date)

    sales = (
        session.query(Sale)
        .filter(Sale.created_at >= start_dt, Sale.created_at <= end_dt, Sale.status == "posted")
        .order_by(Sale.created_at.desc())
        .all()
    )

    total_invoices = len(sales)
    total_subtotal = sum(s.subtotal for s in sales)
    total_discount = sum(s.discount for s in sales)
    total_net = sum(s.total for s in sales)
    total_paid = sum(s.paid for s in sales)
    total_remaining = sum(s.remaining for s in sales)
    total_profit = sum(s.total_profit for s in sales) if PERM_PROFIT_VIEW in user.permission_codes() else 0

    rows = []
    for s in sales:
        rows.append({
            "id": s.id,
            "invoice_no": s.invoice_no,
            "customer_name": s.customer.name if s.customer else "عميل نقدي",
            "date": clock.fmt_local(s.created_at, "%Y-%m-%d %H:%M"),
            "items_count": len(s.items),
            "subtotal": s.subtotal,
            "discount": s.discount,
            "total": s.total,
            "paid": s.paid,
            "remaining": s.remaining,
            "profit": s.total_profit if PERM_PROFIT_VIEW in user.permission_codes() else None,
            "cashier": s.user.full_name if s.user else "—",
        })

    return {
        "title": "تقرير المبيعات",
        "start_date": clock.to_local(start_dt).strftime("%Y-%m-%d"),
        "end_date": clock.to_local(end_dt).strftime("%Y-%m-%d"),
        "total_invoices": total_invoices,
        "total_subtotal": total_subtotal,
        "total_discount": total_discount,
        "total_net": total_net,
        "total_paid": total_paid,
        "total_remaining": total_remaining,
        "total_profit": total_profit,
        "rows": rows,
    }


# ── 2. Profit Report ──────────────────────────────────────────────────────────

def profit_report(
    session: Session,
    user: User,
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
) -> dict[str, Any]:
    """Consolidated business profit & loss statement for period."""
    require_permission(user.permission_codes(), PERM_REPORTS_PROFIT, user.username)
    start_dt, end_dt = _date_bounds(start_date, end_date)

    # 1. Sales profit
    sales = (
        session.query(Sale)
        .filter(Sale.created_at >= start_dt, Sale.created_at <= end_dt, Sale.status == "posted")
        .all()
    )
    sales_profit = sum(s.total_profit for s in sales)
    sales_revenue = sum(s.total for s in sales)

    # 2. Wallet profit
    wallet_txs = (
        session.query(WalletTransaction)
        .filter(WalletTransaction.created_at >= start_dt, WalletTransaction.created_at <= end_dt)
        .all()
    )
    wallet_comm = sum(t.commission for t in wallet_txs)
    wallet_profit = sum(t.profit for t in wallet_txs)

    # 3. Expenses
    expenses = (
        session.query(Expense)
        .filter(Expense.created_at >= start_dt, Expense.created_at <= end_dt)
        .all()
    )
    total_expenses = sum(e.amount for e in expenses)

    # 4. Shifts shortages / overages
    shifts = (
        session.query(Shift)
        .filter(Shift.opened_at >= start_dt, Shift.opened_at <= end_dt, Shift.status == "closed")
        .all()
    )
    shift_diff_total = sum(sh.diff for sh in shifts)

    # Net Profit = Sales profit + Wallet profit - Expenses + Shift diff
    net_profit = sales_profit + wallet_profit - total_expenses + shift_diff_total

    return {
        "title": "تقرير الأرباح والخسائر الشامل (P&L)",
        "start_date": clock.to_local(start_dt).strftime("%Y-%m-%d"),
        "end_date": clock.to_local(end_dt).strftime("%Y-%m-%d"),
        "sales_revenue": sales_revenue,
        "sales_profit": sales_profit,
        "wallet_commission": wallet_comm,
        "wallet_profit": wallet_profit,
        "total_expenses": total_expenses,
        "shift_diff": shift_diff_total,
        "net_profit": net_profit,
        "sales_count": len(sales),
        "wallet_tx_count": len(wallet_txs),
        "expenses_count": len(expenses),
    }


# ── 3. Stock Report ───────────────────────────────────────────────────────────

def stock_report(
    session: Session,
    user: User,
    category_id: Optional[int] = None,
    low_stock_only: bool = False,
) -> dict[str, Any]:
    """Inventory valuation and stock levels report."""
    require_permission(user.permission_codes(), PERM_REPORTS_VIEW, user.username)

    q = session.query(Product).filter(Product.is_active == True)
    if category_id:
        q = q.filter(Product.category_id == category_id)

    products = q.order_by(Product.type.asc(), Product.name.asc()).all()

    rows = []
    total_stock_value = 0
    total_retail_value = 0
    low_stock_count = 0

    for p in products:
        qty = p.current_quantity()
        is_low = qty <= p.min_stock

        if low_stock_only and not is_low:
            continue

        if is_low:
            low_stock_count += 1

        cost_val = qty * p.cost_price
        sale_val = qty * p.sale_price
        total_stock_value += cost_val
        total_retail_value += sale_val

        rows.append({
            "id": p.id,
            "name": p.name,
            "type": p.type,
            "barcode": p.barcode or "—",
            "quantity": qty,
            "min_stock": p.min_stock,
            "is_low": is_low,
            "cost_price": p.cost_price if PERM_PROFIT_VIEW in user.permission_codes() else None,
            "sale_price": p.sale_price,
            "stock_cost_value": cost_val if PERM_PROFIT_VIEW in user.permission_codes() else None,
            "stock_sale_value": sale_val,
        })

    return {
        "title": "تقرير جرد وتقييم المخزون",
        "total_products": len(rows),
        "low_stock_count": low_stock_count,
        "total_stock_cost_value": total_stock_value if PERM_PROFIT_VIEW in user.permission_codes() else None,
        "total_stock_sale_value": total_retail_value,
        "rows": rows,
    }


# ── 4. Wallet Report ──────────────────────────────────────────────────────────

def wallet_report(
    session: Session,
    user: User,
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
    wallet_id: Optional[int] = None,
) -> dict[str, Any]:
    """Electronic wallets operational and commissions report."""
    require_permission(user.permission_codes(), PERM_REPORTS_VIEW, user.username)
    start_dt, end_dt = _date_bounds(start_date, end_date)

    q = session.query(WalletTransaction).filter(
        WalletTransaction.created_at >= start_dt,
        WalletTransaction.created_at <= end_dt,
    )
    if wallet_id:
        q = q.filter(WalletTransaction.wallet_id == wallet_id)

    txs = q.order_by(WalletTransaction.created_at.desc()).all()

    total_amount = sum(t.amount for t in txs)
    total_commission = sum(t.commission for t in txs)
    total_profit = sum(t.profit for t in txs)
    total_cash_in = sum(t.amount for t in txs if t.op_type == "cash_in")
    total_cash_out = sum(t.amount for t in txs if t.op_type == "cash_out")

    rows = []
    for t in txs:
        rows.append({
            "id": t.id,
            "wallet_label": t.wallet.label if t.wallet else "—",
            "op_type": t.op_type,
            "phone": t.customer_phone or "—",
            "amount": t.amount,
            "commission": t.commission,
            "profit": t.profit,
            "cash_effect": t.cash_effect,
            "wallet_effect": t.wallet_effect,
            "date": clock.fmt_local(t.created_at, "%Y-%m-%d %H:%M"),
        })

    return {
        "title": "تقرير حركة المحافظ الإلكترونية والعمولات",
        "start_date": clock.to_local(start_dt).strftime("%Y-%m-%d"),
        "end_date": clock.to_local(end_dt).strftime("%Y-%m-%d"),
        "total_operations": len(txs),
        "total_amount": total_amount,
        "total_commission": total_commission,
        "total_profit": total_profit,
        "total_cash_in": total_cash_in,
        "total_cash_out": total_cash_out,
        "rows": rows,
    }


# ── 5. Debts Report ───────────────────────────────────────────────────────────

def debts_report(session: Session, user: User) -> dict[str, Any]:
    """Summary of customer debts (receivables) and supplier balances (payables)."""
    require_permission(user.permission_codes(), PERM_REPORTS_VIEW, user.username)

    # Customer receivables
    customers = session.query(Customer).filter(Customer.balance > 0).order_by(Customer.balance.desc()).all()
    total_receivables = sum(c.balance for c in customers)

    customer_rows = []
    for c in customers:
        customer_rows.append({
            "id": c.id,
            "name": c.name,
            "phone": c.phone or "—",
            "balance": c.balance,
            "credit_limit": c.credit_limit,
        })

    # Supplier payables
    suppliers = session.query(Supplier).filter(Supplier.balance > 0).order_by(Supplier.balance.desc()).all()
    total_payables = sum(s.balance for s in suppliers)

    supplier_rows = []
    for s in suppliers:
        supplier_rows.append({
            "id": s.id,
            "name": s.name,
            "phone": s.phone or "—",
            "balance": s.balance,
        })

    return {
        "title": "تقرير المديونيات وحسابات الآجل",
        "total_receivables": total_receivables,
        "total_payables": total_payables,
        "net_debt_position": total_receivables - total_payables,
        "customers_count": len(customer_rows),
        "suppliers_count": len(supplier_rows),
        "customers": customer_rows,
        "suppliers": supplier_rows,
    }


# ── 6. Cash Report ────────────────────────────────────────────────────────────

def cash_report(
    session: Session,
    user: User,
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
) -> dict[str, Any]:
    """Complete cash movements ledger and account reconciliations."""
    require_permission(user.permission_codes(), PERM_REPORTS_VIEW, user.username)
    start_dt, end_dt = _date_bounds(start_date, end_date)

    txs = (
        session.query(CashTransaction)
        .filter(CashTransaction.created_at >= start_dt, CashTransaction.created_at <= end_dt)
        .order_by(CashTransaction.created_at.desc())
        .all()
    )

    in_total = sum(t.amount for t in txs if t.type in ("in", "transfer_in"))
    out_total = sum(t.amount for t in txs if t.type in ("out", "transfer_out"))

    accounts = session.query(CashAccount).all()
    account_balances = {a.name: a.balance for a in accounts}

    return {
        "title": "تقرير حركة النقدية والخزائن",
        "start_date": clock.to_local(start_dt).strftime("%Y-%m-%d"),
        "end_date": clock.to_local(end_dt).strftime("%Y-%m-%d"),
        "total_in": in_total,
        "total_out": out_total,
        "net_cash_flow": in_total - out_total,
        "accounts": account_balances,
        "total_cash_now": sum(account_balances.values()),
        "transactions_count": len(txs),
    }


# ── 7. Dashboard Metrics ──────────────────────────────────────────────────────

def dashboard_metrics(session: Session, user: User) -> dict[str, Any]:
    """Summary KPI metrics for landing dashboard."""
    today = clock.local_today()
    start_dt, end_dt = _date_bounds(today, today)
    perm_codes = user.permission_codes()

    # Sales today
    sales_today = (
        session.query(Sale)
        .filter(Sale.created_at >= start_dt, Sale.created_at <= end_dt, Sale.status == "posted")
        .order_by(Sale.created_at.desc())
        .all()
    )
    sales_count = len(sales_today)
    sales_total = sum(s.total for s in sales_today)
    sales_profit = sum(s.total_profit for s in sales_today) if PERM_PROFIT_VIEW in perm_codes else None

    # Wallets today
    wallet_txs = (
        session.query(WalletTransaction)
        .filter(WalletTransaction.created_at >= start_dt, WalletTransaction.created_at <= end_dt)
        .all()
    )
    wallet_count = len(wallet_txs)
    wallet_profit = sum(t.profit for t in wallet_txs) if PERM_PROFIT_VIEW in perm_codes else None

    # Cash accounts
    drawer = session.query(CashAccount).filter_by(type="drawer").first()
    safe = session.query(CashAccount).filter_by(type="safe").first()
    drawer_balance = drawer.balance if drawer else 0
    safe_balance = safe.balance if safe else 0

    # Total wallets balance
    wallets = session.query(Wallet).filter_by(is_active=True).all()
    total_wallets_balance = sum(w.balance for w in wallets)

    # Active Shift
    active_shift = session.query(Shift).filter_by(status="open").order_by(Shift.opened_at.desc()).first()

    # Low Stock Products
    products = session.query(Product).filter_by(is_active=True).all()
    low_stock_items = []
    for p in products:
        qty = p.current_quantity()
        if qty <= p.min_stock:
            low_stock_items.append({
                "id": p.id,
                "name": p.name,
                "type": p.type,
                "qty": qty,
                "min_stock": p.min_stock,
            })

    # Customer Receivables
    customers = session.query(Customer).filter(Customer.balance > 0).all()
    total_receivables = sum(c.balance for c in customers)

    # Recent 5 sales
    recent_sales = []
    for s in sales_today[:5]:
        recent_sales.append({
            "id": s.id,
            "invoice_no": s.invoice_no,
            "customer_name": s.customer.name if s.customer else "عميل نقدي",
            "total": s.total,
            "time": clock.fmt_local(s.created_at, "%I:%M %p"),
        })

    return {
        "today_str": today.strftime("%Y-%m-%d"),
        "sales_count": sales_count,
        "sales_total": sales_total,
        "sales_profit": sales_profit,
        "wallet_count": wallet_count,
        "wallet_profit": wallet_profit,
        "drawer_balance": drawer_balance,
        "safe_balance": safe_balance,
        "total_wallets_balance": total_wallets_balance,
        "active_shift": {
            "id": active_shift.id if active_shift else None,
            "user_name": active_shift.user.full_name if (active_shift and active_shift.user) else "—",
            "opened_at": active_shift.opened_at.strftime("%I:%M %p") if active_shift else None,
            "is_open": active_shift is not None,
        },
        "low_stock_count": len(low_stock_items),
        "low_stock_items": low_stock_items[:10],
        "total_receivables": total_receivables,
        "recent_sales": recent_sales,
    }


# ── 8. Excel Exporter Helper ──────────────────────────────────────────────────

def export_report_to_csv(report_data: dict[str, Any], filepath: str) -> str:
    """Export report tabular rows to a UTF-8 with BOM CSV (opens seamlessly in Excel)."""
    import csv
    from pathlib import Path

    p = Path(filepath)
    p.parent.mkdir(parents=True, exist_ok=True)

    rows = report_data.get("rows") or []
    if not rows:
        # Debts report special case
        if "customers" in report_data:
            rows = report_data["customers"]

    if not rows:
        with open(p, "w", encoding="utf-8-sig", newline="") as f:
            f.write("لا توجد بيانات مطابقة للفترة المحددة\n")
        return str(p)

    headers = list(rows[0].keys())

    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for r in rows:
            # Format piasters to EGP for financial readability
            clean_row = {}
            for k, v in r.items():
                if isinstance(v, int) and ("price" in k or "total" in k or "profit" in k or "cost" in k or "balance" in k or "paid" in k or "subtotal" in k or "amount" in k or "remaining" in k):
                    clean_row[k] = f"{piasters_to_input(v)}"
                else:
                    clean_row[k] = v
            writer.writerow(clean_row)

    return str(p)
