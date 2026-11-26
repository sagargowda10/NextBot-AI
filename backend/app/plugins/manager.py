"""Plugin Manager + Plugin Registry.

The single entry point for invoking business capabilities. `execute()` performs, in order:
  1. lookup  2. status check  3. action lookup  4. input validation (Pydantic)
  5. user authorization (principal permissions)  6. agent permission (allow-list)
  7. execution with timeout  8. execution metadata recording  9. structured result
and converts every failure into a `PluginResult(success=False, ...)` instead of raising.
"""

from __future__ import annotations

import asyncio
import builtins
import time
import uuid
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import ValidationError

from app.core.enums import PluginStatus
from app.core.exceptions import DomainError, NotFoundError, PermissionDenied, ValidationFailed
from app.core.logging import get_logger
from app.plugins.base import BasePlugin, HealthStatus, PluginContext, PluginResult

log = get_logger("plugins")

CIRCUIT_BREAKER_THRESHOLD = 5  # consecutive unexpected errors → FAILED


@dataclass
class PluginStats:
    executions: int = 0
    successes: int = 0
    failures: int = 0
    total_duration_ms: float = 0.0
    last_execution_at: datetime | None = None
    last_error: str | None = None
    consecutive_errors: int = 0

    @property
    def avg_duration_ms(self) -> float:
        return round(self.total_duration_ms / self.executions, 2) if self.executions else 0.0


@dataclass
class ExecutionRecord:
    id: str
    plugin_id: str
    action: str
    agent: str | None
    user_id: int | None
    success: bool
    duration_ms: float
    error: str | None
    started_at: datetime
    conversation_id: int | None = None


@dataclass
class PluginRegistration:
    plugin: BasePlugin
    status: PluginStatus
    registered_at: datetime
    stats: PluginStats = field(default_factory=PluginStats)
    health: HealthStatus | None = None
    desired_enabled: bool = True


class ExecutionSink(Protocol):
    """Persists execution records (DB in production, list in tests)."""

    async def record(self, rec: ExecutionRecord) -> None: ...


