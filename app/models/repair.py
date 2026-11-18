"""ORM model: RepairTicket — a customer's device brought in for repair."""
from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow
from app.core.database import Base

REPAIR_STATUSES = ("received", "diagnosing", "waiting_parts", "ready", "delivered", "cancelled")


class RepairTicket(Base):
    __tablename__ = "repair_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_no: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    customer_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("customers.id"), nullable=True)
    customer_name: Mapped[str] = mapped_column(String(150), nullable=False)
    customer_phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    device_desc: Mapped[str] = mapped_column(String(200), nullable=False)
    imei: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    issue: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="received", index=True)
    estimate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)     # piasters
    final_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # piasters
    parts_cost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)   # piasters (shop's cost)
    paid: Mapped[int] = mapped_column(Integer, nullable=False, default=0)         # piasters received so far
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    received_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    received_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    ready_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    @property
    def balance(self) -> int:
        """Still to collect from the customer (never negative)."""
        return max(0, self.final_price - self.paid)
