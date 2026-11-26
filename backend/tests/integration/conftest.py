"""API integration tests: real FastAPI app + SQLAlchemy + SQLite (aiosqlite) + seeded demo data.

Skipped automatically when the web/DB stack isn't installed (e.g. a minimal environment)."""

from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

REQUIRED = ("fastapi", "sqlalchemy", "aiosqlite", "httpx", "pydantic_settings", "pwdlib", "email_validator", "prometheus_client")
MISSING = [m for m in REQUIRED if importlib.util.find_spec(m) is None]
if MISSING:
    collect_ignore_glob = ["test_*.py"]


@pytest.fixture(scope="session")
def app(tmp_path_factory: pytest.TempPathFactory) -> Any:
    from app.core.config import Settings
    from app.main import create_app

    db = Path(tmp_path_factory.mktemp("db")) / "nextbot-test.db"
    settings = Settings(
        environment="test",
        database_url=f"sqlite+aiosqlite:///{db}",
        demo_mode=True,
        ai_provider="mock",
        payment_provider="mock",
        seed_on_startup=True,
        rate_limit_per_minute=10_000,
        chat_rate_limit_per_minute=10_000,
        outbox_poll_interval_s=0.2,
        jwt_secret="integration-test-secret-0123456789abcdef",
    )
    return create_app(settings)


@pytest.fixture(scope="session")
def client(app: Any) -> Iterator[Any]:
    from fastapi.testclient import TestClient

    with TestClient(app) as c:  # runs the lifespan: create tables, seed, start plugins/agents/RAG/outbox
        yield c


def login(client: Any, email: str, password: str) -> dict[str, str]:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def asha(client: Any) -> dict[str, str]:
    return login(client, "asha@nextbot.demo", "Demo@1234")


@pytest.fixture(scope="session")
def rahul(client: Any) -> dict[str, str]:
    return login(client, "rahul@nextbot.demo", "Demo@1234")


@pytest.fixture(scope="session")
def admin(client: Any) -> dict[str, str]:
    return login(client, "admin@nextbot.demo", "Admin@1234")


@pytest.fixture(scope="session")
def inventory_mgr(client: Any) -> dict[str, str]:
    return login(client, "inventory@nextbot.demo", "Inventory@1234")
