"""NextBot GitHub webhook receiver (Flask).

GitHub -> (HTTPS via ngrok) -> POST /github/webhook -> verify HMAC-SHA256 signature -> store the event in
MongoDB Atlas (or memory) -> live dashboard at GET /.

Handles: ping, push (commits/branch/pusher), workflow_run (CI requested / in progress / success / failure),
and stores any other event generically. GitHub retries are de-duplicated by the X-GitHub-Delivery id.

Run:  python app.py            (reads .env: GITHUB_WEBHOOK_SECRET, MONGO_URL, MONGO_DB, PORT)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from collections import deque
from datetime import UTC, datetime
from typing import Any, Protocol

from flask import Flask, jsonify, render_template_string, request

try:  # optional: python app.py loads .env; tests set env vars directly
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

log = logging.getLogger("github-webhook")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


# ---------------------------------------------------------------- storage
class EventStore(Protocol):
    name: str

    def add(
        self, doc: dict[str, Any]
    ) -> bool: ...  # False when this delivery was already stored
    def recent(self, limit: int = 50) -> list[dict[str, Any]]: ...


class MemoryStore:
    name = "memory"

    def __init__(self) -> None:
        self.docs: deque[dict[str, Any]] = deque(maxlen=500)

    def add(self, doc: dict[str, Any]) -> bool:
        if any(d["delivery_id"] == doc["delivery_id"] for d in self.docs):
            return False
        self.docs.appendleft(doc)
        return True

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(self.docs)[:limit]


class MongoStore:
    name = "mongodb"

    def __init__(self, url: str, db: str) -> None:
        from pymongo import DESCENDING, MongoClient

        self.client: Any = MongoClient(
            url, serverSelectionTimeoutMS=8000, appname="nextbot-github-webhook"
        )
        self.col = self.client[db]["github_events"]
        self.col.create_index(
            "delivery_id", unique=True
        )  # GitHub redeliveries are stored once
        self.col.create_index([("received_at", DESCENDING)])

    def add(self, doc: dict[str, Any]) -> bool:
        from pymongo.errors import DuplicateKeyError

        try:
            self.col.insert_one(dict(doc))
            return True
        except DuplicateKeyError:
            return False

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(self.col.find({}, {"_id": 0}).sort("received_at", -1).limit(limit))


def build_store() -> EventStore:
    url = os.getenv("MONGO_URL", "").strip()
    if not url:
        log.info("MONGO_URL not set - keeping events in memory")
        return MemoryStore()
    store = MongoStore(url, os.getenv("MONGO_DB", "nextbot"))
    store.client.admin.command(
        "ping"
    )  # fail fast with a clear error if Atlas is unreachable
    log.info("connected to MongoDB (%s)", os.getenv("MONGO_DB", "nextbot"))
    return store


# ---------------------------------------------------------------- GitHub specifics
def verify_signature(secret: str, body: bytes, header: str | None) -> bool:
    """X-Hub-Signature-256 = 'sha256=' + HMAC-SHA256(secret, raw body). Constant-time compare."""
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)


def summarize(event: str, p: dict[str, Any]) -> dict[str, Any]:
    repo = (p.get("repository") or {}).get("full_name")
    if event == "ping":
        return {
            "repo": repo,
            "title": "Webhook connected",
            "detail": p.get("zen"),
            "status": "ok",
        }
    if event == "push":
        commits = p.get("commits") or []
        branch = str(p.get("ref", "")).removeprefix("refs/heads/")
        head = p.get("head_commit") or {}
        return {
            "repo": repo,
            "title": f"Push to {branch}: {len(commits)} commit(s)",
            "detail": (head.get("message") or "").splitlines()[0][:140]
            if head
            else None,
            "actor": (p.get("pusher") or {}).get("name"),
            "url": p.get("compare"),
            "status": "ok",
            "commits": [
                {
                    "id": c.get("id", "")[:7],
                    "message": (c.get("message") or "").splitlines()[0][:120],
                }
                for c in commits[:20]
            ],
        }
    if event == "workflow_run":
        run = p.get("workflow_run") or {}
        state = run.get("conclusion") or run.get(
            "status"
        )  # success / failure / in_progress / queued ...
        return {
            "repo": repo,
            "title": f"{run.get('name', 'Workflow')} #{run.get('run_number')}: {state}",
            "detail": f"{run.get('head_branch')} @ {str(run.get('head_sha', ''))[:7]} - {(run.get('display_title') or '')[:100]}",
            "actor": (run.get("actor") or {}).get("login"),
            "url": run.get("html_url"),
            "status": {
                "success": "ok",
                "failure": "fail",
                "cancelled": "warn",
                "timed_out": "fail",
            }.get(state, "info"),
        }
    return {
        "repo": repo,
        "title": f"{event} event",
        "detail": p.get("action"),
        "status": "info",
    }


# ---------------------------------------------------------------- app
DASHBOARD = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="refresh" content="5">
<title>NextBot · GitHub webhooks</title>
<style>
 :root{--bg:#f6f7fb;--card:#fff;--ink:#111827;--muted:#6b7280;--line:#e5e7eb;--ok:#16a34a;--fail:#dc2626;--warn:#d97706;--info:#4f46e5}
 @media (prefers-color-scheme:dark){:root{--bg:#0f172a;--card:#111827;--ink:#e5e7eb;--muted:#94a3b8;--line:#1f2937}}
 body{margin:0;font:14px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;background:var(--bg);color:var(--ink)}
 main{max-width:960px;margin:0 auto;padding:24px 16px}
 h1{font-size:20px;margin:0 0 4px} .muted{color:var(--muted)}
 .ev{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--info);border-radius:10px;padding:12px 14px;margin:10px 0}
 .ok{border-left-color:var(--ok)} .fail{border-left-color:var(--fail)} .warn{border-left-color:var(--warn)}
 .row{display:flex;gap:8px;justify-content:space-between;flex-wrap:wrap} .tag{font-size:12px;padding:1px 8px;border-radius:99px;border:1px solid var(--line)}
 a{color:var(--info)} ul{margin:6px 0 0 18px;padding:0} code{font-size:12px}
</style></head><body><main>
<h1>GitHub → NextBot webhook</h1>
<p class="muted">Store: <b>{{ store }}</b> · {{ events|length }} recent event(s) · auto-refreshes every 5 s ·
POST endpoint: <code>/github/webhook</code></p>
{% for e in events %}
<div class="ev {{ e.status }}">
  <div class="row"><b>{{ e.title }}</b><span class="tag">{{ e.event }}</span></div>
  <div class="muted">{{ e.repo or '' }}{% if e.actor %} · by {{ e.actor }}{% endif %} · {{ e.received_at }}</div>
  {% if e.detail %}<div>{{ e.detail }}</div>{% endif %}
  {% if e.commits %}<ul>{% for c in e.commits %}<li><code>{{ c.id }}</code> {{ c.message }}</li>{% endfor %}</ul>{% endif %}
  {% if e.url %}<div><a href="{{ e.url }}" target="_blank" rel="noreferrer">Open on GitHub ↗</a></div>{% endif %}
</div>
{% else %}
<p class="muted">No events yet. Add the webhook in GitHub (Settings → Webhooks) - GitHub sends a <b>ping</b> right away.</p>
{% endfor %}
</main></body></html>"""


