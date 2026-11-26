# Model Context Protocol (MCP)

NextBot uses the **official MCP Python SDK v2** (`mcp>=2.3`: `MCPServer`, `Client`). Both directions are implemented.

## NextBot as an MCP server (`app/mcp/server.py`)
11 tools, each mapped to a plugin action and executed through the Plugin Manager (validation, permissions, execution log):

| Tool | Plugin action |
|---|---|
| search_products | product_search.search |
| get_product_details | product_search.get_details |
| check_inventory | inventory.product_stock |
| add_to_cart | order_management.cart_add |
| get_cart | order_management.cart_get |
| create_order | order_management.checkout |
| get_order_status | order_management.get |
| request_return | order_management.return_request |
| get_shipment_status | shipping.track |
| get_sales_summary | analytics.sales_summary (admin only) |
| send_notification | email.send |

Tool schemas are generated from the typed function signatures (Pydantic), so `tools/list` returns JSON Schemas with
constraints (e.g. `product_id > 0`). Results are returned as **structured content** (`structured_content`) plus text.
Failures (permission denied, validation, business errors) are raised as `ToolError` → `is_error=true` with a message.

### Transports & identity
* **Streamable HTTP** — mounted at **`/mcp/`** (stateless, JSON responses, DNS-rebinding protection via `MCP_ALLOWED_HOSTS`).
  Send `Authorization: Bearer <access token from /api/v1/auth/login>`; the server verifies the JWT on every call and runs the
  tool as that user. No/invalid token → tool error.
* **stdio** — `NEXTBOT_MCP_USER=asha@nextbot.demo python -m app.mcp.stdio_main` for desktop MCP hosts; logs go to stderr.

Claude Desktop example (`claude_desktop_config.json`):
```json
{ "mcpServers": { "nextbot": { "command": "python", "args": ["-m", "app.mcp.stdio_main"],
  "cwd": "/path/to/NextBot-AI/backend", "env": { "NEXTBOT_MCP_USER": "asha@nextbot.demo", "DATABASE_URL": "sqlite+aiosqlite:///./nextbot.db" } } } }
```
Python client: `scripts/mcp_client_demo.py`.

## NextBot as an MCP client (plugin 12, `app/plugins/builtin/mcp_integration.py`)
* Configured servers (`servers: [{name, transport: inprocess|http|stdio, url|command, allowed_tools}]`).
* `discover_tools` → `tools/list`, marking which tools are allow-listed.
* `call_tool` → `tools/call` only if the tool is in that server's `allowed_tools`; permission `mcp:use` (admin/system).
* Default server `nextbot` uses the SDK's in-process transport to NextBot's own server (a real JSON-RPC session), which makes
  the round-trip demonstrable with no external service.

## Verified
* `tests/unit/test_mcp.py` (in-memory transport): discovery of all 11 tools with schemas; structured results; customer
  denied `get_sales_summary`; invalid input rejected; admin allowed; plugin-12 discovery and allow-listed call; non-allow-listed
  tool blocked; customer cannot use plugin 12.
* `tests/unit/test_mcp_http.py` (**real Streamable HTTP over uvicorn**, mounted like `main.py`): no token → error, bad token →
  error, valid token → success.
