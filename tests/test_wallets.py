"""Unit tests for Phase 5: Wallets, operations matrix, commission rules, limits, and audits."""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.core.money import egp_to_piasters, piasters_to_egp
from app.core.permissions import ROLE_MANAGER, ROLE_WALLET_EMPLOYEE, PermissionDenied
from app.core.security import hash_password
from app.models.accounting import CashAccount
from app.models.user import Role, User
from app.models.wallet import Wallet, CommissionRule
from app.services import shift_service, wallet_service


@pytest.fixture
def manager_user(db_session: Session) -> User:
    role = db_session.query(Role).filter_by(name=ROLE_MANAGER).first()
    u = User(
        username="mgr_wallets",
        password_hash=hash_password("123"),
        full_name="Wallet Mgr",
        role_id=role.id,
        is_active=True,
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def wallet_emp(db_session: Session) -> User:
    role = db_session.query(Role).filter_by(name=ROLE_WALLET_EMPLOYEE).first()
    u = User(
        username="emp_wallets",
        password_hash=hash_password("123"),
        full_name="Wallet Specialist",
        role_id=role.id,
        is_active=True,
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def active_shift(db_session: Session, wallet_emp: User):
    shift = shift_service.open_shift(
        db_session, wallet_emp, opening_cash=egp_to_piasters(10000)
    )
    db_session.commit()
    return shift


@pytest.fixture
def drawer_account(db_session: Session) -> CashAccount:
    drawer = db_session.query(CashAccount).filter(CashAccount.type == "drawer").first()
    if not drawer:
        drawer = CashAccount(name="الدرج الرئيسي", type="drawer", balance=egp_to_piasters(20000))
        db_session.add(drawer)
        db_session.commit()
    else:
        drawer.balance = egp_to_piasters(20000)
        db_session.commit()
    return drawer


@pytest.fixture
def test_wallet(db_session: Session, manager_user: User) -> Wallet:
    w = wallet_service.create_wallet(
        db_session,
        manager_user,
        network="vodafone",
        phone_number="01012345678",
        label="Vodafone Cash Line 1",
        initial_balance=egp_to_piasters(15000),
        daily_limit=egp_to_piasters(30000),
        monthly_limit=egp_to_piasters(100000),
    )
    db_session.commit()
    return w


class TestCommissionRules:
    """Test data-driven commission rules and tiered lookup by amount range."""

    def test_commission_tiered_lookup(self, db_session: Session, manager_user: User):
        # Tier 1: 1..500 EGP -> 5 EGP fixed
        wallet_service.create_commission_rule(
            db_session,
            manager_user,
            network="vodafone",
            op_type="cash_in",
            min_amount=egp_to_piasters(1),
            max_amount=egp_to_piasters(500),
            fixed_fee=egp_to_piasters(5),
            percent_bp=0,
            network_fee=egp_to_piasters(1),
        )
        # Tier 2: 501..2000 EGP -> 10 EGP fixed + 0.5% (50 bp)
        wallet_service.create_commission_rule(
            db_session,
            manager_user,
            network="vodafone",
            op_type="cash_in",
            min_amount=egp_to_piasters(501),
            max_amount=egp_to_piasters(2000),
            fixed_fee=egp_to_piasters(10),
            percent_bp=50,  # 0.5%
            network_fee=egp_to_piasters(2),
        )
        db_session.commit()

        # Test amount in Tier 1: 300 EGP
        comm1, net1 = wallet_service.compute_commission(
            db_session, "vodafone", "cash_in", egp_to_piasters(300)
        )
        assert comm1 == egp_to_piasters(5)
        assert net1 == egp_to_piasters(1)

        # Test amount in Tier 2: 1000 EGP -> 10 EGP + 0.5% of 1000 (5 EGP) = 15 EGP
        comm2, net2 = wallet_service.compute_commission(
            db_session, "vodafone", "cash_in", egp_to_piasters(1000)
        )
        assert comm2 == egp_to_piasters(15)
        assert net2 == egp_to_piasters(2)


class TestOperationsMatrix:
    """Verify AGENTS.md §6 matrix for all 6 op types."""

    @pytest.mark.parametrize(
        "op_type, amount_egp, commission_egp, net_fee_egp, cost_price_egp, exp_cash_effect, exp_wallet_effect, exp_profit",
        [
            ("cash_in", 1000, 15, 2, None, +1015, -1000, 13),       # +(amount + comm), -amount, comm - fee
            ("cash_out", 1000, 10, 0, None, -1000, +1000, 10),      # -amount, +amount, comm
            ("recharge", 100, 10, 0, 95, +100, -95, 5),             # +sale_price, -cost_price, sale_price - cost_price
            ("bill", 500, 10, 1, None, +510, -500, 9),              # +(amount + comm), -amount, comm - fee
            ("fund", 2000, 0, 0, None, -2000, +2000, 0),             # -amount, +amount, 0
            ("withdraw", 3000, 0, 0, None, +3000, -3000, 0),         # +amount, -amount, 0
        ],
    )
    def test_op_effects_and_profit(
        self,
        db_session: Session,
        manager_user: User,
        active_shift,
        drawer_account: CashAccount,
        test_wallet: Wallet,
        op_type,
        amount_egp,
        commission_egp,
        net_fee_egp,
        cost_price_egp,
        exp_cash_effect,
        exp_wallet_effect,
        exp_profit,
    ):
        # Configure rule for this operation
        wallet_service.create_commission_rule(
            db_session,
            manager_user,
            network=test_wallet.network,
            op_type=op_type,
            min_amount=1,
            max_amount=0,  # unlimited
            fixed_fee=egp_to_piasters(commission_egp),
            percent_bp=0,
            network_fee=egp_to_piasters(net_fee_egp),
        )
        db_session.commit()

        drawer_before = drawer_account.balance
        wallet_before = test_wallet.balance

        tx = wallet_service.execute_wallet_transaction(
            session=db_session,
            user=manager_user,
            wallet_id=test_wallet.id,
            op_type=op_type,
            amount=egp_to_piasters(amount_egp),
            cost_price=egp_to_piasters(cost_price_egp) if cost_price_egp else None,
            customer_phone="01099887766",
        )
        db_session.commit()

        # Verify transaction fields
        assert tx.cash_effect == egp_to_piasters(exp_cash_effect)
        assert tx.wallet_effect == egp_to_piasters(exp_wallet_effect)
        assert tx.profit == egp_to_piasters(exp_profit)

        # Verify balances updated accurately
        db_session.refresh(drawer_account)
        db_session.refresh(test_wallet)

        assert drawer_account.balance == drawer_before + egp_to_piasters(exp_cash_effect)
        assert test_wallet.balance == wallet_before + egp_to_piasters(exp_wallet_effect)


class TestLimitsAndBalanceValidation:
    """Test balance and limit enforcement."""

    def test_insufficient_wallet_balance_blocked(
        self,
        db_session: Session,
        wallet_emp: User,
        active_shift,
        drawer_account: CashAccount,
        test_wallet: Wallet,
    ):
        # Wallet balance is 15,000 EGP. Trying to cash_in 20,000 EGP must be blocked.
        with pytest.raises(wallet_service.InsufficientWalletBalance):
            wallet_service.execute_wallet_transaction(
                db_session,
                wallet_emp,
                wallet_id=test_wallet.id,
                op_type="cash_in",
                amount=egp_to_piasters(20000),
            )

    def test_insufficient_drawer_cash_blocked(
        self,
        db_session: Session,
        wallet_emp: User,
        active_shift,
        drawer_account: CashAccount,
        test_wallet: Wallet,
    ):
        # Set drawer balance to 500 EGP
        drawer_account.balance = egp_to_piasters(500)
        db_session.commit()

        # cash_out requires giving 1000 EGP cash to customer -> blocked
        with pytest.raises(wallet_service.InsufficientDrawerCash):
            wallet_service.execute_wallet_transaction(
                db_session,
                wallet_emp,
                wallet_id=test_wallet.id,
                op_type="cash_out",
                amount=egp_to_piasters(1000),
            )

    def test_daily_limit_exceeded_blocked(
        self,
        db_session: Session,
        wallet_emp: User,
        active_shift,
        drawer_account: CashAccount,
        test_wallet: Wallet,
    ):
        # Daily limit is 30,000 EGP. Try doing 35,000 EGP -> blocked
        with pytest.raises(wallet_service.DailyLimitExceeded):
            wallet_service.execute_wallet_transaction(
                db_session,
                wallet_emp,
                wallet_id=test_wallet.id,
                op_type="cash_out",
                amount=egp_to_piasters(35000),
            )


class TestWalletAudit:
    """Test physical wallet end-of-day audit."""

    def test_audit_diff_recorded(
        self,
        db_session: Session,
        manager_user: User,
        test_wallet: Wallet,
    ):
        # System balance: 15,000 EGP
        # Actual balance found: 14,800 EGP (shortage of 200 EGP)
        audit = wallet_service.audit_wallet(
            db_session,
            manager_user,
            wallet_id=test_wallet.id,
            actual_balance=egp_to_piasters(14800),
            note="End of day count: 200 EGP shortage",
        )
        db_session.commit()

        assert audit.id is not None
        assert audit.system_balance == egp_to_piasters(15000)
        assert audit.actual_balance == egp_to_piasters(14800)
        assert audit.diff == -egp_to_piasters(200)

    def test_non_manager_audit_forbidden(
        self,
        db_session: Session,
        wallet_emp: User,
        test_wallet: Wallet,
    ):
        with pytest.raises(PermissionDenied):
            wallet_service.audit_wallet(
                db_session,
                wallet_emp,
                wallet_id=test_wallet.id,
                actual_balance=egp_to_piasters(15000),
            )
