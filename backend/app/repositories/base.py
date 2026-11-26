from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.database.base import Base

M = TypeVar("M", bound=Base)


class Repository(Generic[M]):
    model: type[M]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, id_: Any) -> M | None:
        return await self.session.get(self.model, id_)

    async def get_or_404(self, id_: Any, what: str | None = None) -> M:
        obj = await self.get(id_)
        if obj is None:
            raise NotFoundError(f"{what or self.model.__name__} {id_} not found")
        return obj

    async def add(self, obj: M) -> M:
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def count(self) -> int:
        return int(await self.session.scalar(select(func.count()).select_from(self.model)) or 0)

    async def page(self, offset: int, limit: int, *order_by: Any) -> list[M]:
        stmt = select(self.model).order_by(*order_by).offset(offset).limit(limit)
        return list((await self.session.scalars(stmt)).all())
