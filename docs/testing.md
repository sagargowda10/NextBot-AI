# Testing

```bash
cd backend
pip install -r requirements-dev.txt
pytest tests/unit -q              # agents, plugins, RAG, MCP, events, domain, security — no DB needed
pytest tests/integration -q -rs   # FastAPI + SQLAlchemy + SQLite; PostgreSQL concurrency test needs Docker
cd ../frontend && npm install && npm run typecheck && npm run build && npx playwright test   # needs the stack running
```
Async tests use the AnyIO pytest plugin (`@pytest.mark.anyio`) — it ships with AnyIO, which the MCP SDK already depends on;
`pytest-asyncio` is listed as optional.

## Results on the developer's machine (latest run)
Windows 11 · Python 3.12.3 · Node 22 · Docker Desktop · dev stack (`docker-compose.dev.yml`) · 26 Nov 2026

| Step | Result |
|---|---|
| ruff lint | ✅ All checks passed |
| mypy | ✅ Success: no issues found in 140 source files |
| Backend unit tests | ✅ 89 passed |
| Backend integration tests (FastAPI + SQLAlchemy + SQLite, incl. Testcontainers PostgreSQL concurrency) | ✅ 21 passed |
| Alembic `upgrade head` | ✅ |
| Frontend `npm install` / `tsc --noEmit` / `next lint` | ✅ / ✅ / ✅ no warnings |
| Frontend `next build` | ✅ 22 routes |
| Playwright E2E (5 specs against the running stack) | ✅ 5 passed |

**Total: 110 backend tests + 5 browser tests passing, lint and type checks clean.**

## Full infrastructure verified (`docker compose up --build`, 26 Nov 2026)
| Check | Observed |
|---|---|
| `GET /health/ready` | `status: ready` · database `ok` (PostgreSQL + pgvector) · cache `redis:ok` · traces `mongodb:ok` · event_bus `KafkaEventBus` · plugins 12 total / 12 enabled / 0 failed |
| Prometheus targets | `nextbot-backend (1/1 up)`, scraping `backend:8000/metrics` every 15 s |
| Grafana "NextBot AI — Platform Overview" | live HTTP rate and p95 latency per route (cart, orders, tracking, shipments, returns, admin orders, AI chat), plugin executions/s, plugin durations |
| Browser flow on the full stack | login → cart → checkout + mock payment → shipment created via Kafka consumer → admin courier simulation → return request |
| MCP over Streamable HTTP (`scripts/mcp_client_demo.py`, bearer JWT) | `tools/list` returned all 11 tools (`search_products`, `get_product_details`, `check_inventory`, `add_to_cart`, `get_cart`, `create_order`, `get_order_status`, `request_return`, `get_shipment_status`, `get_sales_summary`, `send_notification`); `search_products` returned structured content from PostgreSQL (Stridex Velocity Run, 5 variants with live stock) |

Bugs these runs found and fixed: catalogue `size` param clash (0 products), SQLite "database is locked" under concurrent
writers (`BEGIN IMMEDIATE`), RAG search deadlocking a chat request (read-only session factory), two invalid test inputs.
`scripts/verify.ps1` regenerates `docs/test-results-local.md` with the raw output.

## Results executed earlier in the build environment
Environment: Linux, **Python 3.13.18**, pytest 9.1.1, pydantic 2.13, **mcp 2.3.0**, PyJWT 2.15, starlette 1.7, uvicorn 0.54.
FastAPI, SQLAlchemy, aiosqlite, LangGraph, Node packages for Next.js, and Docker were **not available and could not be installed**
(no network), so the following is exactly what ran:

```
$ pytest -q
89 passed in 1.84s
$ mypy app --config-file pyproject.toml
Success: no issues found in 139 source files   # external libraries missing → treated as Any
$ python -m compileall app tests               # all modules compile
$ node tscheck.js frontend                      # TypeScript parser over all 37 .ts/.tsx/.mjs files
parsed 37 files, 0 syntax diagnostics           # syntax only — not a type-check (no @types/react, next)
```
YAML/JSON for Compose, Kubernetes, CI, Grafana and package/tsconfig files were also parsed successfully (16 files).

