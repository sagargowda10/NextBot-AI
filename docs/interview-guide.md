# Interview guide — NextBot AI

Answers describe **this codebase** (file paths in `backend/app/...`). Be ready to open the file and show it.

## A. Core explanations (the 20 must-know topics)
1. **Why Python?** The AI ecosystem (LangGraph, OpenAI SDK, MCP SDK, pgvector client) is Python-first, asyncio handles I/O-heavy
   orchestration well, and type hints + Pydantic + mypy give compile-time-ish safety. One language for API, agents and RAG.
2. **Why FastAPI?** Async-native, Pydantic v2 validation, dependency injection (`Depends`) for sessions/auth/rate limits, automatic
   OpenAPI. Security dependencies (`security/dependencies.py`) centralise authn/authz.
3. **Why LangGraph?** The Supervisor is a state machine with a loop (execute groups until done/halted) and conditional edges;
   LangGraph models that explicitly (`orchestration/graph.py`). We avoided adding LangChain on top — no overlapping frameworks.
4. **What is Agentic AI?** Systems where a model decides *what to do next* and acts through tools, not just text generation.
   Here the model classifies intent; agents act via plugins, observe results and compose an answer.
5. **What is a multi-agent system?** Several specialised agents with narrow tools and responsibilities, coordinated by a
   supervisor — easier to secure, test and reason about than one agent with every tool.
6. **What is a Supervisor Agent?** `agents/supervisor.py`: guard → classify → route to a policy plan → execute groups
   (sequential or safe-parallel) → synthesize. It has **no tools** itself.
7. **What is plugin architecture?** Capabilities packaged behind a common contract (`plugins/base.py`) and executed by a
   manager that adds validation, permissions, metrics and lifecycle. Agents and MCP both use plugins.
8. **What is MCP?** The Model Context Protocol: JSON-RPC for tool discovery (`tools/list`) and invocation (`tools/call`) between
   AI hosts and tool servers. We expose 11 commerce tools (`mcp/server.py`) and consume MCP servers (plugin 12).
9. **What is RAG?** Retrieval-Augmented Generation: retrieve relevant chunks from a knowledge base by vector similarity and
   answer from them with citations (`rag/pipeline.py`); fall back when nothing relevant is found.
10. **What is tool calling?** The model emits a structured function call matching a JSON schema. Our OpenAI router uses a
    forced `route_request` function with an `intent` enum; agents then call plugin actions with Pydantic-validated payloads.
11. **Why Kafka?** Durable, ordered (per key), replayable event log for decoupled consumers (fulfilment, notifications,
    analytics), with consumer groups for scaling and DLQ topics for poison messages (`events/kafka.py`).
12. **Why Redis?** Low-latency shared state: conversation memory, search-ID cache and rate-limit counters across replicas.
13. **Why PostgreSQL?** ACID transactions for money and stock, constraints (CHECK, UNIQUE, FK), rich indexing and pgvector so
    embeddings live next to the data they describe.
14. **Why MongoDB?** Schemaless per-turn agent traces (plan, entities, outputs) that change shape often and are append-heavy —
    a poor fit for rigid tables, a good fit for documents.
15. **How does checkout work?** `services/order_service.py`: savepoint → load cart → address → coupon → totals (GST-inclusive,
    shipping) → create order + items → **atomic stock reservation** per line → status `PAYMENT_PENDING` → increment coupon use
    → clear cart → outbox `OrderCreated` → optional fraud approval → audit. Then `payment_service.initiate`.
16. **How does payment failure work?** Payment row `FAILED` with reason, `order.payment_failures += 1`, `PaymentFailed` event;
    stock stays reserved for 30 minutes so the customer can retry with a new idempotency key; at 3 failures or reservation
    expiry (sweeper) the order is cancelled and stock released.
17. **How do agents collaborate?** Through the Supervisor's plan and shared conversation **memory**: Shopping stores
    `last_products`; Order Management stores `last_order_id`; Payment reads it; Logistics creates the shipment; Notification
    reads `last_order_number/total`. `halt=True` stops the chain.
