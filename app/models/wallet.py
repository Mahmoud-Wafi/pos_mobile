"""ORM models: Wallet, CommissionRule, WalletTransaction, WalletAudit."""
from __future__ import annotations

import datetime
from app.core.clock import utcnow
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Wallet(Base):
    """Electronic wallet or mobile cash line (Vodafone, Orange, Etisalat, WE, InstaPay)."""
    __tablename__ = "wallets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # vodafone | orange | etisalat | we | instapay
    network: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    phone_number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True, index=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)        # in piasters
    daily_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)    # in piasters (0 = unlimited)
    monthly_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # in piasters (0 = unlimited)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    transactions: Mapped[list[WalletTransaction]] = relationship(
        "WalletTransaction", back_populates="wallet"
    )
    audits: Mapped[list[WalletAudit]] = relationship("WalletAudit", back_populates="wallet")

    def __repr__(self) -> str:
        return f"<Wallet {self.label} ({self.network}) balance={self.balance}>"


class CommissionRule(Base):
    """Configurable commission rules for wallet transactions."""
    __tablename__ = "commission_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    network: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    # cash_in | cash_out | recharge | bill | fund | withdraw
    op_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    min_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)     # in piasters
    max_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)     # in piasters
    fixed_fee: Mapped[int] = mapped_column(Integer, nullable=False, default=0)      # in piasters
    percent_bp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)     # basis points (100 bp = 1%)
    network_fee: Mapped[int] = mapped_column(Integer, nullable=False, default=0)    # in piasters (cut taken by telco)
    # customer | network
    paid_by: Mapped[str] = mapped_column(String(20), nullable=False, default="customer")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<CommissionRule {self.network} {self.op_type} range={self.min_amount}..{self.max_amount}>"


class WalletTransaction(Base):
    """Immutable ledger of every electronic wallet transaction."""
    __tablename__ = "wallet_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wallet_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wallets.id"), nullable=False, index=True
    )
    # cash_in | cash_out | recharge | bill | fund | withdraw
    op_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    customer_phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)                    # in piasters
    commission: Mapped[int] = mapped_column(Integer, nullable=False, default=0)     # in piasters
    network_fee: Mapped[int] = mapped_column(Integer, nullable=False, default=0)    # in piasters
    profit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)         # in piasters
    cash_effect: Mapped[int] = mapped_column(Integer, nullable=False, default=0)    # signed effect on shop cash drawer
    wallet_effect: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # signed effect on wallet balance
    reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)   # telco SMS/ref code
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    shift_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("shifts.id"), nullable=True, index=True
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )

    wallet: Mapped[Wallet] = relationship("Wallet", back_populates="transactions")
    user: Mapped[User] = relationship("User")
    shift: Mapped[Optional[Shift]] = relationship("Shift")

    def __repr__(self) -> str:
        return f"<WalletTransaction id={self.id} op={self.op_type} amount={self.amount} profit={self.profit}>"


class WalletAudit(Base):
    """End-of-day or shift audit comparing recorded vs actual physical wallet balance."""
    __tablename__ = "wallet_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wallet_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wallets.id"), nullable=False, index=True
    )
    system_balance: Mapped[int] = mapped_column(Integer, nullable=False)            # in piasters
    actual_balance: Mapped[int] = mapped_column(Integer, nullable=False)            # in piasters
    diff: Mapped[int] = mapped_column(Integer, nullable=False)                      # actual - system
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    wallet: Mapped[Wallet] = relationship("Wallet", back_populates="audits")
    user: Mapped[User] = relationship("User")

    def __repr__(self) -> str:
        return f"<WalletAudit wallet_id={self.wallet_id} diff={self.diff}>"


# Prevent circular import issues
from app.models.user import User  # noqa: E402, F401
from app.models.shift import Shift  # noqa: E402, F401

