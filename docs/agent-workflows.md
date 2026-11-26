# Agent workflows

## Framework (`app/agents/base.py`)
* `AgentSpec(name, display_name, description, tools, max_iterations, timeout_s, read_only)`
* `AgentTask(intent, params, message)` → `AgentResult(success, summary, data, products, sources, suggestions, tool_calls,
  requires_approval, halt, error, duration_ms, iterations)`
* `BaseAgent.run()` wraps `handle()` with `asyncio.wait_for(timeout)`, catches every error, records an
  `AgentExecutionRecord` (in-memory metrics + DB row via `SessionAgentRecorder`) and logs a structured line.
* `AgentRun.call()` increments the iteration counter (raises `AgentLimitExceeded` past `max_iterations`) and sends the call
  to the Plugin Manager with `agent_allowed = spec.tools`, so an agent physically cannot use a tool it wasn't granted.

## Supervisor (`app/agents/supervisor.py`, `app/orchestration/graph.py`)
The control flow is a LangGraph `StateGraph` (nodes `guard → classify → route → execute_group* → synthesize`). If
`langgraph` isn't installed, `FallbackGraph` runs the *same node functions and edges* (used by the unit tests in the build
environment). Intent classification is done by the LLM provider:
* `MockLLMProvider` → `RuleBasedIntentParser` (regex rules + entity extraction: prices incl. "20k"/"1.2 lakh", size, colour,
  category, brand, ordinal, quantity, PIN code, order number, period, coupon, wants_delivery/wants_stock).
* `OpenAIProvider` → function calling with an `intent` **enum** and a strict `entities` schema; falls back to rules on any error.

The LLM never chooses agents or tools directly: the intent maps to a **policy-controlled plan**:

| Intent | Plan (group: agent.intent) |
|---|---|
| product_search | 0: shopping.product_search → 1: inventory.check_results ‖ logistics.delivery_estimate *(if asked)* |
| recommend | 0: product_intelligence.recommend → 1: inventory.check_results |
| product_details / compare_products | product_intelligence |
| add_to_cart / view_cart / remove_from_cart | shopping |
| **checkout** | 0: fraud_detection.assess_checkout → 1: order_management.checkout → 2: payment.pay → 3: logistics.create_shipment → 4: notification.checkout |
| track_order | 0: order_management.track_order → 1: logistics.track_order |
| order_history / cancel_order | order_management |
| return_request | 0: return_refund.return_request → 1: notification (if approved, no approval needed) |
| faq / unknown | customer_support.faq (RAG) |
| escalate | customer_support.escalate |
| payment_issue | 0: payment.payment_issue → 1: customer_support.faq |
| delivery_estimate | logistics |
| low_stock / inventory_check | inventory |
| sales_report / plugin_status / agent_executions | analytics |

**Parallelism:** steps in the same group run with `asyncio.gather` only when *every* agent in the group is `read_only`
(e.g. inventory ‖ logistics after a search); groups with writers run sequentially.
**Failure handling:** a step that fails and is `critical`, or returns `halt=True` (e.g. payment declined, order held for
review), stops the remaining groups; non-critical failures are recorded and the turn continues.
**Composition:** mock mode joins agent summaries; OpenAI mode writes prose from the agents' JSON outputs only.

## Conversation memory
Per-conversation working memory in Redis: `last_products` (with variants), `last_filters` (size/colour), `last_order_id`,
`last_order_number`, `last_order_total`, `risk`, `pay_attempts_{order}`. That is how "add the **first** product" and
"place my order" resolve. Full message history is persisted in PostgreSQL; the last 10 messages feed the OpenAI router.

## Worked example: the spec scenario
"Find me black running shoes under ₹3,000 in size 9. Check availability and delivery."
1. guard: clean. classify → `product_search`, entities `{category: footwear, colour: black, size: 9, max_price: 3000, query: running, wants_delivery, wants_stock}`.
2. group 0 — Shopping: `product_search.search` (falls back by relaxing size/colour/brand if nothing matches), stores
   results in memory, `recommendation.related` for cross-sell.
3. group 1 (parallel, read-only) — Inventory: `inventory.product_stock`; Logistics: `shipping.estimate` (default address PIN).
4. synthesize → "I found 1 black running footwear under ₹3,000: 1. Stridex Velocity Run — ₹2,799 … Stock: 1 of 1 in stock …
   Delivery to 570002 in 1-2 days (…)". Then "add the first product" → cart; "place my order" → the 5-agent checkout plan.

## Event-driven agents
`app/events/handlers.py` runs agents from events with the `SYSTEM` principal: `PaymentSuccessful` → `shipping.create_shipment`
(idempotent), lifecycle events → Notification Agent. Email/WhatsApp sends carry a `dedupe_key` (`template:order_number`) so the
chat flow and the event consumer never notify twice.

## Safety limits per agent
| Agent | max tool calls | timeout | parallel-safe |
|---|---|---|---|
| supervisor | 8 plan steps | 30 s | — |
| shopping | 6 | 15 s | no |
| product_intelligence | 6 | 15 s | yes |
| inventory | 4 | 15 s | yes |
| order_management | 4 | 15 s | no |
| payment | 4 | 15 s | no |
| return_refund | 4 | 15 s | no |
| customer_support | 4 | 15 s | yes |
| logistics | 3 | 15 s | yes |
| fraud_detection | 2 | 15 s | yes |
| analytics | 3 | 15 s | yes |
| notification | 4 | 15 s | yes |
