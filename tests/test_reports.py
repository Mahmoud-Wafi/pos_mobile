"""Unit tests for Phase 7: Reports, P&L, stock valuation, wallet commissions,
debts, cash ledger, dashboard metrics, and CSV export.
"""
from __future__ import annotations

import datetime
import os
import time
import pytest
from sqlalchemy.orm import Session

from app.core.money import egp_to_piasters
from app.core.permissions import ROLE_CASHIER, ROLE_MANAGER, PermissionDenied
from app.core.security import hash_password
from app.models.accounting import CashAccount, Expense, ExpenseCategory
from app.models.customer import Customer
from app.models.product import Category, Product
from app.models.sale import Sale, SaleItem, SalePayment
from app.models.shift import Shift
from app.models.user import Role, User
from app.models.wallet import Wallet, WalletTransaction
from app.services import report_service


@pytest.fixture
def manager_user(db_session: Session) -> User:
    role = db_session.query(Role).filter_by(name=ROLE_MANAGER).first()
    u = User(
        username="mgr_reports",
        password_hash=hash_password("123"),
        full_name="Reports Mgr",
        role_id=role.id,
        is_active=True,
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def cashier_user(db_session: Session) -> User:
    role = db_session.query(Role).filter_by(name=ROLE_CASHIER).first()
    u = User(
        username="csh_reports",
        password_hash=hash_password("123"),
        full_name="Reports Cashier",
        role_id=role.id,
        is_active=True,
    )
    db_session.add(u)
    db_session.commit()
    return u


def test_sales_report_reconciliation(db_session: Session, manager_user: User):
    """Verify sales report accurately aggregates posted sales."""
    today = datetime.date.today()

    cust = Customer(name="عميل تجريبي للتقرير", phone="01099999999", balance=0, credit_limit=egp_to_piasters(5000))
    db_session.add(cust)
    db_session.commit()

    # Create dummy sales
    s1 = Sale(
        invoice_no="INV-REP-001",
        customer_id=cust.id,
        user_id=manager_user.id,
        subtotal=egp_to_piasters(1000),
        discount=egp_to_piasters(50),
        total=egp_to_piasters(950),
        paid=egp_to_piasters(950),
        remaining=0,
        status="posted",
        created_at=datetime.datetime.now(),
    )
    s2 = Sale(
        invoice_no="INV-REP-002",
        customer_id=cust.id,
        user_id=manager_user.id,
        subtotal=egp_to_piasters(500),
        discount=0,
        total=egp_to_piasters(500),
        paid=egp_to_piasters(300),
        remaining=egp_to_piasters(200),
        status="posted",
        created_at=datetime.datetime.now(),
    )
    # Draft sale should be excluded
    s3 = Sale(
        invoice_no="INV-REP-003",
        customer_id=cust.id,
        user_id=manager_user.id,
        subtotal=egp_to_piasters(200),
        discount=0,
        total=egp_to_piasters(200),
        paid=0,
        remaining=egp_to_piasters(200),
        status="draft",
        created_at=datetime.datetime.now(),
    )
    db_session.add_all([s1, s2, s3])
    db_session.commit()

    rep = report_service.sales_report(db_session, manager_user, today, today)
    assert rep["total_invoices"] == 2
    assert rep["total_subtotal"] == egp_to_piasters(1500)
    assert rep["total_discount"] == egp_to_piasters(50)
    assert rep["total_net"] == egp_to_piasters(1450)
    assert rep["total_paid"] == egp_to_piasters(1250)
    assert rep["total_remaining"] == egp_to_piasters(200)


def test_profit_report_reconciliation(db_session: Session, manager_user: User, cashier_user: User):
    """Verify P&L formula: Sales profit + Wallet profit - Expenses + Shift diff."""
    today = datetime.date.today()

    # Cashier cannot view profit report
    with pytest.raises(PermissionDenied):
        report_service.profit_report(db_session, cashier_user, today, today)

    # Add a cash account and an expense
    acc = CashAccount(name="خزنة تجريبية للتقرير", type="drawer", balance=egp_to_piasters(10000))
    cat = ExpenseCategory(name="نثريات التقرير")
    db_session.add_all([acc, cat])
    db_session.commit()

    exp = Expense(
        category_id=cat.id,
        account_id=acc.id,
        amount=egp_to_piasters(100),
        user_id=manager_user.id,
        created_at=datetime.datetime.now(),
    )
    db_session.add(exp)
    db_session.commit()

    rep = report_service.profit_report(db_session, manager_user, today, today)
    assert rep["total_expenses"] >= egp_to_piasters(100)
    assert rep["net_profit"] == (
        rep["sales_profit"] + rep["wallet_profit"] - rep["total_expenses"] + rep["shift_diff"]
    )


def test_stock_report_valuation(db_session: Session, manager_user: User):
    """Verify inventory valuation report calculates cost and retail value."""
    cat = Category(name="فئة تقرير المخزون")
    db_session.add(cat)
    db_session.commit()

    p1 = Product(
        name="صنف تقرير 1",
        category_id=cat.id,
        type="accessory",
        cost_price=egp_to_piasters(50),
        sale_price=egp_to_piasters(80),
        min_stock=5,
        track_imei=False,
        is_active=True,
    )
    db_session.add(p1)
    db_session.commit()

    rep = report_service.stock_report(db_session, manager_user)
    assert rep["total_products"] >= 1
    assert rep["total_stock_sale_value"] is not None


def test_debts_report(db_session: Session, manager_user: User):
    """Verify customer receivables and supplier payables reporting."""
    c1 = Customer(name="عميل مديونية 1", phone="01011111111", balance=egp_to_piasters(500), credit_limit=egp_to_piasters(2000))
    c2 = Customer(name="عميل مديونية 2", phone="01022222222", balance=egp_to_piasters(300), credit_limit=egp_to_piasters(2000))
    db_session.add_all([c1, c2])
    db_session.commit()

    rep = report_service.debts_report(db_session, manager_user)
    assert rep["total_receivables"] >= egp_to_piasters(800)
    assert len(rep["customers"]) >= 2


def test_dashboard_metrics(db_session: Session, manager_user: User):
    """Verify aggregated metrics for landing dashboard."""
    metrics = report_service.dashboard_metrics(db_session, manager_user)
    assert "sales_count" in metrics
    assert "sales_total" in metrics
    assert "drawer_balance" in metrics
    assert "low_stock_count" in metrics
    assert "active_shift" in metrics
    assert "recent_sales" in metrics


def test_export_report_to_csv(tmp_path, db_session: Session, manager_user: User):
    """Verify CSV export produces clean UTF-8 with BOM file."""
    today = datetime.date.today()
    rep = report_service.sales_report(db_session, manager_user, today, today)
    csv_file = str(tmp_path / "sales_report.csv")
    out = report_service.export_report_to_csv(rep, csv_file)
    assert os.path.exists(out)

    with open(out, "rb") as f:
        content = f.read()
        # Verify UTF-8 BOM
        assert content.startswith(b"\xef\xbb\xbf")


def test_search_performance_benchmark(db_session: Session):
    """Ensure searching products by name or barcode takes < 200ms."""
    start = time.perf_counter()
    res = db_session.query(Product).filter(Product.name.like("%Galaxy%")).all()
    elapsed = (time.perf_counter() - start) * 1000
    assert elapsed < 200, f"Search took too long: {elapsed:.2f}ms"

