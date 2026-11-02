"""ORM models: Sale, SaleItem, SalePayment, SaleReturn, SaleReturnItem."""
from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Sale(Base):
    """Sales invoice header."""
    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    shift_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("shifts.id"), nullable=True, index=True
    )
    subtotal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)    # piasters
    discount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)    # piasters
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)       # piasters (subtotal - discount)
    paid: Mapped[int] = mapped_column(Integer, nullable=False, default=0)        # piasters
    remaining: Mapped[int] = mapped_column(Integer, nullable=False, default=0)   # piasters (total - paid)
    # held | posted | void
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="held", index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, nullable=False, index=True
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        nullable=False,
    )

    customer: Mapped[Customer] = relationship("Customer", back_populates="sales")
    user: Mapped[User] = relationship("User")
    shift: Mapped[Optional[Shift]] = relationship("Shift", back_populates="sales")

    items: Mapped[list[SaleItem]] = relationship(
        "SaleItem", back_populates="sale", cascade="all, delete-orphan"
    )
    payments: Mapped[list[SalePayment]] = relationship(
        "SalePayment", back_populates="sale", cascade="all, delete-orphan"
    )
    returns: Mapped[list[SaleReturn]] = relationship(
        "SaleReturn", back_populates="sale"
    )

    @property
    def total_cost(self) -> int:
        return sum(item.quantity * item.unit_cost for item in self.items)

    @property
    def total_profit(self) -> int:
        return self.total - self.total_cost

    def __repr__(self) -> str:
        return f"<Sale invoice_no={self.invoice_no} total={self.total} status={self.status}>"


class SaleItem(Base):
    """Line item in a sale invoice."""
    __tablename__ = "sale_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sale_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sales.id"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id"), nullable=False, index=True
    )
    device_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("devices.id"), nullable=True, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[int] = mapped_column(Integer, nullable=False)   # piasters
    unit_cost: Mapped[int] = mapped_column(Integer, nullable=False)    # piasters (snapshot at sale time)
    discount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # piasters
    line_total: Mapped[int] = mapped_column(Integer, nullable=False)  # (unit_price * qty) - discount
    warranty_end_date: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime, nullable=True, index=True
    )

    sale: Mapped[Sale] = relationship("Sale", back_populates="items")
    product: Mapped[Product] = relationship("Product")
    device: Mapped[Optional[Device]] = relationship("Device")

    @property
    def profit(self) -> int:
        return self.line_total - (self.quantity * self.unit_cost)

    def __repr__(self) -> str:
        return f"<SaleItem product_id={self.product_id} qty={self.quantity} total={self.line_total}>"


class SalePayment(Base):
    """Payment methods breakdown for a sale (supports split payments)."""
    __tablename__ = "sale_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sale_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sales.id"), nullable=False, index=True
    )
    # cash | vodafone | orange | etisalat | instapay | credit
    method: Mapped[str] = mapped_column(String(30), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # piasters
    wallet_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    sale: Mapped[Sale] = relationship("Sale", back_populates="payments")

    def __repr__(self) -> str:
        return f"<SalePayment method={self.method} amount={self.amount}>"


class SaleReturn(Base):
    """Return / refund against a posted sale invoice."""
    __tablename__ = "sale_returns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sale_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sales.id"), nullable=False, index=True
    )
    return_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    refund_amount: Mapped[int] = mapped_column(Integer, nullable=False)  # piasters
    refund_method: Mapped[str] = mapped_column(String(30), nullable=False, default="cash")
    restock: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, nullable=False, index=True
    )

    sale: Mapped[Sale] = relationship("Sale", back_populates="returns")
    items: Mapped[list[SaleReturnItem]] = relationship(
        "SaleReturnItem", back_populates="sale_return", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<SaleReturn return_no={self.return_no} refund={self.refund_amount}>"


class SaleReturnItem(Base):
    """Line item in a sale return."""
    __tablename__ = "sale_return_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    return_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sale_returns.id"), nullable=False, index=True
    )
    sale_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sale_items.id"), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    sale_return: Mapped[SaleReturn] = relationship("SaleReturn", back_populates="items")
    sale_item: Mapped[SaleItem] = relationship("SaleItem")


from app.models.customer import Customer  # noqa: E402, F401
from app.models.user import User  # noqa: E402, F401
from app.models.shift import Shift  # noqa: E402, F401
from app.models.product import Product  # noqa: E402, F401
from app.models.stock import Device  # noqa: E402, F401

