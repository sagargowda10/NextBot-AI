"""Orders, payments, shipments and returns."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_state, page_params
from app.core.state import AppState
from app.database.session import get_session
from app.schemas.commerce import (
    CancelRequest,
    CheckoutRequest,
    OrderOut,
    PaymentInitiate,
    PaymentOut,
    ReturnCreate,
    ReturnOut,
    ShipmentOut,
    ShipmentStatusUpdate,
)
from app.schemas.common import Page, PageParams
from app.security.dependencies import get_principal, require
from app.security.permissions import Principal
from app.services.order_service import OrderService
from app.services.payment_service import PaymentService
from app.services.return_service import ReturnService
from app.services.shipment_service import ShipmentService

orders = APIRouter(prefix="/orders", tags=["Orders"])
payments = APIRouter(prefix="/payments", tags=["Payments"])
shipments = APIRouter(prefix="/shipments", tags=["Shipments"])
returns = APIRouter(prefix="/returns", tags=["Returns"])


def deps(session: AsyncSession = Depends(get_session), state: AppState = Depends(get_state)) -> tuple[AsyncSession, AppState]:
    return session, state


@orders.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def checkout(body: CheckoutRequest, principal: Principal = Depends(require("order:own")), d=Depends(deps)) -> OrderOut:  # type: ignore[no-untyped-def]
    """Validate cart → reserve stock → create order (PAYMENT_PENDING) → optionally pay in one step."""
    order = await OrderService(*d).checkout(principal, body)
    if body.payment_method in ("mock_upi", "mock_card", "mock_fail", "razorpay", "stripe"):
        key = body.idempotency_key or f"api-{order.id}-{uuid.uuid4().hex[:8]}"
        await PaymentService(*d).initiate(principal, order.id, body.payment_method, key)
        order = await OrderService(*d).get(principal, order.id)
    return order


@orders.get("", response_model=Page[OrderOut])
async def my_orders(principal: Principal = Depends(get_principal), p: PageParams = Depends(page_params), d=Depends(deps)) -> Page[OrderOut]:  # type: ignore[no-untyped-def]
    svc = OrderService(*d)
    return Page(items=await svc.history(principal, p.size, p.offset), total=await svc.count_for(principal), page=p.page, size=p.size)


@orders.get("/{order_id}", response_model=OrderOut)
async def get_order(order_id: int, principal: Principal = Depends(get_principal), d=Depends(deps)) -> OrderOut:  # type: ignore[no-untyped-def]
    return await OrderService(*d).get(principal, order_id)


@orders.post("/{order_id}/cancel")
async def cancel_order(order_id: int, body: CancelRequest, principal: Principal = Depends(get_principal), d=Depends(deps)) -> dict:  # type: ignore[no-untyped-def]
    return await OrderService(*d).cancel(principal, order_id, body.reason)


@orders.get("/{order_id}/tracking", response_model=ShipmentOut | None)
async def track_order(order_id: int, principal: Principal = Depends(get_principal), d=Depends(deps)) -> ShipmentOut | None:  # type: ignore[no-untyped-def]
    return await ShipmentService(*d).track(principal, order_id)


@payments.post("/initiate", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
async def initiate(body: PaymentInitiate, principal: Principal = Depends(require("payment:own")), d=Depends(deps)) -> PaymentOut:  # type: ignore[no-untyped-def]
    return await PaymentService(*d).initiate(principal, body.order_id, body.method, body.idempotency_key)


@payments.get("/{payment_id}", response_model=PaymentOut)
async def get_payment(payment_id: int, principal: Principal = Depends(get_principal), d=Depends(deps)) -> PaymentOut:  # type: ignore[no-untyped-def]
    return await PaymentService(*d).get(principal, payment_id)


@payments.post("/webhook")
async def payment_webhook(request: Request, x_nextbot_signature: str | None = Header(None), d=Depends(deps)) -> dict:  # type: ignore[no-untyped-def]
    """Gateway callback. Body must be signed: `X-NextBot-Signature: t=<unix>,v1=<hmac_sha256(secret, t.body)>`."""
    return await PaymentService(*d).handle_webhook(await request.body(), x_nextbot_signature)


@shipments.get("/{shipment_id}", response_model=ShipmentOut)
async def get_shipment(shipment_id: int, principal: Principal = Depends(get_principal), d=Depends(deps)) -> ShipmentOut:  # type: ignore[no-untyped-def]
    return await ShipmentService(*d).get(principal, shipment_id)


@shipments.post("/{shipment_id}/status", response_model=ShipmentOut, dependencies=[Depends(require("shipment:manage"))])
async def advance_shipment(shipment_id: int, body: ShipmentStatusUpdate, d=Depends(deps)) -> ShipmentOut:  # type: ignore[no-untyped-def]
    """Courier webhook / admin: progress a shipment (PACKED → SHIPPED → OUT_FOR_DELIVERY → DELIVERED)."""
    return await ShipmentService(*d).advance(shipment_id, body.status, body.location)


@returns.post("", response_model=ReturnOut, status_code=status.HTTP_201_CREATED)
async def create_return(body: ReturnCreate, principal: Principal = Depends(require("return:own")), d=Depends(deps)) -> ReturnOut:  # type: ignore[no-untyped-def]
    return await ReturnService(*d).request(principal, body.order_id, body.reason)


@returns.get("", response_model=list[ReturnOut])
async def list_returns(principal: Principal = Depends(get_principal), d=Depends(deps)) -> list[ReturnOut]:  # type: ignore[no-untyped-def]
    return await ReturnService(*d).list(principal)


@returns.get("/{return_id}", response_model=ReturnOut)
async def get_return(return_id: int, principal: Principal = Depends(get_principal), d=Depends(deps)) -> ReturnOut:  # type: ignore[no-untyped-def]
    return await ReturnService(*d).get(principal, return_id)


@returns.post("/{return_id}/receive", response_model=ReturnOut)
async def receive_return(return_id: int, principal: Principal = Depends(require("return:manage")), d=Depends(deps)) -> ReturnOut:  # type: ignore[no-untyped-def]
    return await ReturnService(*d).mark_received(principal, return_id)