def create_app(store: EventStore | None = None, secret: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = (
        5 * 1024 * 1024
    )  # GitHub payloads are capped at 25 MB; push is far smaller
    store = store or build_store()
    secret = secret if secret is not None else os.getenv("GITHUB_WEBHOOK_SECRET", "")
    if not secret:
        log.warning("GITHUB_WEBHOOK_SECRET is empty - every delivery will be rejected")

    @app.post("/github/webhook")
    def github_webhook():  # type: ignore[no-untyped-def]
        body = request.get_data(
            cache=True
        )  # raw bytes: the signature is over the exact body
        if not verify_signature(
            secret, body, request.headers.get("X-Hub-Signature-256")
        ):
            log.warning(
                "rejected delivery with a bad/missing signature from %s",
                request.remote_addr,
            )
            return jsonify(error="invalid signature"), 401
        event = request.headers.get("X-GitHub-Event", "unknown")
        delivery = (
            request.headers.get("X-GitHub-Delivery") or hashlib.sha256(body).hexdigest()
        )
        payload = request.get_json(silent=True) or {}
        doc = {
            "delivery_id": delivery,
            "event": event,
            "received_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
            **summarize(event, payload),
        }
        stored = store.add(doc)
        log.info("%s %s (%s)", "stored" if stored else "duplicate", event, doc["title"])
        return jsonify(ok=True, event=event, duplicate=not stored), 202

    @app.get("/")
    def dashboard():  # type: ignore[no-untyped-def]
        return render_template_string(
            DASHBOARD, events=store.recent(50), store=store.name
        )  # autoescaped

    @app.get("/api/events")
    def events_json():  # type: ignore[no-untyped-def]
        return jsonify(store.recent(50))

    @app.get("/health")
    def health():  # type: ignore[no-untyped-def]
        return jsonify(status="ok", store=store.name)

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