18. **How does plugin registration work?** `plugins/registry.py` lists 12 built-ins (optional entry-point discovery, off by
    default). `bootstrap.start()` registers, applies env + admin config, initialises (ENABLED/FAILED) and syncs `plugins` rows.
19. **How is the application secured?** JWT + bcrypt, DB-sourced roles, permission strings checked by routes and the Plugin
    Manager, ownership filters, Pydantic validation, bound SQL, HMAC webhooks, rate limits, audit log, secrets env-only, prompt
    guard, agent allow-lists/limits, human approvals. See `docs/security.md`.
20. **How is it deployed?** Docker images → GHCR via GitHub Actions → Kubernetes (Deployments, HPA, Ingress, migration Job) on
    EKS with RDS/pgvector, ElastiCache, MSK. Local: Docker Compose (full or lightweight).

## B. General project questions (30)
1. *Elevator pitch?* An e-commerce platform where a supervisor and 11 agents handle shopping-to-support via 12 governed plugins, with RAG, MCP and event-driven fulfilment; runs offline in demo mode.
2. *What makes it more than a chatbot?* Agents perform real state changes (cart, order, payment, shipment, return) through audited services, not canned replies.
3. *Monolith or microservices?* Modular monolith with seams (service Protocols, outbox events) that allow extraction later without premature distributed complexity.
4. *Walk through "Find black running shoes under ₹3,000 in size 9…".* Intent `product_search` → Shopping searches with filters → Inventory and Logistics run in parallel → reply with products, stock and ETA.
5. *How does "add the first product" know which product?* Redis conversation memory `last_products`, plus remembered size/colour to choose the variant.
6. *How do you prevent overselling?* Conditional `UPDATE … WHERE quantity - reserved >= q` plus CHECK constraints; tested with 20 concurrent buyers on PostgreSQL.
7. *What is demo mode?* `AI_PROVIDER=mock`, `PAYMENT_PROVIDER=mock`, mock courier/email/WhatsApp — every flow works and responses say they're simulated.
8. *How do you avoid pretending something is live?* `demo_mode`/`ai_provider` in chat responses, `is_simulated` on payments/shipments, `SIMULATED` notifications, plugin `mode`.
9. *What happens if the LLM is down?* OpenAI provider falls back to rules for routing and to deterministic summaries/extractive answers.
10. *How is the order state controlled?* A transition table in `domain/order_state.py`; every status change calls `assert_transition`.
11. *How are returns decided?* `domain/returns.py`: delivered, inside `RETURN_WINDOW_DAYS`, not already requested, no non-returnable categories.
12. *How do refunds work?* Approved return → warehouse "receive" → restock + `refund_internal` (gateway refund, Refund row, events).
13. *What needs human approval?* Refunds ≥ ₹10k, cancellations ≥ ₹50k, stock deltas ≥ 500, risk ≥ 60 — configurable.
14. *What does the approval executor do?* `ApprovalService.decide` runs the action in a savepoint, stores result/FAILED, audits.
15. *How is fraud handled?* Explainable rules (`domain/fraud_rules.py`) → score + reasons → review recommendation; never auto-reject.
16. *What's in the knowledge base?* Seven Markdown policies (returns, shipping, payments, warranty, store, cancellation, account/coupons) plus product descriptions.
17. *How do notifications avoid duplicates?* `dedupe_key = template:order_number` checked per channel before sending.
18. *How are events published reliably?* Transactional outbox → relay → bus; consumers dedupe by `event_id`.
19. *What are the 12 demos?* Listed in the README; each is covered by unit tests (fakes) and HTTP integration tests.
20. *How is the frontend structured?* Next.js App Router, 20 client pages, `AppShell` role-aware navigation, `useAuth` context, `api()` fetch wrapper with refresh.
21. *How does the UI show agent work?* Each reply has an expandable "Agents" trail with tools, durations and success.
22. *How are admins notified of failures?* Plugin dashboard (failed count, last error, execution log), agent dashboard, Prometheus/Grafana.
23. *What metrics exist?* HTTP RED metrics, plugin enabled/executions/latency, agent executions/latency, event outcomes.
24. *Where are agent traces?* `agent_executions` + `agent_tool_executions` tables, Mongo `agent_traces`, in-memory metrics.
25. *What would you build next?* Real streaming responses (SSE), per-tenant plugins, vector search for products in OpenSearch, offline LLM evals.
26. *Biggest trade-off?* Deterministic plans per intent trade some flexibility for safety and testability.
27. *How do you test agents without an LLM or DB?* Mock provider + in-memory service fakes implementing the same contracts.
28. *What didn't you verify?* In the build sandbox, API/DB integration and frontend build couldn't run (packages unavailable); they're in CI. Be upfront about it.
29. *How does it handle multiple channels?* Channel abstraction on conversations and notification adapters; web chat fully implemented, WhatsApp/email via plugins, voice as an extension point.
30. *Why INR and Indian PIN zones?* Target market realism: GST-inclusive pricing, ₹ formatting, PIN-prefix delivery estimates.

