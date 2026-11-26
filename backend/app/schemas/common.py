from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class DTO(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class Page(DTO, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class PageParams(BaseModel):
    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


class Message(DTO):
    message: str
