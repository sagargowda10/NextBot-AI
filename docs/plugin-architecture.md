# Plugin architecture

## Contract (`app/plugins/base.py`)
```python
class BasePlugin(ABC):
    plugin_id, name, version, description, requires_credentials, default_config, secret_keys
    def get_plugin_id(self) / get_name() / get_version() / get_description()
    async def initialize(self, config) -> None          # merges defaults, validates, may build adapters
    def validate_configuration(self, config) -> list[str]
    async def health_check(self) -> HealthStatus
    async def shutdown(self) -> None
    async def execute(self, action_name, payload: BaseModel, ctx: PluginContext) -> Any
    def actions(self) -> dict[str, PluginAction]         # built from @action-decorated methods

@action("search", ProductFilter, "catalog:read", "Search products with structured filters")
async def search(self, p: ProductFilter, ctx: PluginContext) -> dict: ...
```
`PluginContext` carries the authenticated `Principal`, the per-request `ServiceContainer`, the calling agent and its
allow-list, and the conversation id. Plugins read the user id **from the principal, never from the payload**.

## Plugin Manager + Registry (`app/plugins/manager.py`)
* **Registration** — `register()` rejects duplicate ids; the durable registry row lives in `plugins`.
* **Lifecycle** — `DISABLED → INITIALIZING → ENABLED`, or `FAILED` if `initialize()` raises (e.g. Razorpay selected without keys;
  the error is kept in `stats.last_error`). `enable()`, `disable()` (calls `shutdown()`), `shutdown_all()`.
* **Execution pipeline** — lookup → status → action → Pydantic validation → user permission (`principal.has`) → agent allow-list
  (`plugin.action` or `plugin.*`) → `asyncio.wait_for` → stats + `ExecutionRecord` (ring buffer + buffered DB sink) → `PluginResult`.
  Expected business errors (`DomainError`) become `success=False` with a code; unexpected errors are logged and counted.
* **Circuit breaker** — 5 consecutive unexpected errors/timeouts → `FAILED` until an admin re-enables it.
* **Configuration manager** — `configure()` accepts only known, non-secret keys, re-validates, re-initialises if enabled, and is
  persisted to `plugin_configurations`. `secret_keys` can only come from environment variables and are rendered as `********`.
* **Monitoring** — `summary()` (total/enabled/disabled/failed/executions/successes/failures), per-plugin stats (count, success,
  failure, avg ms, last run, last error), `health()`, `/metrics` gauges and the admin dashboard.

## Discovery & trust
Built-ins are listed explicitly in `app/plugins/registry.py` (exactly 12). Third-party trusted plugins can be shipped as
Python packages exposing the `nextbot.plugins` entry-point group; discovery is **off** unless
`NEXTBOT_ENABLE_ENTRYPOINT_PLUGINS=1`. NextBot never downloads code at runtime, and every plugin — built-in or not — runs
behind the same permission and allow-list checks.

## The 12 plugins
| id | Actions (permission) |
|---|---|
| `product_search` | search, get_details, semantic_search (`catalog:read`) |
| `recommendation` | personalized, similar, frequently_bought, budget, related, customer_budget (`catalog:read`) |
| `inventory` | availability, product_stock (`catalog:read`), low_stock (`inventory:read`), adjust (`inventory:write`), reserve, release (`inventory:reserve`) |
| `payment` | initiate, verify, history (`payment:own`), refund (`payment:refund`), providers |
| `order_management` | cart_get/add/update/remove (`cart:write`), checkout, get, latest, history, cancel (`order:own`), return_request, return_list (`return:own`) |
| `shipping` | create_shipment (`order:own` + ownership + CONFIRMED check), track (`shipment:own`), estimate (`catalog:read`), advance (`shipment:manage`) |
| `customer_support` | answer, faqs, escalate (`support:use`) |
| `whatsapp` | send_message, send_template (`notify:self`), handle_webhook (`notify:any`) |
| `email` | send, templates (`notify:self`) |
| `analytics` | sales_summary, order_report, product_performance, agent_metrics, plugin_status (`analytics:read`), inventory_analytics (`analytics:inventory`) |
| `fraud_detection` | assess_order (`order:own`), assess_payment (`payment:own`) |
| `mcp_integration` | list_servers, discover_tools, call_tool (`mcp:use`; per-server tool allow-list) |

## Adding a plugin
1. Subclass `BasePlugin`, declare `@action`s with Pydantic inputs and a permission.
2. Add the class to `BUILTIN_PLUGINS` (or publish it under the `nextbot.plugins` entry point).
3. Grant the permission to roles in `ROLE_PERMISSIONS` and the action to an agent's `tools`.
4. Write a unit test with `tests/fakes.py`.
