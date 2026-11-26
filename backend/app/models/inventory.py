from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.models.catalog import ProductVariant


class Warehouse(TimestampMixin, Base):
    __tablename__ = "warehouses"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    city: Mapped[str] = mapped_column(String(80))
    pincode: Mapped[str] = mapped_column(String(6))
    priority: Mapped[int] = mapped_column(Integer, default=1)  # lower = picked first


class Inventory(TimestampMixin, Base):
    """On-hand `quantity` and `reserved` units per variant per warehouse.

    Oversell protection: reservations use a single conditional UPDATE
    (`... SET reserved = reserved + :q WHERE quantity - reserved >= :q`) and the CHECK constraints
    below make an oversell impossible even if application code were wrong.
    """

    __tablename__ = "inventory"
    __table_args__ = (
        UniqueConstraint("variant_id", "warehouse_id", name="variant_warehouse"),
        CheckConstraint("quantity >= 0", name="quantity_non_negative"),
        CheckConstraint("reserved >= 0", name="reserved_non_negative"),
        CheckConstraint("reserved <= quantity", name="reserved_lte_quantity"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("product_variants.id", ondelete="CASCADE"), index=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    reserved: Mapped[int] = mapped_column(Integer, default=0)
    variant: Mapped[ProductVariant] = relationship(lazy="selectin")
    warehouse: Mapped[Warehouse] = relationship(lazy="selectin")

    @property
    def available(self) -> int:
        return self.quantity - self.reserved
