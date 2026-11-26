"""Order state machine. Every status change in the system goes through `assert_transition`."""

from __future__ import annotations

from app.core.enums import OrderStatus as S
from app.core.exceptions import ConflictError

ALLOWED: dict[S, frozenset[S]] = {
    S.CREATED: frozenset({S.PAYMENT_PENDING, S.CANCELLED}),
    S.PAYMENT_PENDING: frozenset({S.CONFIRMED, S.CANCELLED}),
    S.CONFIRMED: frozenset({S.PROCESSING, S.CANCELLED}),
    S.PROCESSING: frozenset({S.PACKED, S.CANCELLED}),
    S.PACKED: frozenset({S.SHIPPED}),
    S.SHIPPED: frozenset({S.OUT_FOR_DELIVERY, S.DELIVERED}),
    S.OUT_FOR_DELIVERY: frozenset({S.DELIVERED}),
    S.DELIVERED: frozenset({S.RETURN_REQUESTED}),
    S.RETURN_REQUESTED: frozenset({S.RETURNED, S.DELIVERED}),  # DELIVERED = return rejected
    S.CANCELLED: frozenset(),
    S.RETURNED: frozenset(),
}

CANCELLABLE = frozenset({S.CREATED, S.PAYMENT_PENDING, S.CONFIRMED, S.PROCESSING})


def can_transition(current: S, target: S) -> bool:
    return target in ALLOWED.get(current, frozenset())


def assert_transition(current: S | str, target: S | str) -> S:
    cur, tgt = S(current), S(target)
    if not can_transition(cur, tgt):
        raise ConflictError(
            f"Order cannot move from {cur.value} to {tgt.value}",
            details={"from": cur.value, "to": tgt.value},
        )
    return tgt


def is_cancellable(status: S | str) -> bool:
    return S(status) in CANCELLABLE
