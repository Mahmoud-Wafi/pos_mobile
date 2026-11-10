"""ORM models: Stock, Device, StockMovement."""
from __future__ import annotations

import datetime
from app.core.clock import utcnow
from typing import Optional

from sqlalchemy import (
    DateTime, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Stock(Base):
    """Non-IMEI product stock level. For IMEI items quantity = count of in_stock devices."""
    __tablename__ = "stock"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id"), unique=True, nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    product: Mapped[Product] = relationship("Product", back_populates="stock")

    def __repr__(self) -> str:
        return f"<Stock product_id={self.product_id} qty={self.quantity}>"


class Device(Base):
    """A single physical phone tracked by IMEI."""
    __tablename__ = "devices"
    __table_args__ = (
        UniqueConstraint("imei1"),
        UniqueConstraint("imei2"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id"), nullable=False, index=True
    )
    imei1: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    imei2: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, unique=True, index=True)
    condition: Mapped[str] = mapped_column(String(10), nullable=False, default="new")  # new | used
    purchase_cost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)   # piasters
    extra_cost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)       # piasters
    # in_stock | sold | returned | damaged
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="in_stock", index=True)
    purchase_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    sale_item_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    product: Mapped[Product] = relationship("Product", back_populates="devices")

    @property
    def total_cost(self) -> int:
        return self.purchase_cost + self.extra_cost

    def __repr__(self) -> str:
        return f"<Device imei1={self.imei1} status={self.status}>"


class StockMovement(Base):
    """Immutable ledger of every stock change."""
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id"), nullable=False, index=True
    )
    device_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("devices.id"), nullable=True, index=True
    )
    # purchase|sale|return_in|return_out|adjust|used_purchase
    type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)   # signed (+/-)
    ref_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ref_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )

    product: Mapped[Product] = relationship("Product", back_populates="movements")

    def __repr__(self) -> str:
        return f"<StockMovement {self.type} qty={self.quantity} product_id={self.product_id}>"


# Resolve forward references
from app.models.product import Product  # noqa: E402, F401

