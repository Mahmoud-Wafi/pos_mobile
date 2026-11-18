"""ORM model: WarrantyClaim — a customer's warranty case against a sold item."""
from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import utcnow
from app.core.database import Base

CLAIM_STATUSES = ("open", "in_repair", "resolved", "rejected")


class WarrantyClaim(Base):
    __tablename__ = "warranty_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sale_item_id: Mapped[int] = mapped_column(Integer, ForeignKey("sale_items.id"), nullable=False, index=True)
    device_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("devices.id"), nullable=True)
    issue: Mapped[str] = mapped_column(Text, nullable=False)
    resolution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", index=True)
    in_warranty: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # when the claim was opened
    opened_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    opened_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    closed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    sale_item = relationship("SaleItem")
    device = relationship("Device")