class PluginManager:
    def __init__(self, *, sink: ExecutionSink | None = None, default_timeout_s: float = 10.0, history: int = 500):
        self._plugins: dict[str, PluginRegistration] = {}
        self._history: deque[ExecutionRecord] = deque(maxlen=history)
        self._sink = sink
        self._timeout = default_timeout_s

    # ------------------------------------------------------------------ registry
    def register(self, plugin: BasePlugin, *, enabled: bool = True) -> None:
        pid = plugin.get_plugin_id()
        if not pid or pid in self._plugins:
            raise ValueError(f"Plugin id {pid!r} is empty or already registered")
        self._plugins[pid] = PluginRegistration(
            plugin=plugin, status=PluginStatus.DISABLED, registered_at=datetime.now(UTC), desired_enabled=enabled
        )

    def register_many(self, plugins: Iterable[BasePlugin]) -> None:
        for p in plugins:
            self.register(p)

    def set_sink(self, sink: ExecutionSink | None) -> None:
        self._sink = sink

    def ids(self) -> list[str]:
        return list(self._plugins)

    def get(self, plugin_id: str) -> PluginRegistration:
        try:
            return self._plugins[plugin_id]
        except KeyError as exc:
            raise NotFoundError(f"Plugin {plugin_id!r} not found") from exc

    def list(self) -> list[PluginRegistration]:
        return list(self._plugins.values())

    def executions(self, plugin_id: str | None = None, limit: int = 50, failed_only: bool = False) -> builtins.list[ExecutionRecord]:
        recs = [r for r in reversed(self._history) if (plugin_id is None or r.plugin_id == plugin_id)]
        if failed_only:
            recs = [r for r in recs if not r.success]
        return recs[:limit]

    def summary(self) -> dict[str, Any]:
        regs = self.list()
        count = lambda s: sum(1 for r in regs if r.status == s)  # noqa: E731
        return {
            "total": len(regs),
            "enabled": count(PluginStatus.ENABLED),
            "disabled": count(PluginStatus.DISABLED),
            "failed": count(PluginStatus.FAILED),
            "initializing": count(PluginStatus.INITIALIZING),
            "executions": sum(r.stats.executions for r in regs),
            "successes": sum(r.stats.successes for r in regs),
            "failures": sum(r.stats.failures for r in regs),
        }

    # ------------------------------------------------------------------ lifecycle
    async def initialize_all(self, configs: dict[str, dict[str, Any]] | None = None) -> None:
        configs = configs or {}
        for pid, reg in self._plugins.items():
            if not reg.desired_enabled:
                reg.status = PluginStatus.DISABLED
                continue
            await self._initialize(pid, configs.get(pid))

    async def _initialize(self, plugin_id: str, config: dict[str, Any] | None = None) -> None:
        reg = self.get(plugin_id)
        reg.status = PluginStatus.INITIALIZING
        try:
            await reg.plugin.initialize(config if config is not None else reg.plugin.config)
            reg.health = await reg.plugin.health_check()
            reg.status = PluginStatus.ENABLED
            reg.stats.consecutive_errors = 0
            log.info("plugin_enabled", extra={"plugin": plugin_id, "mode": reg.plugin.mode})
        except Exception as exc:  # initialization must never crash the app
            reg.status = PluginStatus.FAILED
            details = getattr(exc, "details", None) or {}
            reg.stats.last_error = f"{exc}: {'; '.join(details['errors'])}" if details.get("errors") else str(exc)
            log.error("plugin_init_failed", extra={"plugin": plugin_id, "error": str(exc)})

    async def enable(self, plugin_id: str) -> PluginRegistration:
        reg = self.get(plugin_id)
        reg.desired_enabled = True
        await self._initialize(plugin_id)
        return reg

    async def disable(self, plugin_id: str) -> PluginRegistration:
        reg = self.get(plugin_id)
        reg.desired_enabled = False
        try:
            await reg.plugin.shutdown()
        finally:
            reg.status = PluginStatus.DISABLED
        return reg

    async def configure(self, plugin_id: str, values: dict[str, Any]) -> PluginRegistration:
        reg = self.get(plugin_id)
        forbidden = set(values) & set(reg.plugin.secret_keys)
        if forbidden:
            raise ValidationFailed("Secrets can only be set through environment variables", details={"keys": sorted(forbidden)})
        unknown = set(values) - set(reg.plugin.default_config)
        if unknown:
            raise ValidationFailed("Unknown configuration keys", details={"keys": sorted(unknown)})
        merged = {**reg.plugin.config, **values}
        errors = reg.plugin.validate_configuration(merged)
        if errors:
            raise ValidationFailed("Invalid configuration", details={"errors": errors})
        if reg.status == PluginStatus.ENABLED:
            await self._initialize(plugin_id, merged)
        else:
            reg.plugin.config = merged
        return reg

    async def health(self, plugin_id: str) -> HealthStatus:
        reg = self.get(plugin_id)
        if reg.status != PluginStatus.ENABLED:
            reg.health = HealthStatus(healthy=False, detail=f"Plugin is {reg.status.value}")
            return reg.health
        try:
            reg.health = await reg.plugin.health_check()
        except Exception as exc:
            reg.health = HealthStatus(healthy=False, detail=str(exc))
        return reg.health

    async def shutdown_all(self) -> None:
        for reg in self._plugins.values():
            try:
                await reg.plugin.shutdown()
            except Exception:  # pragma: no cover
                log.exception("plugin_shutdown_failed")

    @staticmethod
    def masked_config(reg: PluginRegistration) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in reg.plugin.config.items():
            out[k] = ("********" if v else None) if k in reg.plugin.secret_keys else v
        return out

    # ------------------------------------------------------------------ execution
    async def execute(
        self,
        plugin_id: str,
        action: str,
        payload: dict[str, Any] | None,
        ctx: PluginContext,
        *,
        timeout_s: float | None = None,
    ) -> PluginResult:
        started = datetime.now(UTC)
        t0 = time.perf_counter()
        exec_id = uuid.uuid4().hex

        def fail(code: str, message: str, *, count: bool = True, unexpected: bool = False) -> PluginResult:
            duration = (time.perf_counter() - t0) * 1000
            reg = self._plugins.get(plugin_id)
            if reg is not None and count:
                self._account(reg, success=False, duration=duration, error=message, unexpected=unexpected)
            self._remember(exec_id, plugin_id, action, ctx, False, duration, message, started)
            return PluginResult(
                success=False,
                plugin_id=plugin_id,
                action=action,
                error=message,
                error_code=code,
                duration_ms=round(duration, 2),
                execution_id=exec_id,
            )

        # 1. lookup
        reg = self._plugins.get(plugin_id)
        if reg is None:
            return fail("plugin_not_found", f"Unknown plugin {plugin_id!r}", count=False)
        # 2. status
        if reg.status != PluginStatus.ENABLED:
            return fail("plugin_unavailable", f"{reg.plugin.get_name()} is {reg.status.value}", count=False)
        # 3. action
        act = reg.plugin.actions().get(action)
        if act is None:
            return fail("action_not_found", f"{plugin_id} has no action {action!r}", count=False)
        # 4. validation
        try:
            model = act.input_model.model_validate(payload or {})
        except ValidationError as exc:
            return fail("invalid_input", "Invalid input: " + "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()))
        # 5. user authorization
        if not ctx.principal.has(act.permission):
            return fail("forbidden", f"You don't have permission to {plugin_id}.{action}")
        # 6. agent permission
        if ctx.agent_allowed is not None and not (f"{plugin_id}.{action}" in ctx.agent_allowed or f"{plugin_id}.*" in ctx.agent_allowed):
            return fail("agent_forbidden", f"Agent {ctx.agent} may not call {plugin_id}.{action}")
        # 7. execute
        try:
            data = await asyncio.wait_for(reg.plugin.execute(action, model, ctx), timeout_s or self._timeout)
        except TimeoutError:
            return fail("timeout", f"{plugin_id}.{action} timed out", unexpected=True)
        except PermissionDenied as exc:
            return fail(exc.code, exc.message)
        except DomainError as exc:  # expected business outcome (out of stock, not found, ...)
            return fail(exc.code, exc.message)
        except Exception as exc:
            log.exception("plugin_execution_error", extra={"plugin": plugin_id, "action": action})
            return fail("plugin_error", f"{plugin_id}.{action} failed: {type(exc).__name__}", unexpected=True)
        # 8. record
        duration = (time.perf_counter() - t0) * 1000
        self._account(reg, success=True, duration=duration, error=None, unexpected=False)
        self._remember(exec_id, plugin_id, action, ctx, True, duration, None, started)
        # 9. structured output
        if hasattr(data, "model_dump"):
            data = data.model_dump(mode="json")
        elif isinstance(data, list):
            data = [d.model_dump(mode="json") if hasattr(d, "model_dump") else d for d in data]
        return PluginResult(
            success=True, plugin_id=plugin_id, action=action, data=data, duration_ms=round(duration, 2), execution_id=exec_id
        )

    def _account(self, reg: PluginRegistration, *, success: bool, duration: float, error: str | None, unexpected: bool) -> None:
        s = reg.stats
        s.executions += 1
        s.total_duration_ms += duration
        s.last_execution_at = datetime.now(UTC)
        if success:
            s.successes += 1
            s.consecutive_errors = 0
        else:
            s.failures += 1
            s.last_error = error
            if unexpected:
                s.consecutive_errors += 1
                if s.consecutive_errors >= CIRCUIT_BREAKER_THRESHOLD:
                    reg.status = PluginStatus.FAILED
                    log.error("plugin_circuit_open", extra={"plugin": reg.plugin.plugin_id})

    def _remember(
        self,
        exec_id: str,
        plugin_id: str,
        action: str,
        ctx: PluginContext,
        success: bool,
        duration: float,
        error: str | None,
        started: datetime,
    ) -> None:
        rec = ExecutionRecord(
            exec_id, plugin_id, action, ctx.agent, ctx.principal.user_id, success, round(duration, 2), error, started, ctx.conversation_id
        )
        self._history.append(rec)
        if self._sink is not None:
            try:
                asyncio.get_running_loop().create_task(self._safe_sink(rec))
            except RuntimeError:  # pragma: no cover - no loop
                pass

    async def _safe_sink(self, rec: ExecutionRecord) -> None:
        try:
            await self._sink.record(rec)  # type: ignore[union-attr]
        except Exception:  # pragma: no cover
            log.warning("plugin_execution_persist_failed", extra={"plugin": rec.plugin_id})