## C. Python (15)
1. *Why `async` everywhere?* Most work is I/O (DB, Redis, HTTP, LLM); asyncio lets one worker serve many concurrent requests.
2. *`asyncio.gather` use?* Parallel read-only agent groups in `execute_group`.
3. *`asyncio.wait_for`?* Timeouts on agents and plugin actions; raises `TimeoutError` (3.11+ alias).
4. *Protocols vs ABCs?* ABC for plugins (shared behaviour + required methods); `typing.Protocol` for service contracts (structural typing, easy fakes).
5. *Dataclasses vs Pydantic?* Dataclasses for internal records (`ExecutionRecord`, `RiskSignals`); Pydantic for validated boundaries (DTOs, tool inputs).
6. *Decorators in the code?* `@action` attaches metadata to plugin methods; `BasePlugin.__init__` collects them.
7. *`StrEnum`?* Enum values are strings (DB/JSON friendly) with type safety (`core/enums.py`).
8. *Context managers?* `async with session.begin_nested()` savepoints, `asynccontextmanager` service factories, MCP session manager.
9. *Structural pattern matching?* `match task.intent:` in agents and approval execution.
10. *Decimal for money?* Avoid float rounding; `quantize(…, ROUND_HALF_UP)` in `domain/pricing.py`.
11. *Type hints + mypy?* `mypy` with the pydantic plugin passes on `app/` (139 files).
12. *Circular imports?* Avoided with layered packages and local imports at call sites where services reference each other.
13. *`lru_cache`?* Settings singleton and the dummy bcrypt hash.
14. *Logging?* Stdlib logging with a JSON formatter and recursive redaction of sensitive keys.
15. *Deterministic embeddings?* `hashlib.blake2b` feature hashing — stable across processes (unlike Python's salted `hash()`).

## D. FastAPI (15)
1. *Dependency injection example?* `get_session` (unit of work), `get_state`, `require("perm")`, `rate_limit(...)`.
2. *How is a request's transaction committed?* The `get_session` yield-dependency commits on success, rolls back on exceptions.
3. *Error handling?* `DomainError` hierarchy mapped to status codes by one exception handler; unhandled errors → generic 500 (logged).
4. *Validation?* Pydantic models for bodies; `Query(..., pattern=, ge=, le=)` for params; 422 on failure.
5. *Auth?* `HTTPBearer` scheme → JWT decode → load user → `Principal`.
6. *Role checks?* `Depends(require("plugins:manage"))` on routes or router-level dependencies.
7. *Pagination?* `page_params` dependency → `Page[T]` DTO with `total/page/size`.
8. *Never exposing ORM entities?* Mappers (`services/mappers.py`) build DTOs; `response_model` on every route.
9. *Lifespan?* Creates tables in dev, seeds, starts plugins/RAG/events/MCP session manager; stops them on shutdown.
10. *Middleware?* CORS, security headers, Prometheus timing.
11. *Mounting sub-apps?* The MCP Starlette app is mounted at `/mcp`.
12. *App factory?* `create_app(settings)` — run with `uvicorn app.main:create_app --factory`; tests build isolated apps.
13. *Webhooks?* Raw body read (`await request.body()`) to verify the HMAC before parsing.
14. *OpenAPI?* Auto-generated at `/docs`; tags per router; description explains demo mode and MCP.
15. *Testing?* `TestClient` runs the lifespan against SQLite; integration tests assert HTTP behaviour end-to-end.

## E. Agentic AI (15)
1. *Why a fixed plan per intent instead of free-form tool selection?* Predictability, security and testability; the LLM's job is understanding language.
2. *How are tools constrained?* Agent allow-lists enforced by the Plugin Manager, plus user permissions.
3. *Iteration limits?* `max_iterations` per agent; exceeding raises `AgentLimitExceeded` → safe failure.
4. *What if an agent crashes?* `BaseAgent.run` catches it, returns `success=False`, records the error; the supervisor decides to halt or continue.
5. *How is context passed between agents?* Conversation memory dict persisted in Redis between turns.
6. *Structured outputs?* `AgentResult` (Pydantic) and the OpenAI function schema for routing.
7. *Prompt injection defence?* Guard node blocks known patterns; permissions come from JWT; retrieved text is quoted data.
8. *Grounding?* Composer prompt uses only agent outputs JSON; RAG answers only from retrieved chunks or returns the fallback.
9. *Observability for agents?* Per-run records (duration, iterations, tool calls, error), per-agent stats, dashboard, Mongo traces.
10. *Human-in-the-loop placement?* Sensitive actions create ApprovalRequests; agents report "awaiting review" instead of acting.
11. *Parallelism safety?* Only read-only agents in the same group run concurrently.
12. *Mock vs real LLM?* `LLMProvider` protocol; `MockLLMProvider` (rules) and `OpenAIProvider` are interchangeable via config.
13. *How do events trigger agents?* Consumers run the Notification Agent / shipping plugin with the SYSTEM principal.
14. *How would you evaluate the agent?* Golden conversations (like `test_agents.py`) with expected plans/outcomes; track intent accuracy and tool error rates.
15. *How does MCP relate to agents?* MCP exposes the same plugin actions to external agents with the same guard-rails.

## F. Plugin architecture (10)
1. *Required interface?* `get_plugin_id/get_name/get_version/get_description/initialize/execute/validate_configuration/health_check/shutdown`.
2. *How are actions declared?* `@action(name, InputModel, permission, description)`.
3. *Execution steps?* Lookup, status, action, validation, user permission, agent permission, timeout, record, structured result.
4. *Statuses?* ENABLED, DISABLED, INITIALIZING, FAILED.
5. *Circuit breaker?* Five consecutive unexpected errors → FAILED until re-enabled.
6. *Secrets?* `secret_keys` are env-only, rejected by the config API, masked in responses.
7. *Execution logs?* Ring buffer for the dashboard + batched DB sink into `plugin_executions`; aggregates on `plugins`.
8. *External providers?* Adapters (Razorpay, Stripe, Shiprocket, WhatsApp Cloud, SMTP) raise `ExternalServiceNotConfigured` without credentials.
9. *Untrusted plugins?* Not loaded by default; entry-point discovery is opt-in and still sandboxed by permissions/allow-lists (not process isolation — call that out).
10. *Testing a plugin?* Instantiate, `PluginManager.register`, execute with a `PluginContext` built from `tests/fakes.py`.

## G. Database & system design (10)
1. *Why one cart per user with unique (cart, variant)?* Simplifies merges and prevents duplicate lines.
2. *Why snapshot prices/addresses on orders?* Orders must not change when catalogue or profile changes.
3. *Idempotent payments?* Unique `idempotency_key`; replays return the existing payment; mismatched reuse → 409.
4. *Outbox vs publishing directly?* Direct publish can lose events or publish for rolled-back transactions; outbox is atomic with the data.
5. *Exactly-once?* At-least-once delivery + idempotent consumers (`processed_events` unique key) = effectively once.
6. *Indexes chosen?* Category+price for listing, user+created for history, status for dashboards, HNSW for vectors, unique keys for idempotency.
7. *Scaling reads?* Redis ID cache, optional OpenSearch read model, read replicas for analytics.
8. *Scaling writes?* Stateless API replicas; short transactions; per-row conditional updates for hot stock rows.
9. *Data retention?* Agent traces in Mongo (TTL index recommended); Kafka retention 7 days; audit logs kept in Postgres.
10. *Splitting into microservices?* Payments and notifications first — they already communicate via events and service contracts.
