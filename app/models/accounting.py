"""ORM models: CashAccount, CashTransaction, Expense, ExpenseCategory, OwnerDraw."""
from __future__ import annotations

import datetime
from app.core.clock import utcnow
from typing import Optional

from sqlalchemy import (
    DateTime, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CashAccount(Base):
    """Cash drawers, safes, bank accounts, and InstaPay accounts."""
    __tablename__ = "cash_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    # drawer | safe | bank | instapay
    type: Mapped[str] = mapped_column(String(30), nullable=False, default="drawer")
    balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # in piasters
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    transactions: Mapped[list[CashTransaction]] = relationship(
        "CashTransaction", back_populates="account"
    )

    def __repr__(self) -> str:
        return f"<CashAccount {self.name} balance={self.balance}>"


class CashTransaction(Base):
    """Immutable ledger of all cash in/out events."""
    __tablename__ = "cash_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cash_accounts.id"), nullable=False, index=True
    )
    # in | out | transfer_in | transfer_out
    type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # in piasters (always positive)
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # sale | expense | debt_collection | etc.
    ref_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)   # sale | return | customer_payment | expense
    ref_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    shift_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("shifts.id"), nullable=True, index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )

    account: Mapped[CashAccount] = relationship("CashAccount", back_populates="transactions")

    def __repr__(self) -> str:
        return f"<CashTransaction {self.type} amount={self.amount} account_id={self.account_id}>"


class ExpenseCategory(Base):
    """Expense categories (e.g. إيجار, كهرباء, بوفيه, مرتبات)."""
    __tablename__ = "expense_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)


class Expense(Base):
    """Shop operating expenses."""
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("expense_categories.id"), nullable=False, index=True
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # piasters
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cash_accounts.id"), nullable=False, index=True
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cash_transaction_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("cash_transactions.id"), nullable=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )


class OwnerDraw(Base):
    """Owner drawings (separate from shop expenses)."""
    __tablename__ = "owner_draws"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # piasters
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cash_accounts.id"), nullable=False, index=True
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )
