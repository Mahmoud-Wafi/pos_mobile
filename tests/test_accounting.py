"""Unit tests for Phase 6: Cash & Accounting, expenses, transfers, owner draws,
shift reconciliation, and daily close report.
"""
from __future__ import annotations

import datetime
from app.core import clock
import pytest
from sqlalchemy.orm import Session

from app.core.money import egp_to_piasters, piasters_to_egp
from app.core.permissions import ROLE_CASHIER, ROLE_MANAGER, PermissionDenied
from app.core.security import hash_password
from app.models.accounting import CashAccount, Expense, ExpenseCategory, OwnerDraw
from app.models.product import Product
from app.models.sale import Sale
from app.models.shift import Shift
from app.models.user import Role, User
from app.services import accounting_service, shift_service


@pytest.fixture
def manager_user(db_session: Session) -> User:
    role = db_session.query(Role).filter_by(name=ROLE_MANAGER).first()
    u = User(
        username="mgr_accounting",
        password_hash=hash_password("123"),
        full_name="Accounting Mgr",
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
        username="csh_accounting",
        password_hash=hash_password("123"),
        full_name="Accounting Cashier",
        role_id=role.id,
        is_active=True,
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def test_accounts(db_session: Session, manager_user: User) -> tuple[CashAccount, CashAccount]:
    drawer = accounting_service.create_account(
        db_session, manager_user, name="درج المحاسبة التجريبي", account_type="drawer", initial_balance=egp_to_piasters(10000)
    )
    safe = accounting_service.create_account(
        db_session, manager_user, name="خزنة المحاسبة التجريبية", account_type="safe", initial_balance=egp_to_piasters(50000)
    )
    db_session.commit()
    return drawer, safe


@pytest.fixture
def rent_category(db_session: Session, manager_user: User) -> ExpenseCategory:
    cat = accounting_service.create_expense_category(db_session, manager_user, "إيجار الفرع التجريبي")
    db_session.commit()
    return cat


class TestCashDrawerIntegrity:
    """Acceptance criterion: drawer balance equals sum of its transactions at all times."""

    def test_drawer_balance_equals_sum_of_transactions(
        self,
        db_session: Session,
        manager_user: User,
        test_accounts: tuple[CashAccount, CashAccount],
        rent_category: ExpenseCategory,
    ):
        drawer, safe = test_accounts

        # Initial check
        assert accounting_service.verify_drawer_balance_integrity(db_session, drawer.id)

        # 1. Expense: pay 1,000 EGP rent
        accounting_service.add_expense(
            db_session, manager_user,
            category_id=rent_category.id,
            amount=egp_to_piasters(1000),
            account_id=drawer.id,
            note="Month rent part",
        )
        db_session.commit()
        assert accounting_service.verify_drawer_balance_integrity(db_session, drawer.id)

        # 2. Transfer: Move 3,000 EGP from drawer to safe
        accounting_service.transfer(
            db_session, manager_user,
            from_account_id=drawer.id,
            to_account_id=safe.id,
            amount=egp_to_piasters(3000),
            note="Evening drawer empty",
        )
        db_session.commit()
        assert accounting_service.verify_drawer_balance_integrity(db_session, drawer.id)
        assert accounting_service.verify_drawer_balance_integrity(db_session, safe.id)

        # 3. Transfer back: Move 500 EGP from safe to drawer
        accounting_service.transfer(
            db_session, manager_user,
            from_account_id=safe.id,
            to_account_id=drawer.id,
            amount=egp_to_piasters(500),
            note="Change for morning",
        )
        db_session.commit()
        assert accounting_service.verify_drawer_balance_integrity(db_session, drawer.id)
        assert accounting_service.verify_drawer_balance_integrity(db_session, safe.id)

        # Balance check: 10,000 - 1,000 - 3,000 + 500 = 6,500 EGP
        db_session.refresh(drawer)
        assert drawer.balance == egp_to_piasters(6500)


class TestExpensesAndDraws:
    """Test expenses and owner drawings."""

    def test_add_expense_insufficient_funds_raises(
        self,
        db_session: Session,
        manager_user: User,
        test_accounts: tuple[CashAccount, CashAccount],
        rent_category: ExpenseCategory,
    ):
        drawer, _ = test_accounts
        # Drawer has 10,000 EGP. Trying to spend 15,000 EGP raises InsufficientFunds.
        with pytest.raises(accounting_service.InsufficientFunds):
            accounting_service.add_expense(
                db_session, manager_user,
                category_id=rent_category.id,
                amount=egp_to_piasters(15000),
                account_id=drawer.id,
            )

    def test_owner_draw_separate_from_expenses(
        self,
        db_session: Session,
        manager_user: User,
        test_accounts: tuple[CashAccount, CashAccount],
    ):
        _, safe = test_accounts
        initial_safe = safe.balance

        draw = accounting_service.owner_draw(
            db_session, manager_user,
            amount=egp_to_piasters(5000),
            account_id=safe.id,
            note="Owner personal draw",
        )
        db_session.commit()

        db_session.refresh(safe)
        assert safe.balance == initial_safe - egp_to_piasters(5000)
        assert draw.id is not None
        assert draw.amount == egp_to_piasters(5000)

        # Confirm not counted in Expense table
        exp_count = db_session.query(Expense).filter(Expense.amount == egp_to_piasters(5000)).count()
        assert exp_count == 0


class TestShiftReconciliation:
    """Acceptance criterion: shift diff recorded against user."""

    def test_shift_close_records_diff(
        self,
        db_session: Session,
        cashier_user: User,
    ):
        # Open shift with 1,000 EGP
        shift = shift_service.open_shift(
            db_session, cashier_user,
            opening_cash=egp_to_piasters(1000),
        )
        db_session.commit()

        # Close shift with actual 950 EGP (shortage of 50 EGP)
        closed_shift = shift_service.close_shift(
            db_session, cashier_user,
            shift_id=shift.id,
            actual_cash=egp_to_piasters(950),
            notes="Missing 50 EGP change",
        )
        db_session.commit()

        assert closed_shift.status == "closed"
        assert closed_shift.expected_cash == egp_to_piasters(1000)
        assert closed_shift.actual_cash == egp_to_piasters(950)
        assert closed_shift.diff == -egp_to_piasters(50)
        assert closed_shift.user_id == cashier_user.id


class TestDailyCloseReport:
    """Test consolidated daily financial close."""

    def test_daily_close_calculates_net_profit(
        self,
        db_session: Session,
        manager_user: User,
        cashier_user: User,
        test_accounts: tuple[CashAccount, CashAccount],
        rent_category: ExpenseCategory,
    ):
        drawer, safe = test_accounts

        # Add 500 EGP expense
        accounting_service.add_expense(
            db_session, manager_user,
            category_id=rent_category.id,
            amount=egp_to_piasters(500),
            account_id=drawer.id,
        )

        # Shift with 100 EGP overage
        shift = shift_service.open_shift(
            db_session, cashier_user, opening_cash=egp_to_piasters(1000)
        )
        shift_service.close_shift(
            db_session, cashier_user, shift_id=shift.id, actual_cash=egp_to_piasters(1100)
        )
        db_session.commit()

        today = clock.local_today()
        report = accounting_service.daily_close(db_session, manager_user, ref_date=today)

        assert report["date"] == today.strftime("%Y-%m-%d")
        assert report["expenses"] == egp_to_piasters(500)
        assert report["shift_diff"] == egp_to_piasters(100)
        # Net Profit = 0 (sales) + 0 (wallets) - 500 (expenses) + 100 (overage) = -400 EGP
        assert report["net_profit"] == -egp_to_piasters(400)
        assert report["balances"]["total_cash"] > 0