| Suite | Tests | Result | What it proves |
|---|---|---|---|
| `unit/test_agents.py` | 15 | ✅ pass | All 12 demos through the **real** Supervisor graph (fallback runner), 11 agents, Plugin Manager and 12 plugins over in-memory services; checkout plan order; payment failure halts pipeline; prompt injection blocked before agents; unanswerable → fallback; agent iteration limit, allow-list and timeout; notification de-duplication |
| `unit/test_plugin_manager.py` | 9 | ✅ pass | exactly 12 plugins with the full contract; all initialise in demo mode; validation, user authorisation, agent allow-list; disabled/unknown plugins; timeout; circuit breaker → FAILED; secrets env-only + masked; failed init reported |
| `unit/test_mcp.py` | 4 | ✅ pass | real MCP JSON-RPC (SDK in-memory transport): tools/list (11 tools + schemas), tools/call structured content, permission and validation errors, plugin-12 discovery + allow-listed call |
| `unit/test_mcp_http.py` | 1 | ✅ pass | MCP over **Streamable HTTP on uvicorn**, bearer-token identity (none / bad / valid) |
| `unit/test_rag.py` | 9 | ✅ pass | chunking, deterministic normalised embeddings, 5 grounded Q&As with correct top source, metadata filter, fallback |
| `unit/test_events.py` | 5 | ✅ pass | routing, idempotent redelivery, retry then success, poison → DLQ without blocking other consumers, backoff/partition key |
| `unit/test_domain.py` | 13 | ✅ pass | GST-inclusive totals, shipping, coupons, order state machine, return window/categories, delivery zones, fraud scoring, approval thresholds |
| `unit/test_intent.py` | 19 | ✅ pass | all 12 demo phrasings + extras; entity extraction (₹, k/lakh, size, colour, ordinal, period) |
| `unit/test_security.py` | 14 | ✅ pass | RBAC, prompt guard (block/allow), HMAC webhooks (tamper, wrong secret, replay), JWT (type, secret, expiry), log redaction |

## Written, run in CI, NOT executed in the build environment
| Suite | Tests | Needs |
|---|---|---|
| `integration/test_api_auth_catalog.py` | 5 | FastAPI, SQLAlchemy, aiosqlite, httpx — health/OpenAPI, auth flow, filters, semantic search, SQL-injection payload, catalogue RBAC |
| `integration/test_api_commerce.py` | 7 | same — cart ops & stock validation, checkout + mock payment + event-driven shipment + stock commit, payment failure + retry + idempotency, 3 failures → cancel + release, order privacy, bad webhook signature, return eligibility |
| `integration/test_api_ai_platform.py` | 6 | same — the 12 chat demos via HTTP, injection refusal, plugin disable/enable/config/execution log, approval workflow + audit, dashboard & `/metrics` |
| `integration/test_api_addresses.py` | 2 | same — address CRUD, single default, duplicate label 409, invalid PIN 422, cross-customer privacy, checkout uses the new default address |
| `integration/test_inventory_concurrency_pg.py` | 1 | Docker + Testcontainers — 20 concurrent reservations of 3 units on PostgreSQL → exactly 3 succeed |
| `frontend/e2e/demo.spec.ts` | 5 | running stack + Playwright — chat journey, catalogue/cart, admin plugin/agent dashboards, unfiltered catalogue regression, address → checkout → admin marks delivered |
| Frontend `tsc` / `next build` | — | Node packages |

These have **not been observed passing**; treat the first run on your machine as their first run. If one fails, the error
message plus `-x -vv` output usually pinpoints the fix quickly.

## Manually verified on the developer's machine (Windows, Docker Desktop, dev stack)
Observed working in the browser on 26 Nov 2026: login, AI assistant demo ("laptop under ₹60,000" → 3 products + stock),
catalogue (22 products), add to cart, address book, checkout with mock UPI (payment SUCCEEDED, order PROCESSING),
order history, admin "All Orders" courier simulation.

## Reproduce everything locally (Windows)
`powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1` — writes `docs/test-results-local.md` with the real pass/fail
of every suite. Copy that table here once it has run.
