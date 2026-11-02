"""ORM models: Category, Brand, Product."""
from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TimestampMixin:
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        nullable=False,
    )


class Category(TimestampMixin, Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("categories.id"), nullable=True, index=True
    )
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    parent: Mapped[Optional[Category]] = relationship("Category", remote_side="Category.id")
    products: Mapped[list[Product]] = relationship("Product", back_populates="category")

    def __repr__(self) -> str:
        return f"<Category {self.name}>"


class Brand(TimestampMixin, Base):
    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    products: Mapped[list[Product]] = relationship("Product", back_populates="brand")

    def __repr__(self) -> str:
        return f"<Brand {self.name}>"


class Product(TimestampMixin, Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    barcode: Mapped[Optional[str]] = mapped_column(String(100), unique=True, nullable=True, index=True)
    category_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("categories.id"), nullable=True, index=True
    )
    brand_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("brands.id"), nullable=True, index=True
    )
    # phone | accessory | card
    type: Mapped[str] = mapped_column(String(20), nullable=False, default="accessory")
    cost_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)   # piasters
    sale_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)   # piasters
    min_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)    # piasters
    min_stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    track_imei: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    warranty_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    category: Mapped[Optional[Category]] = relationship("Category", back_populates="products")
    brand: Mapped[Optional[Brand]] = relationship("Brand", back_populates="products")
    stock: Mapped[Optional[Stock]] = relationship("Stock", back_populates="product", uselist=False)
    devices: Mapped[list[Device]] = relationship("Device", back_populates="product")
    movements: Mapped[list[StockMovement]] = relationship("StockMovement", back_populates="product")

    def current_quantity(self) -> int:
        """Return available quantity (stock row for accessories, in_stock devices for phones)."""
        if self.track_imei:
            return sum(1 for d in self.devices if d.status == "in_stock")
        return self.stock.quantity if self.stock else 0

    def __repr__(self) -> str:
        return f"<Product {self.name}>"


# Import here to avoid circular references — Stock and Device defined in stock.py
from app.models.stock import Stock, Device, StockMovement  # noqa: E402, F401

