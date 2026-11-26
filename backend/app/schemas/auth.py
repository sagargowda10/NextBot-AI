from __future__ import annotations

from datetime import datetime

from pydantic import EmailStr, Field

from app.schemas.common import DTO


# ---------- Auth ----------
class RegisterRequest(DTO):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=120)
    phone: str | None = Field(None, pattern=r"^\+?[0-9]{10,13}$")


class LoginRequest(DTO):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(DTO):
    refresh_token: str


class TokenPair(DTO):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(DTO):
    id: int
    email: str
    full_name: str
    roles: list[str]
    is_active: bool = True
    created_at: datetime | None = None
