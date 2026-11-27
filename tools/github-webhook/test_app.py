import hashlib
import hmac
import json

import pytest

from app import MemoryStore, create_app, verify_signature

SECRET = "test-secret"


def sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def client():
    store = MemoryStore()
    app = create_app(store=store, secret=SECRET)
    return app.test_client(), store


def post(
    c, event: str, payload: dict, delivery: str = "d-1", signature: str | None = None
):
    body = json.dumps(payload).encode()
    headers = {
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": delivery,
        "X-Hub-Signature-256": signature or sign(body),
    }
    return c.post(
        "/github/webhook", data=body, headers=headers, content_type="application/json"
    )


def test_signature_helper():
    assert verify_signature(SECRET, b"x", sign(b"x"))
    assert not verify_signature(SECRET, b"x", sign(b"y")) and not verify_signature(
        SECRET, b"x", None
    )
    assert not verify_signature(
        "", b"x", sign(b"x")
    )  # no secret configured -> reject everything


def test_rejects_bad_signature(client):
    c, store = client
    r = post(c, "push", {"ref": "refs/heads/main"}, signature="sha256=deadbeef")
    assert r.status_code == 401 and store.recent() == []


def test_ping_and_push_are_stored_and_shown(client):
    c, store = client
    assert (
        post(
            c,
            "ping",
            {"zen": "Keep it simple.", "repository": {"full_name": "me/NextBot-AI"}},
            "d-ping",
        ).status_code
        == 202
    )
    push = {
        "ref": "refs/heads/main",
        "repository": {"full_name": "me/NextBot-AI"},
        "pusher": {"name": "sagar"},
        "compare": "https://github.com/me/NextBot-AI/compare/a...b",
        "head_commit": {"message": "Add n8n workflow view\n\nlong body"},
        "commits": [{"id": "abcdef1234", "message": "Add n8n workflow view"}],
    }
    assert post(c, "push", push, "d-push").status_code == 202
    first = store.recent()[0]
    assert (
        first["title"] == "Push to main: 1 commit(s)"
        and first["actor"] == "sagar"
        and first["commits"][0]["id"] == "abcdef1"
    )
    html = c.get("/").get_data(as_text=True)
    assert "Push to main" in html and "Webhook connected" in html


def test_workflow_run_status_and_duplicate_delivery(client):
    c, store = client
    run = {
        "action": "completed",
        "repository": {"full_name": "me/NextBot-AI"},
        "workflow_run": {
            "name": "CI",
            "run_number": 7,
            "status": "completed",
            "conclusion": "failure",
            "head_branch": "main",
            "head_sha": "abc1234def",
            "html_url": "https://github.com/x",
            "actor": {"login": "sagar"},
        },
    }
    assert post(c, "workflow_run", run, "d-run").get_json()["duplicate"] is False
    assert (
        post(c, "workflow_run", run, "d-run").get_json()["duplicate"] is True
    )  # GitHub redelivery
    assert (
        len(store.recent()) == 1
        and store.recent()[0]["status"] == "fail"
        and "CI #7: failure" in store.recent()[0]["title"]
    )


def test_dashboard_escapes_html(client):
    c, _ = client
    post(
        c,
        "push",
        {
            "ref": "refs/heads/main",
            "head_commit": {"message": "<script>alert(1)</script>"},
            "commits": [],
        },
        "d-xss",
    )
    html = c.get("/").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
