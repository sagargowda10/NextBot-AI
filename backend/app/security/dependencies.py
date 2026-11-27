"""FastAPI security dependencies — centralised authentication and authorisation."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import Role
from app.core.exceptions import AuthenticationError, PermissionDenied, RateLimited
from app.database.session import get_session
from app.models.user import User
from app.security.permissions import Principal
from app.security.tokens import decode_token

bearer = HTTPBearer(auto_error=False, description="JWT access token from /api/v1/auth/login")


async def principal_from_token(token: str, session: AsyncSession) -> Principal:
    s = get_settings()
    payload = decode_token(token, secret=s.jwt_secret, algorithm=s.jwt_algorithm, expected_type="access")
    user = await session.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise AuthenticationError("Account not found or disabled")
    # roles come from the database, not the token, so revocations apply immediately
    return Principal(user_id=user.id, email=user.email, roles=frozenset(Role(r) for r in user.role_names), name=user.full_name)


async def get_principal(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer), session: AsyncSession = Depends(get_session)
) -> Principal:
    if creds is None or creds.scheme.lower() != "bearer":
        raise AuthenticationError("Not authenticated")
    return await principal_from_token(creds.credentials, session)


def require(*permissions: str) -> Callable[..., Awaitable[Principal]]:
    async def dep(principal: Principal = Depends(get_principal)) -> Principal:
        missing = [p for p in permissions if not principal.has(p)]
        if missing:
            raise PermissionDenied("You don't have permission for this action", details={"missing": missing})
        return principal

    return dep


def require_roles(*roles: Role) -> Callable[..., Awaitable[Principal]]:
    async def dep(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.has_any_role(*roles):
            raise PermissionDenied("Insufficient role")
        return principal

    return dep


def client_ip(request: Request) -> str:
    """Caller IP. Behind the Next.js same-origin proxy every request comes from the frontend container,
    so use the first X-Forwarded-For hop the proxy adds (only used to key anonymous rate limits)."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()[:64]
    return request.client.host if request.client else "anon"


def rate_limit(bucket: str, per_minute_attr: str) -> Callable[..., Awaitable[None]]:
    """Per-user (or per-IP) fixed-window limiter backed by Redis (or memory in demo mode)."""

    async def dep(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
        limit = int(getattr(get_settings(), per_minute_attr))
        who = (creds.credentials[-16:] if creds else None) or client_ip(request)
        n = await request.app.state.nb.cache.incr_window(f"rl:{bucket}:{who}", 60)
        if n > limit:
            raise RateLimited(f"Too many requests — limit is {limit}/minute")

    return dep
