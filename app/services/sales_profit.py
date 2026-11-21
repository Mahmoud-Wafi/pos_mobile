"""Sales profit net of returns — the single definition used by every report (D-022).

* A sale's profit is booked in the period the invoice was created (posted AND voided invoices, so
  history never changes when an invoice is voided later).
* A return reduces profit in the period the RETURN happened: revenue goes back by the refunded amount;
  the cost goes back too only if the goods were restocked (a non-restocked return keeps its cost as a loss).
* A void is a full return, so a voided sale nets to zero over time without double counting.
"""
from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.sale import Sale, SaleReturn


def net_sales_profit(session: Session, start_dt: datetime.datetime, end_dt: datetime.datetime) -> dict[str, Any]:
    sales = (session.query(Sale)
             .filter(Sale.created_at >= start_dt, Sale.created_at <= end_dt, Sale.status.in_(("posted", "void")))
             .all())
    returns = (session.query(SaleReturn)
               .filter(SaleReturn.created_at >= start_dt, SaleReturn.created_at <= end_dt)
               .all())

    gross_revenue = sum(s.total for s in sales)
    gross_profit = sum(s.total_profit for s in sales)
    returns_revenue = sum(r.refund_amount for r in returns)
    cost_recovered = 0
    for r in returns:
        if r.restock:
            cost_recovered += sum(i.quantity * i.sale_item.unit_cost for i in r.items)
    return {
        "sales": [s for s in sales if s.status == "posted"],
        "gross_revenue": gross_revenue,
        "gross_profit": gross_profit,
        "returns_count": len(returns),
        "returns_revenue": returns_revenue,
        "returns_cost_recovered": cost_recovered,
        "net_revenue": gross_revenue - returns_revenue,
        "net_profit": gross_profit - returns_revenue + cost_recovered,
    }
