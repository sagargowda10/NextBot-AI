from fastapi import APIRouter

from app.api.v1 import admin, ai, analytics, auth, catalog, inventory, orders, plugins

api_router = APIRouter(prefix="/api/v1")
for r in (
    auth.router,
    catalog.products,
    catalog.cart,
    orders.orders,
    orders.payments,
    orders.shipments,
    orders.returns,
    inventory.router,
    ai.router,
    plugins.router,
    analytics.router,
    admin.router,
):
    api_router.include_router(r)
