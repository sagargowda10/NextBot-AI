# Security

## Authentication
* **JWT** (PyJWT, HS256, issuer `nextbot-ai`): 30-min access + 7-day refresh tokens with a `type` claim; using a refresh
  token as an access token (or vice versa) is rejected. `JWT_SECRET` must be ≥ 32 characters.
* Roles are re-read from the database on every request, so revoking a role takes effect immediately.
* **bcrypt** via `pwdlib` (12 rounds). Unknown-email logins verify against a real dummy hash to equalise timing.
* OAuth2-ready: `HTTPBearer` security scheme; an IdP's tokens can replace `decode_token` without touching routes.

## Authorisation
* Roles: `ADMIN`, `CUSTOMER`, `SUPPORT_AGENT`, `INVENTORY_MANAGER` (+ internal `SYSTEM` for consumers / service MCP).
* Permission strings (`catalog:read`, `order:own`, `order:read_all`, `inventory:write`, `analytics:read`, `plugins:manage`…)
  checked centrally by `require(...)` dependencies and by the Plugin Manager for every plugin action.
* **Ownership**: orders, payments, shipments, returns and conversations are filtered by `user_id`; foreign IDs return **404**
  (not 403) so IDs can't be probed. Tested: `test_orders_are_private`.

## Input & data protection
* Pydantic validation on every request body, query and plugin payload; strict patterns for PIN, phone, payment method, periods.
* SQLAlchemy bound parameters only — no string-built SQL. Tested with an injection payload (`test_sql_injection_attempt_is_inert`).
* No card numbers or CVVs are ever accepted or stored; payments keep provider references only.
* Secrets come only from environment variables, are never returned by the API (`********`) and cannot be set through the
  plugin config API. Logs are JSON with key-based redaction (`password`, `token`, `api_key`, `authorization`, `card`, `cvv`…)
  and Bearer-token scrubbing.
* Security headers on API and frontend (`nosniff`, `DENY` framing, referrer policy); CORS allow-list; non-root containers,
  read-only root FS in Kubernetes.

## Abuse controls
* Rate limiting per user token (or IP) with Redis fixed windows: auth and chat buckets (`CHAT_RATE_LIMIT_PER_MINUTE`).
* **Webhooks**: `X-NextBot-Signature: t=<unix>,v1=<HMAC-SHA256(secret, "t." + body)>`, constant-time compare, 5-minute replay
  window, and event-id de-duplication.
* Audit log for logins, checkouts, payments, cancellations, returns, stock adjustments, plugin changes and approval decisions.

## AI security
| Threat | Control |
|---|---|
| Prompt injection ("ignore previous instructions", "reveal system prompt", tool/role forgery) | `prompt_guard.inspect_message` blocks before any agent runs; flagged-but-allowed phrases (e.g. "I am the admin") grant nothing because permissions come from the JWT |
| LLM picks dangerous tools | LLM only returns an enum intent; plans are fixed per intent; each agent has a tool allow-list enforced by the Plugin Manager |
| Malformed/hostile tool arguments | Pydantic validation of every payload; user id taken from the principal, never from arguments |
| Runaway loops | per-agent `max_iterations`, per-agent timeout, per-plugin timeout, supervisor step cap, graph recursion limit |
| Indirect injection via documents | retrieved text wrapped as quoted data; RAG prompt forbids following document instructions |
| Sensitive actions | human approval for refunds ≥ ₹10,000, cancellations ≥ ₹50,000, stock adjustments ≥ 500 units, risk score ≥ 60 |
| Leaking prompts/credentials | refusal path; system prompts never echoed; secrets never in context |
| Fraud false positives | rule scores only *recommend* review; nothing auto-rejects a customer |
