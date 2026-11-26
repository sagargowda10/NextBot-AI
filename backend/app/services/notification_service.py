from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.state import AppState
from app.models.platform import Notification
from app.models.user import User
from app.schemas.platform import NotificationOut


def notification_out(n: Notification) -> NotificationOut:
    return NotificationOut(
        id=n.id,
        user_id=n.user_id,
        channel=n.channel,
        template=n.template,
        recipient=n.recipient,
        subject=n.subject,
        body=n.body,
        status=n.status,
        created_at=n.created_at,
    )


class NotificationService:
    def __init__(self, session: AsyncSession, state: AppState) -> None:
        self.session, self.state = session, state

    async def record(
        self,
        *,
        user_id: int | None,
        channel: str,
        template: str,
        recipient: str,
        subject: str | None,
        body: str,
        status: str,
        meta: dict[str, Any] | None = None,
    ) -> NotificationOut:
        n = Notification(
            user_id=user_id,
            channel=channel,
            template=template,
            recipient=recipient,
            subject=subject,
            body=body,
            status=status,
            meta=meta or {},
        )
        self.session.add(n)
        await self.session.flush()
        return notification_out(n)

    async def recipient_for(self, user_id: int, channel: str) -> str | None:
        user = await self.session.get(User, user_id)
        if user is None:
            return None
        if channel == "EMAIL":
            return user.email
        if channel == "WHATSAPP" and user.profile is not None and user.profile.whatsapp_opt_in:
            return user.phone
        return None

    async def already_sent(self, user_id: int, channel: str, dedupe_key: str) -> bool:
        rows = (
            await self.session.scalars(
                select(Notification)
                .where(Notification.user_id == user_id, Notification.channel == channel)
                .order_by(Notification.id.desc())
                .limit(50)
            )
        ).all()
        return any((n.meta or {}).get("dedupe_key") == dedupe_key for n in rows)

    async def for_user(self, user_id: int | None, limit: int = 50) -> list[NotificationOut]:
        stmt = select(Notification).order_by(Notification.id.desc()).limit(limit)
        if user_id is not None:
            stmt = stmt.where(Notification.user_id == user_id)
        return [notification_out(n) for n in (await self.session.scalars(stmt)).all()]
