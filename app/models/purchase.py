"""ORM models: Supplier, Purchase, PurchaseItem, SupplierPayment, UsedDevicePurchase."""
from __future__ import annotations

import datetime
from app.core.clock import utcnow
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Supplier(Base):
    """Product and accessory suppliers."""
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    # Balance in piasters: positive = we owe the supplier, 0 = settled
    balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
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

    purchases: Mapped[list[Purchase]] = relationship("Purchase", back_populates="supplier")
    payments: Mapped[list[SupplierPayment]] = relationship("SupplierPayment", back_populates="supplier")

    def __repr__(self) -> str:
        return f"<Supplier {self.name} balance={self.balance}>"


class Purchase(Base):
    """Purchase invoice from a supplier."""
    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_number: Mapped[str] = mapped_column(String(60), nullable=False, unique=True, index=True)
    supplier_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("suppliers.id"), nullable=False, index=True
    )
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)       # in piasters
    paid: Mapped[int] = mapped_column(Integer, nullable=False, default=0)        # in piasters
    balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)     # total - paid
    # draft | posted | void
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="posted", index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )

    supplier: Mapped[Supplier] = relationship("Supplier", back_populates="purchases")
    user: Mapped[User] = relationship("User")
    items: Mapped[list[PurchaseItem]] = relationship(
        "PurchaseItem", back_populates="purchase", cascade="all, delete-orphan"
    )
    payments: Mapped[list[SupplierPayment]] = relationship("SupplierPayment", back_populates="purchase")

    def __repr__(self) -> str:
        return f"<Purchase {self.invoice_number} total={self.total} status={self.status}>"


class PurchaseItem(Base):
    """A single line item in a purchase invoice."""
    __tablename__ = "purchase_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    purchase_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("purchases.id"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id"), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_cost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)   # in piasters
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)       # in piasters

    purchase: Mapped[Purchase] = relationship("Purchase", back_populates="items")
    product: Mapped[Product] = relationship("Product")

    def __repr__(self) -> str:
        return f"<PurchaseItem purchase_id={self.purchase_id} product_id={self.product_id} qty={self.quantity}>"


class SupplierPayment(Base):
    """Payment voucher made to a supplier."""
    __tablename__ = "supplier_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    supplier_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("suppliers.id"), nullable=False, index=True
    )
    purchase_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("purchases.id"), nullable=True, index=True
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)                 # in piasters
    # cash | wallet | bank
    method: Mapped[str] = mapped_column(String(30), nullable=False, default="cash")
    account_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("cash_accounts.id"), nullable=True
    )
    cash_transaction_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("cash_transactions.id"), nullable=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    supplier: Mapped[Supplier] = relationship("Supplier", back_populates="payments")
    purchase: Mapped[Optional[Purchase]] = relationship("Purchase", back_populates="payments")
    user: Mapped[User] = relationship("User")

    def __repr__(self) -> str:
        return f"<SupplierPayment supplier_id={self.supplier_id} amount={self.amount}>"


class UsedDevicePurchase(Base):
    """Legal record of buying a used phone directly from an individual seller."""
    __tablename__ = "used_device_purchases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    seller_name: Mapped[str] = mapped_column(String(150), nullable=False)
    seller_national_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    seller_phone: Mapped[str] = mapped_column(String(30), nullable=False)
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("devices.id"), unique=True, nullable=False, index=True
    )
    price: Mapped[int] = mapped_column(Integer, nullable=False)                  # in piasters
    condition_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    declaration_printed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cash_transaction_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("cash_transactions.id"), nullable=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    device: Mapped[Device] = relationship("Device")
    user: Mapped[User] = relationship("User")

    def __repr__(self) -> str:
        return f"<UsedDevicePurchase seller={self.seller_name} device_id={self.device_id} price={self.price}>"


# Circular imports avoided
from app.models.user import User  # noqa: E402, F401
from app.models.product import Product  # noqa: E402, F401
from app.models.stock import Device  # noqa: E402, F401

