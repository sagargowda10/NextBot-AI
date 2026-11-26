"""In-memory implementations of the service contracts.

They let the full Supervisor → agents → Plugin Manager → plugins path run in unit tests with no
database. Business rules are the real ones from `app/domain`, so behaviour matches production.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.core.enums import OrderStatus, Role
from app.core.exceptions import NotFoundError, OutOfStockError, PermissionDenied, ValidationFailed
from app.domain.delivery import estimate_delivery
from app.domain.fraud_rules import RiskSignals
from app.domain.order_state import assert_transition, is_cancellable
from app.domain.pricing import LineInput, calculate_totals
from app.domain.returns import check_return_eligibility
from app.rag.embeddings import HashingEmbedder
from app.rag.pipeline import RagPipeline, load_markdown_docs
from app.rag.vector_store import InMemoryVectorStore
from app.schemas.catalog import ProductDetail, ProductFilter, ProductSummary, VariantOut
from app.schemas.commerce import (
    CartItemOut,
    CartOut,
    CheckoutRequest,
    DeliveryEstimateOut,
    InventoryAdjustResult,
    OrderItemOut,
    OrderOut,
    PaymentOut,
    RefundOut,
    ReturnOut,
    ShipmentEvent,
    ShipmentOut,
    StockLevel,
)
from app.schemas.platform import GroundedAnswer, NotificationOut, SalesSummary
from app.security.permissions import Principal
from app.services.contracts import ServiceContainer

ids = itertools.count(1000)
NOW = datetime.now(UTC)

CUSTOMER = Principal(user_id=1, email="asha@example.com", roles=frozenset({Role.CUSTOMER}), name="Asha")
ADMIN = Principal(user_id=9, email="admin@nextbot.local", roles=frozenset({Role.ADMIN}), name="Admin")
INV_MGR = Principal(user_id=8, email="inventory@nextbot.local", roles=frozenset({Role.INVENTORY_MANAGER}), name="Inv")

# id, name, brand, category, price, mrp, rating, variants [(size, colour, stock)], tags, specs
CATALOG = [
    (
        1,
        "Voltix AirBook 14",
        "voltix",
        "laptops",
        54990,
        64990,
        4.4,
        [(None, "silver", 12)],
        "thin light office",
        {"CPU": "Ryzen 5", "RAM": "16 GB"},
    ),
    (2, "Nimbus Pro 15", "nimbus", "laptops", 58990, 69990, 4.2, [(None, "grey", 3)], "gaming office", {"CPU": "Core i5", "RAM": "16 GB"}),
    (
        3,
        "Nimbus Ultra 16",
        "nimbus",
        "laptops",
        89990,
        99990,
        4.7,
        [(None, "black", 5)],
        "gaming creator",
        {"CPU": "Core i7", "RAM": "32 GB"},
    ),
    (
        4,
        "Stridex Velocity Run",
        "stridex",
        "footwear",
        2799,
        3999,
        4.5,
        [("8", "black", 4), ("9", "black", 6), ("10", "black", 0)],
        "running",
        {"Use": "Road running"},
    ),
    (5, "Stridex Trail Pro", "stridex", "footwear", 4499, 5499, 4.3, [("9", "black", 2)], "running trail", {"Use": "Trail"}),
    (6, "Stridex Daily Walk", "stridex", "footwear", 1999, 2499, 4.0, [("9", "white", 9)], "casual walking", {"Use": "Walking"}),
    (7, "Nimbus Note 5G", "nimbus", "smartphones", 18999, 21999, 4.1, [(None, "blue", 20)], "5g", {"Display": "6.6 in"}),
    (8, "Voltix Edge 5G", "voltix", "smartphones", 31999, 34999, 4.6, [(None, "black", 7)], "5g camera", {"Display": "6.7 in"}),
    (9, "Auralis Buds ANC", "auralis", "audio", 3999, 5999, 4.4, [(None, "black", 40)], "wireless noise cancelling", {"Battery": "30 h"}),
]


def _summary(p: tuple, stock: dict[int, int], score: float | None = None) -> ProductSummary:
    pid, name, brand, cat, price, mrp, rating, variants, _tags, _specs = p
    vs = [
        VariantOut(id=pid * 10 + i, sku=f"SKU-{pid}-{i}", size=s, colour=c, price=Decimal(price), stock_available=stock[pid * 10 + i])
        for i, (s, c, _) in enumerate(variants)
    ]
    return ProductSummary(
        id=pid,
        name=name,
        slug=name.lower().replace(" ", "-"),
        brand=brand.title(),
        category=cat,
        price=Decimal(price),
        mrp=Decimal(mrp),
        discount_percent=round((mrp - price) / mrp * 100),
        rating=rating,
        in_stock=any(v.stock_available for v in vs),
        variants=vs,
        score=score,
    )


@dataclass
class Store:
    stock: dict[int, int] = field(default_factory=dict)  # variant_id -> available
    reserved: dict[int, int] = field(default_factory=dict)
    carts: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    orders: dict[int, dict[str, Any]] = field(default_factory=dict)
    payments: dict[int, dict[str, Any]] = field(default_factory=dict)
    shipments: dict[int, dict[str, Any]] = field(default_factory=dict)
    returns: list[dict[str, Any]] = field(default_factory=list)
    notifications: list[NotificationOut] = field(default_factory=list)
    approvals: list[dict[str, Any]] = field(default_factory=list)
    failed_payments: int = 0

    def __post_init__(self) -> None:
        for p in CATALOG:
            for i, (_s, _c, qty) in enumerate(p[7]):
                self.stock[p[0] * 10 + i] = qty
                self.reserved[p[0] * 10 + i] = 0

    def product(self, pid: int) -> tuple:
        for p in CATALOG:
            if p[0] == pid:
                return p
        raise NotFoundError("product")

    def variant(self, vid: int) -> tuple[tuple, int]:
        return self.product(vid // 10), vid % 10


class FakeProducts:
    def __init__(self, s: Store) -> None:
        self.s = s

    async def search(self, f: ProductFilter) -> list[ProductSummary]:
        out = []
        for p in CATALOG:
            pid, name, brand, cat, price, *_rest = p
            variants, tags = p[7], p[8]
            if f.category and cat != f.category or f.brand and brand != f.brand:
                continue
            if f.max_price is not None and price > f.max_price or f.min_price is not None and price < f.min_price:
                continue
            if f.query and not all(w in (name + " " + tags).lower() for w in f.query.lower().split()):
                continue
            if (f.size or f.colour) and not any((not f.size or s == f.size) and (not f.colour or c == f.colour) for s, c, _ in variants):
                continue
            out.append(_summary(p, self.s.stock))
        return sorted(out, key=lambda x: -x.rating)[: f.limit]

    async def get(self, product_id: int) -> ProductDetail | None:
        try:
            p = self.s.product(product_id)
        except NotFoundError:
            return None
        return ProductDetail(**_summary(p, self.s.stock).model_dump(), description=f"{p[1]} — {p[8]}", specifications=p[9])

    async def semantic_search(self, query: str, limit: int = 5) -> list[ProductSummary]:
        return [_summary(p, self.s.stock) for p in CATALOG if any(w in p[8] for w in query.lower().split())][:limit]


class FakeRecs:
    def __init__(self, s: Store) -> None:
        self.s = s

    async def personalized(self, user_id: int, category: str | None, budget: Decimal | None, limit: int) -> list[ProductSummary]:
        return [_summary(p, self.s.stock) for p in CATALOG if not category or p[3] == category][:limit]

    async def similar(self, product_id: int, limit: int) -> list[ProductSummary]:
        cat = self.s.product(product_id)[3]
        return [_summary(p, self.s.stock) for p in CATALOG if p[3] == cat and p[0] != product_id][:limit]

    async def frequently_bought(self, product_id: int, limit: int) -> list[ProductSummary]:
        return []

    async def budget_picks(self, category: str | None, budget: Decimal, limit: int) -> list[ProductSummary]:
        picks = [p for p in CATALOG if (not category or p[3] == category) and p[4] <= budget]
        return [_summary(p, self.s.stock) for p in sorted(picks, key=lambda p: -p[6])][:limit]

    async def customer_budget(self, user_id: int, category: str | None) -> Decimal | None:
        return Decimal("25000") if category == "smartphones" else None


class FakeInventory:
    def __init__(self, s: Store) -> None:
        self.s = s

    def _level(self, vid: int) -> StockLevel:
        p, i = self.s.variant(vid)
        avail = self.s.stock[vid] - self.s.reserved[vid]
        return StockLevel(
            inventory_id=vid,
            variant_id=vid,
            product_id=p[0],
            product_name=p[1],
            sku=f"SKU-{p[0]}-{i}",
            warehouse="BLR-1",
            quantity=self.s.stock[vid],
            reserved=self.s.reserved[vid],
            available=avail,
            low_stock=avail <= 5,
        )

    async def availability(self, variant_ids: list[int]) -> list[StockLevel]:
        return [self._level(v) for v in variant_ids]

    async def for_products(self, product_ids: list[int]) -> list[StockLevel]:
        return [self._level(v) for v in self.s.stock if v // 10 in product_ids]

    async def low_stock(self, threshold: int) -> list[StockLevel]:
        return [lv for lv in (self._level(v) for v in self.s.stock) if lv.available <= threshold]

    async def adjust(self, principal: Principal, inventory_id: int, delta: int, reason: str) -> InventoryAdjustResult:
        self.s.stock[inventory_id] += delta
        return InventoryAdjustResult(applied=True, stock=self._level(inventory_id))

    async def reserve_for_order(self, order_id: int) -> bool:
        for it in self.s.orders[order_id]["items"]:
            if self.s.stock[it["variant_id"]] - self.s.reserved[it["variant_id"]] < it["quantity"]:
                raise OutOfStockError("out of stock")
        for it in self.s.orders[order_id]["items"]:
            self.s.reserved[it["variant_id"]] += it["quantity"]
        return True

    async def release_for_order(self, order_id: int) -> bool:
        for it in self.s.orders[order_id]["items"]:
            self.s.reserved[it["variant_id"]] -= it["quantity"]
        return True


class FakeCart:
    def __init__(self, s: Store) -> None:
        self.s = s

    async def get(self, user_id: int) -> CartOut:
        items = self.s.carts.get(user_id, [])
        outs = []
        for it in items:
            p, i = self.s.variant(it["variant_id"])
            outs.append(
                CartItemOut(
                    id=it["id"],
                    variant_id=it["variant_id"],
                    product_id=p[0],
                    product_name=p[1],
                    sku=f"SKU-{p[0]}-{i}",
                    size=p[7][i][0],
                    colour=p[7][i][1],
                    unit_price=Decimal(p[4]),
                    quantity=it["quantity"],
                    line_total=Decimal(p[4]) * it["quantity"],
                )
            )
        t = calculate_totals([LineInput(o.unit_price, o.quantity) for o in outs])
        return CartOut(id=user_id, items=outs, subtotal=t.subtotal, discount=t.discount, tax=t.tax, shipping=t.shipping, total=t.total)

    async def add(self, user_id: int, variant_id: int, quantity: int) -> CartOut:
        if self.s.stock.get(variant_id, 0) - self.s.reserved.get(variant_id, 0) < quantity:
            raise OutOfStockError("Not enough stock")
        self.s.carts.setdefault(user_id, []).append({"id": next(ids), "variant_id": variant_id, "quantity": quantity})
        return await self.get(user_id)

    async def update(self, user_id: int, item_id: int, quantity: int) -> CartOut:
        for it in self.s.carts.get(user_id, []):
            if it["id"] == item_id:
                it["quantity"] = quantity
        self.s.carts[user_id] = [i for i in self.s.carts.get(user_id, []) if i["quantity"] > 0]
        return await self.get(user_id)

    async def remove(self, user_id: int, item_id: int) -> CartOut:
        self.s.carts[user_id] = [i for i in self.s.carts.get(user_id, []) if i["id"] != item_id]
        return await self.get(user_id)


class FakeOrders:
    def __init__(self, s: Store, inv: FakeInventory, cart: FakeCart) -> None:
        self.s, self.inv, self.cart = s, inv, cart

    def _out(self, o: dict[str, Any]) -> OrderOut:
        items = [
            OrderItemOut(
                id=n,
                product_id=it["variant_id"] // 10,
                variant_id=it["variant_id"],
                product_name=it["name"],
                sku="SKU",
                quantity=it["quantity"],
                unit_price=it["price"],
                line_total=it["price"] * it["quantity"],
            )
            for n, it in enumerate(o["items"])
        ]
        return OrderOut(
            id=o["id"],
            order_number=o["number"],
            user_id=o["user_id"],
            status=o["status"],
            subtotal=o["total"],
            discount=Decimal(0),
            tax=Decimal(0),
            shipping_fee=Decimal(0),
            total=o["total"],
            items=items,
            created_at=o["created_at"],
            delivered_at=o.get("delivered_at"),
            risk_score=o.get("risk"),
        )

    def _owned(self, principal: Principal, order_id: int) -> dict[str, Any]:
        o = self.s.orders.get(order_id)
        if o is None or not principal.can_access_user_resource(o["user_id"], "order:read_all"):
            raise NotFoundError("Order not found")
        return o

    async def checkout(self, principal: Principal, req: CheckoutRequest, risk_score: int | None = None) -> OrderOut:
        cart = await self.cart.get(principal.user_id or 0)
        if not cart.items:
            raise ValidationFailed("Your cart is empty")
        oid = next(ids)
        o = {
            "id": oid,
            "number": f"NB-{oid}",
            "user_id": principal.user_id,
            "status": OrderStatus.CREATED,
            "total": cart.total,
            "created_at": datetime.now(UTC),
            "risk": risk_score,
            "items": [
                {"variant_id": i.variant_id, "quantity": i.quantity, "price": i.unit_price, "name": i.product_name} for i in cart.items
            ],
        }
        self.s.orders[oid] = o
        await self.inv.reserve_for_order(oid)
        o["status"] = assert_transition(o["status"], OrderStatus.PAYMENT_PENDING)
        self.s.carts[principal.user_id or 0] = []
        return self._out(o)

    async def get(self, principal: Principal, order_id: int) -> OrderOut:
        return self._out(self._owned(principal, order_id))

    async def latest(self, principal: Principal, status: str | None = None) -> OrderOut | None:
        mine = [o for o in self.s.orders.values() if o["user_id"] == principal.user_id and (status is None or o["status"] == status)]
        return self._out(max(mine, key=lambda o: o["created_at"])) if mine else None

    async def history(self, principal: Principal, limit: int = 10) -> list[OrderOut]:
        mine = sorted((o for o in self.s.orders.values() if o["user_id"] == principal.user_id), key=lambda o: o["created_at"], reverse=True)
        return [self._out(o) for o in mine[:limit]]

    async def cancel(self, principal: Principal, order_id: int, reason: str, agent: str | None = None) -> dict[str, Any]:
        o = self._owned(principal, order_id)
        if not is_cancellable(o["status"]):
            raise ValidationFailed(f"Order is {o['status']}")
        o["status"] = assert_transition(o["status"], OrderStatus.CANCELLED)
        await self.inv.release_for_order(order_id)
        return {"order": self._out(o).model_dump(mode="json"), "approval_request_id": None}


class FakePayments:
    def __init__(self, s: Store) -> None:
        self.s = s

    async def initiate(self, principal: Principal, order_id: int, method: str, idempotency_key: str) -> PaymentOut:
        for p in self.s.payments.values():
            if p["key"] == idempotency_key:
                return p["out"]
        o = self.s.orders[order_id]
        if o["user_id"] != principal.user_id:
            raise PermissionDenied("not your order")
        ok = method != "mock_fail"
        pid = next(ids)
        out = PaymentOut(
            id=pid,
            order_id=order_id,
            provider="mock",
            method=method,
            amount=o["total"],
            status="SUCCEEDED" if ok else "FAILED",
            provider_reference=f"mock_pay_{pid}",
            failure_reason=None if ok else "Card declined (simulated)",
            is_simulated=True,
            created_at=datetime.now(UTC),
        )
        self.s.payments[pid] = {"key": idempotency_key, "out": out}
        if ok:
            o["status"] = assert_transition(o["status"], OrderStatus.CONFIRMED)
        else:
            self.s.failed_payments += 1
        return out

    async def get(self, principal: Principal, payment_id: int) -> PaymentOut:
        return self.s.payments[payment_id]["out"]

    async def history(self, principal: Principal, limit: int = 10) -> list[PaymentOut]:
        return [p["out"] for p in reversed(list(self.s.payments.values()))][:limit]

    async def refund(self, principal: Principal, payment_id: int, amount: Decimal, reason: str, agent: str | None = None) -> RefundOut:
        return RefundOut(id=next(ids), payment_id=payment_id, amount=amount, status="COMPLETED", reason=reason)


class FakeShipments:
    def __init__(self, s: Store) -> None:
        self.s = s

    async def create_for_order(self, order_id: int) -> ShipmentOut:
        if order_id in self.s.shipments:
            return self.s.shipments[order_id]["out"]
        o = self.s.orders[order_id]
        if o["status"] != OrderStatus.CONFIRMED:
            raise ValidationFailed("Order is not confirmed")
        o["status"] = assert_transition(o["status"], OrderStatus.PROCESSING)
        est = estimate_delivery("570001")
        out = ShipmentOut(
            id=next(ids),
            order_id=order_id,
            carrier="MockExpress",
            tracking_number=f"MX{order_id}",
            status="CREATED",
            estimated_delivery=est.latest,
            events=[ShipmentEvent(status="CREATED", at=datetime.now(UTC), note="Shipment booked")],
        )
        self.s.shipments[order_id] = {"out": out}
        return out

    async def track(self, principal: Principal, order_id: int) -> ShipmentOut | None:
        rec = self.s.shipments.get(order_id)
        return rec["out"] if rec else None

    async def estimate(self, pincode: str) -> DeliveryEstimateOut:
        return DeliveryEstimateOut(**estimate_delivery(pincode).__dict__)

    async def advance(self, shipment_id: int, status: str, location: str | None = None) -> ShipmentOut:
        raise NotImplementedError

    async def default_pincode(self, user_id: int) -> str | None:
        return "570001"


class FakeReturns:
    def __init__(self, s: Store, orders: FakeOrders) -> None:
        self.s, self.orders = s, orders

    async def request(self, principal: Principal, order_id: int | None, reason: str, agent: str | None = None) -> ReturnOut:
        mine = [o for o in self.s.orders.values() if o["user_id"] == principal.user_id and o["status"] == OrderStatus.DELIVERED]
        if not mine:
            raise NotFoundError("You have no delivered orders to return.")
        o = max(mine, key=lambda x: x["created_at"])
        el = check_return_eligibility(status=o["status"], delivered_at=o["delivered_at"], category_slugs=["footwear"], window_days=10)
        status = "PENDING_APPROVAL" if o["total"] >= 10000 else "APPROVED"
        if el.eligible:
            o["status"] = assert_transition(o["status"], OrderStatus.RETURN_REQUESTED)
        r = ReturnOut(
            id=next(ids),
            order_id=o["id"],
            order_number=o["number"],
            status=status if el.eligible else "REJECTED",
            reason=reason,
            refund_amount=o["total"],
            eligible=el.eligible,
            eligibility_message=el.reason,
            created_at=datetime.now(UTC),
        )
        self.s.returns.append(r.model_dump())
        return r

    async def list(self, principal: Principal) -> list[ReturnOut]:
        return [ReturnOut(**r) for r in reversed(self.s.returns)]


class FakeSupport:
    def __init__(self) -> None:
        self.rag = RagPipeline(HashingEmbedder(384), InMemoryVectorStore())
        self._indexed = False

    async def answer(self, question: str, category: str | None = None) -> GroundedAnswer:
        if not self._indexed:
            await self.rag.index(load_markdown_docs())
            self._indexed = True
        return await self.rag.answer(question)

    async def faqs(self) -> list[dict[str, str]]:
        return [{"q": "Return window?", "a": "10 days"}]

    async def escalate(self, principal: Principal, conversation_id: int | None, summary: str) -> dict[str, Any]:
        return {"ticket": "SUP-1001", "status": "OPEN"}


class FakeNotifications:
    def __init__(self, s: Store) -> None:
        self.s = s
        self.keys: dict[int, str | None] = {}

    async def record(
        self,
        *,
        user_id: int | None,
        channel: str,
        template: str,
        recipient: str,
        subject: str | None,
        body: str,
        status: str,
        meta: dict[str, Any] | None = None,
    ) -> NotificationOut:
        n = NotificationOut(
            id=next(ids),
            user_id=user_id,
            channel=channel,
            template=template,
            recipient=recipient,
            subject=subject,
            body=body,
            status=status,
            created_at=datetime.now(UTC),
        )
        self.keys[n.id] = (meta or {}).get("dedupe_key")
        self.s.notifications.append(n)
        return n

    async def recipient_for(self, user_id: int, channel: str) -> str | None:
        return "asha@example.com" if channel == "EMAIL" else "+919800000001"

    async def already_sent(self, user_id: int, channel: str, dedupe_key: str) -> bool:
        return any(n.user_id == user_id and n.channel == channel and self.keys.get(n.id) == dedupe_key for n in self.s.notifications)


class FakeAnalytics:
    def __init__(self, s: Store) -> None:
        self.s = s

    async def sales_summary(self, period: str) -> SalesSummary:
        paid = [
            o
            for o in self.s.orders.values()
            if o["status"] not in (OrderStatus.CREATED, OrderStatus.PAYMENT_PENDING, OrderStatus.CANCELLED)
        ]
        rev = sum((o["total"] for o in paid), Decimal(0))
        return SalesSummary(
            period=period,
            start=NOW - timedelta(days=30),
            end=NOW,
            revenue=rev,
            orders=len(paid),
            average_order_value=(rev / len(paid)).quantize(Decimal("0.01")) if paid else Decimal(0),
        )

    async def product_performance(self, limit: int) -> list[dict[str, Any]]:
        return [{"product_id": 4, "name": "Stridex Velocity Run", "units": 12, "revenue": "33588"}][:limit]

    async def inventory_insights(self, threshold: int) -> dict[str, Any]:
        return {"low_stock": 3}

    async def order_stats(self) -> dict[str, Any]:
        return {"total": len(self.s.orders)}


class FakeRisk:
    def __init__(self, s: Store, cart: FakeCart) -> None:
        self.s, self.cart = s, cart

    async def signals_for(self, user_id: int) -> RiskSignals:
        return RiskSignals(
            account_age_days=200,
            failed_payments_24h=self.s.failed_payments,
            orders_last_hour=0,
            avg_order_value=Decimal("3000"),
            lifetime_orders=4,
        )

    async def cart_total(self, user_id: int) -> Decimal:
        return (await self.cart.get(user_id)).total


class FakeApprovals:
    def __init__(self, s: Store) -> None:
        self.s = s

    async def create(self, *, action: str, summary: str, payload: dict[str, Any], agent: str | None, user_id: int | None) -> int:
        self.s.approvals.append({"action": action, "summary": summary})
        return len(self.s.approvals)


def build_services(store: Store | None = None) -> tuple[ServiceContainer, Store]:
    s = store or Store()
    inv, cart = FakeInventory(s), FakeCart(s)
    orders = FakeOrders(s, inv, cart)
    return ServiceContainer(
        products=FakeProducts(s),
        recommendations=FakeRecs(s),
        inventory=inv,
        cart=cart,
        orders=orders,
        payments=FakePayments(s),
        shipments=FakeShipments(s),
        returns=FakeReturns(s, orders),
        support=FakeSupport(),
        notifications=FakeNotifications(s),
        analytics=FakeAnalytics(s),
        risk=FakeRisk(s, cart),
        approvals=FakeApprovals(s),
    ), s


def add_delivered_order(s: Store, user_id: int = 1, total: int = 2799, days_ago: int = 3) -> int:
    oid = next(ids)
    s.orders[oid] = {
        "id": oid,
        "number": f"NB-{oid}",
        "user_id": user_id,
        "status": OrderStatus.DELIVERED,
        "total": Decimal(total),
        "created_at": NOW - timedelta(days=days_ago + 3),
        "delivered_at": NOW - timedelta(days=days_ago),
        "items": [{"variant_id": 41, "quantity": 1, "price": Decimal(total), "name": "Stridex Velocity Run"}],
    }
    return oid
