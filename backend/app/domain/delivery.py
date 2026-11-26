"""Delivery ETA estimation by Indian PIN-code zone (first digit = postal region)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

WAREHOUSE_ZONE = "5"  # primary warehouse in Bengaluru (PIN 56xxxx)

_ZONE_DAYS = {
    "5": (1, 2),  # Karnataka, AP, Telangana
    "6": (2, 3),  # Tamil Nadu, Kerala
    "4": (3, 4),  # Maharashtra, MP, Chhattisgarh
    "3": (3, 5),  # Rajasthan, Gujarat
    "1": (4, 5),  # Delhi, Haryana, Punjab, HP, J&K
    "2": (4, 6),  # UP, Uttarakhand
    "7": (4, 6),  # West Bengal, Odisha, North-East
    "8": (4, 6),  # Bihar, Jharkhand
}


@dataclass(frozen=True)
class DeliveryEstimate:
    pincode: str
    min_days: int
    max_days: int
    earliest: date
    latest: date
    serviceable: bool
    message: str


def estimate_delivery(pincode: str, now: datetime | None = None) -> DeliveryEstimate:
    now = now or datetime.now(UTC)
    pin = (pincode or "").strip()
    if len(pin) != 6 or not pin.isdigit() or pin[0] == "0":
        return DeliveryEstimate(pin, 0, 0, now.date(), now.date(), False, "Please provide a valid 6-digit PIN code.")
    lo, hi = _ZONE_DAYS.get(pin[0], (5, 7))
    if pin[:2] == "56":  # same city as the warehouse
        lo, hi = 1, 1
    earliest, latest = now.date() + timedelta(days=lo), now.date() + timedelta(days=hi)
    msg = f"Delivery to {pin} in {lo}-{hi} days ({earliest:%a %d %b} – {latest:%a %d %b})."
    if lo == hi:
        msg = f"Next-day delivery to {pin} ({earliest:%a %d %b})."
    return DeliveryEstimate(pin, lo, hi, earliest, latest, True, msg)
