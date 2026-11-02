"""ORM models: Customer, CustomerPayment."""
from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import (
    DateTime, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Customer(Base):
    """Customer account with credit balance (positive = customer owes shop)."""
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, index=True)
    national_id: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, index=True)
    credit_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # in piasters
    balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)       # in piasters (positive = owes shop)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        nullable=False,
    )
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    sales: Mapped[list[Sale]] = relationship("Sale", back_populates="customer")
    payments: Mapped[list[CustomerPayment]] = relationship("CustomerPayment", back_populates="customer")

    def __repr__(self) -> str:
        return f"<Customer {self.name} balance={self.balance}>"


class CustomerPayment(Base):
    """Payment received from a customer towards their debt."""
    __tablename__ = "customer_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id"), nullable=False, index=True
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # in piasters
    method: Mapped[str] = mapped_column(String(30), nullable=False, default="cash")  # cash | bank | instapay | wallet
    shift_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("shifts.id"), nullable=True, index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, nullable=False, index=True
    )

    customer: Mapped[Customer] = relationship("Customer", back_populates="payments")

    def __repr__(self) -> str:
        return f"<CustomerPayment customer_id={self.customer_id} amount={self.amount}>"


from app.models.sale import Sale  # noqa: E402, F401

