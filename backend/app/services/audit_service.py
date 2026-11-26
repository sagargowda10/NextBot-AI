from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import redact
from app.models.platform import AuditLog
from app.security.permissions import Principal


async def audit(
    session: AsyncSession,
    principal: Principal | None,
    action: str,
    resource_type: str,
    resource_id: Any,
    details: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    session.add(
        AuditLog(
            actor_id=principal.user_id if principal else None,
            actor_email=principal.email if principal else None,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            details=redact(details or {}),
            ip=ip,
        )
    )
