import asyncio
import inspect

import pytest
from pydantic import BaseModel

from app.core.enums import PluginStatus
from app.core.exceptions import ValidationFailed
from app.plugins.base import BasePlugin, PluginContext, action
from app.plugins.manager import CIRCUIT_BREAKER_THRESHOLD, PluginManager
from app.plugins.registry import builtin_plugins
from tests.fakes import ADMIN, CUSTOMER, build_services

pytestmark = pytest.mark.anyio

REQUIRED = (
    "get_plugin_id",
    "get_name",
    "get_version",
    "get_description",
    "initialize",
    "execute",
    "validate_configuration",
    "health_check",
    "shutdown",
)


class EchoIn(BaseModel):
    text: str
    delay: float = 0.0
    explode: bool = False


class EchoPlugin(BasePlugin):
    plugin_id, name, description = "echo", "Echo", "test plugin"
    default_config = {"prefix": ">", "api_secret": None}
    secret_keys = frozenset({"api_secret"})

    @action("say", EchoIn, "catalog:read")
    async def say(self, p: EchoIn, ctx: PluginContext) -> dict:
        await asyncio.sleep(p.delay)
        if p.explode:
            raise RuntimeError("boom")
        return {"out": f"{self.config['prefix']}{p.text}"}

    @action("admin_only", EchoIn, "analytics:read")
    async def admin_only(self, p: EchoIn, ctx: PluginContext) -> dict:
        return {"ok": True}


def ctx(principal=CUSTOMER, agent=None, allowed=None) -> PluginContext:
    services, _ = build_services()
    return PluginContext(principal=principal, services=services, agent=agent, agent_allowed=allowed)


async def manager() -> PluginManager:
    pm = PluginManager(default_timeout_s=0.2)
    pm.register(EchoPlugin())
    await pm.initialize_all()
    return pm


def test_exactly_twelve_builtin_plugins_with_full_contract():
    plugins = builtin_plugins()
    assert len(plugins) == 12 and len({p.get_plugin_id() for p in plugins}) == 12
    for p in plugins:
        for m in REQUIRED:
            assert callable(getattr(p, m)), (p.plugin_id, m)
        assert p.get_name() and p.get_version() and p.get_description() and p.actions()
        for a in p.actions().values():
            assert inspect.iscoroutinefunction(a.handler) and ":" in a.permission


async def test_all_builtins_initialize_in_demo_mode():
    pm = PluginManager()
    pm.register_many(builtin_plugins())
    await pm.initialize_all()
    assert pm.summary()["enabled"] == 12 and pm.summary()["failed"] == 0
    modes = {r.plugin.plugin_id: r.plugin.mode for r in pm.list()}
    assert modes["payment"] == modes["whatsapp"] == modes["email"] == modes["shipping"] == "mock"


async def test_successful_execution_is_recorded():
    pm = await manager()
    res = await pm.execute("echo", "say", {"text": "hi"}, ctx())
    assert res.success and res.data == {"out": ">hi"} and res.execution_id
    reg = pm.get("echo")
    assert reg.stats.executions == 1 and reg.stats.successes == 1 and reg.stats.last_execution_at
    assert pm.executions("echo")[0].success


async def test_validation_and_authorization_failures():
    pm = await manager()
    bad = await pm.execute("echo", "say", {"nope": 1}, ctx())
    assert not bad.success and bad.error_code == "invalid_input"
    forbidden = await pm.execute("echo", "admin_only", {"text": "x"}, ctx(CUSTOMER))
    assert forbidden.error_code == "forbidden"
    assert (await pm.execute("echo", "admin_only", {"text": "x"}, ctx(ADMIN))).success


async def test_agent_allow_list_enforced():
    pm = await manager()
    denied = await pm.execute("echo", "say", {"text": "x"}, ctx(agent="shopping", allowed=frozenset({"other.*"})))
    assert denied.error_code == "agent_forbidden"
    ok = await pm.execute("echo", "say", {"text": "x"}, ctx(agent="shopping", allowed=frozenset({"echo.say"})))
    assert ok.success


async def test_disabled_and_unknown_plugins():
    pm = await manager()
    await pm.disable("echo")
    res = await pm.execute("echo", "say", {"text": "x"}, ctx())
    assert res.error_code == "plugin_unavailable"
    assert (await pm.execute("nope", "say", {}, ctx())).error_code == "plugin_not_found"
    await pm.enable("echo")
    assert (await pm.execute("echo", "say", {"text": "x"}, ctx())).success


async def test_timeout_and_circuit_breaker():
    pm = await manager()
    t = await pm.execute("echo", "say", {"text": "x", "delay": 1}, ctx())
    assert t.error_code == "timeout"
    for _ in range(CIRCUIT_BREAKER_THRESHOLD):
        r = await pm.execute("echo", "say", {"text": "x", "explode": True}, ctx())
        assert r.error_code in ("plugin_error", "plugin_unavailable")
    assert pm.get("echo").status == PluginStatus.FAILED
    assert len(pm.executions("echo", failed_only=True)) >= CIRCUIT_BREAKER_THRESHOLD


async def test_configuration_secrets_env_only_and_masked():
    pm = await manager()
    with pytest.raises(ValidationFailed):
        await pm.configure("echo", {"api_secret": "leak"})
    with pytest.raises(ValidationFailed):
        await pm.configure("echo", {"unknown": 1})
    await pm.configure("echo", {"prefix": "#"})
    assert (await pm.execute("echo", "say", {"text": "x"}, ctx())).data == {"out": "#x"}
    reg = pm.get("echo")
    reg.plugin.config["api_secret"] = "from-env"
    assert pm.masked_config(reg)["api_secret"] == "********"


async def test_failed_initialization_marks_plugin_failed():
    pm = PluginManager()
    from app.plugins.builtin.payment import PaymentPlugin

    pm.register(PaymentPlugin())
    await pm.initialize_all({"payment": {"provider": "razorpay"}})  # no credentials
    assert pm.get("payment").status == PluginStatus.FAILED
    assert "razorpay requires" in (pm.get("payment").stats.last_error or "")
