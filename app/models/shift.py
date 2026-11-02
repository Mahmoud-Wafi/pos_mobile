"""ORM models: Shift."""
from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import (
    DateTime, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Shift(Base):
    """Cashier work shift with cash drawer reconciliation."""
    __tablename__ = "shifts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    opened_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, nullable=False, index=True
    )
    closed_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime, nullable=True
    )
    opening_cash: Mapped[int] = mapped_column(Integer, nullable=False, default=0)   # piasters
    expected_cash: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # piasters
    actual_cash: Mapped[int] = mapped_column(Integer, nullable=False, default=0)    # piasters
    diff: Mapped[int] = mapped_column(Integer, nullable=False, default=0)           # actual - expected (signed)
    # open | closed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    user: Mapped[User] = relationship("User")
    sales: Mapped[list[Sale]] = relationship("Sale", back_populates="shift")

    def __repr__(self) -> str:
        return f"<Shift id={self.id} user_id={self.user_id} status={self.status}>"


from app.models.user import User  # noqa: E402, F401
from app.models.sale import Sale  # noqa: E402, F401

