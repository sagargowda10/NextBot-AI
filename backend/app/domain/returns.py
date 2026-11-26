"""Return eligibility rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.enums import OrderStatus

NON_RETURNABLE_CATEGORIES = frozenset({"innerwear", "personal-care", "gift-cards"})


@dataclass(frozen=True)
class Eligibility:
    eligible: bool
    reason: str
    window_ends: datetime | None = None


def check_return_eligibility(
    *,
    status: OrderStatus | str,
    delivered_at: datetime | None,
    category_slugs: list[str],
    window_days: int,
    now: datetime | None = None,
    already_requested: bool = False,
) -> Eligibility:
    now = now or datetime.now(UTC)
    if already_requested:
        return Eligibility(False, "A return has already been requested for this order.")
    if OrderStatus(status) != OrderStatus.DELIVERED or delivered_at is None:
        return Eligibility(False, "Only delivered orders can be returned.")
    if delivered_at.tzinfo is None:
        delivered_at = delivered_at.replace(tzinfo=UTC)
    window_ends = delivered_at + timedelta(days=window_days)
    if now > window_ends:
        return Eligibility(False, f"The {window_days}-day return window ended on {window_ends:%d %b %Y}.", window_ends)
    blocked = sorted(set(category_slugs) & NON_RETURNABLE_CATEGORIES)
    if blocked:
        return Eligibility(False, f"Items in {', '.join(blocked)} are not returnable.", window_ends)
    return Eligibility(True, f"Eligible for return until {window_ends:%d %b %Y}.", window_ends)
