from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Column, ForeignKey, Integer, Numeric, String, Table, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)


class Permission(Base):
    __tablename__ = "permissions"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str] = mapped_column(String(200), default="")


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True)
    description: Mapped[str] = mapped_column(String(200), default="")
    permissions: Mapped[list[Permission]] = relationship(secondary=role_permissions, lazy="selectin")


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(16))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    roles: Mapped[list[Role]] = relationship(secondary=user_roles, lazy="selectin")
    profile: Mapped[CustomerProfile | None] = relationship(back_populates="user", lazy="selectin", uselist=False)
    addresses: Mapped[list[Address]] = relationship(back_populates="user", lazy="selectin", cascade="all, delete-orphan")

    @property
    def role_names(self) -> list[str]:
        return [r.name for r in self.roles]


class CustomerProfile(TimestampMixin, Base):
    __tablename__ = "customer_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    preferred_categories: Mapped[list[Any]] = mapped_column(default=list)
    budget_hints: Mapped[dict[str, Any]] = mapped_column(default=dict)  # {"smartphones": 25000}
    preferred_channel: Mapped[str] = mapped_column(String(16), default="EMAIL")
    whatsapp_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    loyalty_points: Mapped[int] = mapped_column(Integer, default=0)
    lifetime_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    user: Mapped[User] = relationship(back_populates="profile")


class Address(TimestampMixin, Base):
    __tablename__ = "addresses"
    __table_args__ = (UniqueConstraint("user_id", "label", name="user_label"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(40), default="Home")
    line1: Mapped[str] = mapped_column(String(200))
    line2: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(80))
    pincode: Mapped[str] = mapped_column(String(6), index=True)
    phone: Mapped[str] = mapped_column(String(16))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    user: Mapped[User] = relationship(back_populates="addresses")
