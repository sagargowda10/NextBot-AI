"""Real Model Context Protocol round-trips using the official `mcp` SDK (in-memory transport).

These exercise JSON-RPC initialize → tools/list → tools/call between an SDK client and the
NextBot MCP server, which then runs through the Plugin Manager with permission checks.
"""

import pytest
from mcp import Client

from app.mcp.server import TOOL_MAP
from tests.fakes import ADMIN, CUSTOMER
from tests.unit.harness import make_harness

pytestmark = pytest.mark.anyio


async def test_tool_discovery_lists_all_tools_with_schemas():
    h, _ = await make_harness()
    async with Client(h.mcp_server(CUSTOMER)) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == set(TOOL_MAP) and len(tools) == 11
    schema = tools["search_products"].input_schema
    assert schema["type"] == "object" and "max_price" in schema["properties"] and "ctx" not in schema["properties"]
    assert tools["get_product_details"].input_schema["required"] == ["product_id"]


async def test_tools_call_returns_structured_content():
    h, _ = await make_harness()
    async with Client(h.mcp_server(CUSTOMER)) as client:
        res = await client.call_tool("search_products", {"category": "laptops", "max_price": 60000})
        assert not res.is_error
        names = [i["name"] for i in res.structured_content["items"]]
        assert names and "Nimbus Ultra 16" not in names  # ₹89,990 filtered out
        cart = await client.call_tool("add_to_cart", {"variant_id": 41, "quantity": 1})
        assert cart.structured_content["items"][0]["variant_id"] == 41


async def test_permissions_and_validation_errors_surface_as_tool_errors():
    h, _ = await make_harness()
    async with Client(h.mcp_server(CUSTOMER)) as client:
        denied = await client.call_tool("get_sales_summary", {"period": "this month"})
        assert denied.is_error and "forbidden" in denied.content[0].text
        bad = await client.call_tool("get_product_details", {"product_id": 0})
        assert bad.is_error
    async with Client(h.mcp_server(ADMIN)) as client:
        ok = await client.call_tool("get_sales_summary", {"period": "this month"})
        assert not ok.is_error and "revenue" in ok.structured_content
    assert any(r.agent == "mcp_client" for r in h.plugins.executions("analytics"))


async def test_mcp_integration_plugin_discovers_and_calls_over_protocol():
    h, _ = await make_harness()
    reg = h.plugins.get("mcp_integration")
    reg.plugin.inprocess_server = h.mcp_server(ADMIN)
    from app.plugins.base import PluginContext

    ctx = PluginContext(principal=ADMIN, services=h.services, extras={"plugin_manager": h.plugins})
    disc = await h.plugins.execute("mcp_integration", "discover_tools", {"server": "nextbot"}, ctx)
    assert disc.success and len(disc.data["tools"]) == 11
    assert {t["name"] for t in disc.data["tools"] if t["allowed"]} == {
        "search_products",
        "get_product_details",
        "check_inventory",
        "get_sales_summary",
    }
    call = await h.plugins.execute(
        "mcp_integration", "call_tool", {"server": "nextbot", "tool": "search_products", "arguments": {"category": "audio"}}, ctx
    )
    assert call.success and call.data["result"]["items"][0]["name"] == "Auralis Buds ANC"
    blocked = await h.plugins.execute(
        "mcp_integration", "call_tool", {"server": "nextbot", "tool": "add_to_cart", "arguments": {"variant_id": 41}}, ctx
    )
    assert not blocked.success and "not allow-listed" in blocked.error
    customer_ctx = PluginContext(principal=CUSTOMER, services=h.services)
    assert (await h.plugins.execute("mcp_integration", "list_servers", {}, customer_ctx)).error_code == "forbidden"
