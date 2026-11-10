"""SQLAlchemy ORM models for Phase 1: System tables.

Covers: roles, role_permissions, users, audit_log, settings.
"""
from __future__ import annotations

import datetime
from app.core.clock import utcnow
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ── Timestamps mixin ──────────────────────────────────────────────────────────

class TimestampMixin:
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


# ── Role ──────────────────────────────────────────────────────────────────────

class Role(TimestampMixin, Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    permissions: Mapped[list[RolePermission]] = relationship(
        "RolePermission", back_populates="role", cascade="all, delete-orphan"
    )
    users: Mapped[list[User]] = relationship("User", back_populates="role")

    def permission_codes(self) -> set[str]:
        return {rp.permission_code for rp in self.permissions}

    def __repr__(self) -> str:
        return f"<Role {self.name}>"


# ── RolePermission ────────────────────────────────────────────────────────────

class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(Integer, ForeignKey("roles.id"), nullable=False, index=True)
    permission_code: Mapped[str] = mapped_column(String(100), nullable=False)

    role: Mapped[Role] = relationship("Role", back_populates="permissions")


# ── User ──────────────────────────────────────────────────────────────────────

class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role_id: Mapped[int] = mapped_column(Integer, ForeignKey("roles.id"), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    last_login: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    role: Mapped[Role] = relationship("Role", back_populates="users")

    def permission_codes(self) -> set[str]:
        return self.role.permission_codes() if self.role else set()

    def __repr__(self) -> str:
        return f"<User {self.username}>"


# ── AuditLog ──────────────────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    table_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    record_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # JSON
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # JSON
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )

    user: Mapped[Optional[User]] = relationship("User", foreign_keys=[user_id])

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} by user_id={self.user_id}>"


# ── Setting ───────────────────────────────────────────────────────────────────

class Setting(TimestampMixin, Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Setting {self.key}={self.value!r}>"

