"""NextBot MCP server — exposes controlled commerce tools over the Model Context Protocol.

Built on the official `mcp` Python SDK (v2, `MCPServer`). Every tool call is routed through the
Plugin Manager, so MCP clients get exactly the same validation, permission checks and execution
logging as the in-app agents. Identity:
  * Streamable HTTP (`/mcp`): `Authorization: Bearer <JWT>` is verified server-side per call.
  * stdio / in-process: the server's configured service principal is used.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from app.core.logging import get_logger
from app.plugins.base import PluginResult
from app.security.permissions import Principal

log = get_logger("mcp")


class ToolGateway(Protocol):
    async def call(self, plugin_id: str, action: str, payload: dict[str, Any], principal: Principal) -> PluginResult: ...


Authenticator = Callable[[str], Awaitable[Principal]]

TOOL_MAP: dict[str, tuple[str, str]] = {
    "search_products": ("product_search", "search"),
    "get_product_details": ("product_search", "get_details"),
    "check_inventory": ("inventory", "product_stock"),
    "add_to_cart": ("order_management", "cart_add"),
    "get_cart": ("order_management", "cart_get"),
    "create_order": ("order_management", "checkout"),
    "get_order_status": ("order_management", "get"),
    "request_return": ("order_management", "return_request"),
    "get_shipment_status": ("shipping", "track"),
    "get_sales_summary": ("analytics", "sales_summary"),
    "send_notification": ("email", "send"),
}


def build_mcp_server(
    gateway: ToolGateway,
    *,
    default_principal: Principal | None,
    authenticate: Authenticator | None = None,
) -> MCPServer:
    server: MCPServer = MCPServer(
        name="nextbot-commerce",
        version="1.0.0",
        instructions="NextBot AI commerce tools. All calls are permission-checked against the authenticated user.",
    )

    async def resolve(ctx: Context | None) -> Principal:
        headers = ctx.headers if ctx is not None else None
        auth = (headers or {}).get("authorization") or (headers or {}).get("Authorization")
        if auth and auth.lower().startswith("bearer ") and authenticate is not None:
            try:
                return await authenticate(auth.split(" ", 1)[1])
            except Exception as exc:
                raise ToolError("Invalid or expired token") from exc
        if headers is not None and default_principal is None:
            raise ToolError("Authentication required: send Authorization: Bearer <token>")
        if default_principal is None:
            raise ToolError("No principal configured for this transport")
        return default_principal

    async def run(tool: str, payload: dict[str, Any], ctx: Context | None) -> dict[str, Any]:
        principal = await resolve(ctx)
        plugin_id, action = TOOL_MAP[tool]
        clean = {k: v for k, v in payload.items() if v is not None}
        result = await gateway.call(plugin_id, action, clean, principal)
        log.info("mcp_tool_call", extra={"tool": tool, "ok": result.success, "user": principal.user_id})
        if not result.success:
            raise ToolError(f"{result.error_code}: {result.error}")
        data = result.data
        return data if isinstance(data, dict) else {"result": data}

    @server.tool(description="Search the product catalogue with optional filters (price in INR).")
    async def search_products(
        ctx: Context,
        query: str | None = None,
        category: str | None = None,
        brand: str | None = None,
        colour: str | None = None,
        size: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        limit: int = Field(10, ge=1, le=50),
    ) -> dict[str, Any]:
        return await run(
            "search_products",
            dict(
                query=query, category=category, brand=brand, colour=colour, size=size, min_price=min_price, max_price=max_price, limit=limit
            ),
            ctx,
        )

    @server.tool(description="Full details and specifications of one product.")
    async def get_product_details(ctx: Context, product_id: int = Field(gt=0)) -> dict[str, Any]:
        return await run("get_product_details", {"product_id": product_id}, ctx)

    @server.tool(description="Stock levels for one or more products across warehouses.")
    async def check_inventory(ctx: Context, product_ids: list[int]) -> dict[str, Any]:
        return await run("check_inventory", {"product_ids": product_ids}, ctx)

    @server.tool(description="Add a product variant to the authenticated user's cart.")
    async def add_to_cart(ctx: Context, variant_id: int = Field(gt=0), quantity: int = Field(1, ge=1, le=10)) -> dict[str, Any]:
        return await run("add_to_cart", {"variant_id": variant_id, "quantity": quantity}, ctx)

    @server.tool(description="The authenticated user's cart with totals.")
    async def get_cart(ctx: Context) -> dict[str, Any]:
        return await run("get_cart", {}, ctx)

    @server.tool(description="Check out the authenticated user's cart into an order (mock payment in demo mode).")
    async def create_order(ctx: Context, coupon_code: str | None = None, address_id: int | None = None) -> dict[str, Any]:
        return await run("create_order", {"coupon_code": coupon_code, "address_id": address_id}, ctx)

    @server.tool(description="Status and items of one of the user's orders.")
    async def get_order_status(ctx: Context, order_id: int = Field(gt=0)) -> dict[str, Any]:
        return await run("get_order_status", {"order_id": order_id}, ctx)

    @server.tool(description="Request a return for a delivered order (eligibility is checked).")
    async def request_return(ctx: Context, order_id: int | None = None, reason: str = "Not as expected") -> dict[str, Any]:
        return await run("request_return", {"order_id": order_id, "reason": reason}, ctx)

    @server.tool(description="Shipment tracking timeline for an order.")
    async def get_shipment_status(ctx: Context, order_id: int = Field(gt=0)) -> dict[str, Any]:
        return await run("get_shipment_status", {"order_id": order_id}, ctx)

    @server.tool(description="Revenue/orders summary for a period (admin only).")
    async def get_sales_summary(ctx: Context, period: str = "this month") -> dict[str, Any]:
        return await run("get_sales_summary", {"period": period}, ctx)

    @server.tool(description="Send a templated notification email to the authenticated user.")
    async def send_notification(ctx: Context, template: str = "generic", message: str = "") -> dict[str, Any]:
        return await run("send_notification", {"template": template, "context": {"message": message}}, ctx)

    return server
