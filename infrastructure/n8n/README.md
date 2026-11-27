# n8n workflow automation

`docker compose up -d` (full stack) starts **n8n on http://localhost:5678** and auto-imports + activates
`nextbot-order-events.json`. The backend forwards every domain event (OrderCreated, PaymentSuccessful/Failed,
ShipmentCreated, OrderDelivered, ReturnRequested, Refund*, Inventory*) to `http://n8n:5678/webhook/nextbot-events`.

Each request carries:
- `X-NextBot-Token` - shared token; the workflow's first node rejects anything else.
- `X-NextBot-Signature` - `sha256=<HMAC of the raw body with N8N_SIGNING_SECRET>` for receivers that verify integrity.
- `X-NextBot-Event` - the event type. Body = the event envelope (`event_type`, `aggregate_id`, `payload`, ...).

Forwarding is best effort: if n8n is down or the workflow is inactive, orders are unaffected and the failure is shown
on **Admin -> Workflows (n8n)** in NextBot.

First visit to http://localhost:5678 asks you to create an n8n owner account (local only). Then open
**Workflows -> NextBot order events -> Executions** to see every event NextBot sent.
If the auto-import didn't run: **Workflows -> Import from File** -> this JSON -> toggle **Active**.

Extend it: replace the "Set" nodes with Telegram / Gmail / Slack / Google Sheets nodes.
