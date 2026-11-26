"""Plugin contract.

Every business capability is a plugin: an object implementing `BasePlugin` that exposes
named, typed *actions*. Each action declares a Pydantic input model and the permission it
requires; the Plugin Manager validates input, checks permissions and records every call.
"""

from __future__ import annotations

from abc import ABC
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.core.exceptions import ValidationFailed
from app.security.permissions import Principal
from app.services.contracts import ServiceContainer


@dataclass
class PluginContext:
    """Everything a plugin may touch during one call. Built per request."""

    principal: Principal
    services: ServiceContainer
    agent: str | None = None
    # "plugin_id.action" or "plugin_id.*" entries the calling agent may use; None = direct API call
    agent_allowed: frozenset[str] | None = None
    conversation_id: int | None = None
    extras: dict[str, Any] = field(default_factory=dict)


class PluginResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool
    plugin_id: str
    action: str
    data: Any = None
    error: str | None = None
    error_code: str | None = None
    duration_ms: float = 0.0
    execution_id: str | None = None


class HealthStatus(BaseModel):
    healthy: bool
    detail: str = "ok"
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


Handler = Callable[[Any, BaseModel, PluginContext], Awaitable[Any]]


@dataclass(frozen=True)
class PluginAction:
    name: str
    description: str
    input_model: type[BaseModel]
    permission: str
    handler: Handler


F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def action(name: str, input_model: type[BaseModel], permission: str, description: str = "") -> Callable[[F], F]:
    """Mark a coroutine method as a plugin action: `async def handler(self, payload, ctx)`."""

    def decorator(fn: F) -> F:
        fn.__plugin_action__ = (name, input_model, permission, description or (fn.__doc__ or "").strip())  # type: ignore[attr-defined]
        return fn

    return decorator


class NoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BasePlugin(ABC):  # noqa: B024 - contract methods have safe defaults; subclasses override
    plugin_id: str = ""
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    requires_credentials: bool = False  # True when a real external provider needs secrets
    default_config: dict[str, Any] = {}
    secret_keys: frozenset[str] = frozenset()  # config keys that are secrets (env-only, always masked)

    def __init__(self) -> None:
        self.config: dict[str, Any] = dict(self.default_config)
        self._actions: dict[str, PluginAction] = {}
        for attr in dir(type(self)):
            fn = getattr(type(self), attr, None)
            meta = getattr(fn, "__plugin_action__", None)
            if meta:
                name, model, perm, desc = meta
                self._actions[name] = PluginAction(name, desc, model, perm, fn)  # type: ignore[arg-type]

    # ---- identity -------------------------------------------------------
    def get_plugin_id(self) -> str:
        return self.plugin_id

    def get_name(self) -> str:
        return self.name

    def get_version(self) -> str:
        return self.version

    def get_description(self) -> str:
        return self.description

    # ---- lifecycle ------------------------------------------------------
    async def initialize(self, config: dict[str, Any] | None = None) -> None:
        merged = {**self.default_config, **(config or {})}
        errors = self.validate_configuration(merged)
        if errors:
            raise ValidationFailed(f"Invalid configuration for {self.plugin_id}", details={"errors": errors})
        self.config = merged

    def validate_configuration(self, config: dict[str, Any]) -> list[str]:
        return []

    async def health_check(self) -> HealthStatus:
        return HealthStatus(healthy=True, detail="ok", checked_at=datetime.now(UTC))

    async def shutdown(self) -> None:
        return None

    @property
    def mode(self) -> str:
        """'local' for in-process implementations, 'mock' when simulating an external provider."""
        return "local"

    # ---- execution ------------------------------------------------------
    def actions(self) -> dict[str, PluginAction]:
        return self._actions

    async def execute(self, action_name: str, payload: BaseModel, ctx: PluginContext) -> Any:
        act = self._actions[action_name]
        return await act.handler(self, payload, ctx)
