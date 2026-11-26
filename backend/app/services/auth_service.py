from __future__ import annotations

from datetime import timedelta
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.enums import Role
from app.core.exceptions import AuthenticationError, ConflictError
from app.models.commerce import ShoppingCart
from app.models.user import CustomerProfile, User
from app.models.user import Role as RoleModel
from app.schemas.auth import RegisterRequest, TokenPair, UserOut
from app.security.passwords import hash_password, verify_password
from app.security.permissions import Principal
from app.security.tokens import create_token, decode_token
from app.services.audit_service import audit


@lru_cache(maxsize=1)
def _dummy_hash() -> str:  # real bcrypt hash so unknown-email logins cost the same as wrong-password logins
    return hash_password("timing-equaliser-not-a-password")


def principal_for(user: User) -> Principal:
    return Principal(user_id=user.id, email=user.email, roles=frozenset(Role(r) for r in user.role_names), name=user.full_name)


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id, email=user.email, full_name=user.full_name, roles=user.role_names, is_active=user.is_active, created_at=user.created_at
    )


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session, self.s = session, settings

    def tokens(self, user: User) -> TokenPair:
        s = self.s
        roles = user.role_names
        access = create_token(
            subject=str(user.id),
            roles=roles,
            secret=s.jwt_secret,
            algorithm=s.jwt_algorithm,  # type: ignore[attr-defined]
            expires_in=timedelta(minutes=s.access_token_minutes),
            token_type="access",
        )  # type: ignore[attr-defined]
        refresh = create_token(
            subject=str(user.id),
            roles=roles,
            secret=s.jwt_secret,
            algorithm=s.jwt_algorithm,  # type: ignore[attr-defined]
            expires_in=timedelta(days=s.refresh_token_days),
            token_type="refresh",
        )  # type: ignore[attr-defined]
        return TokenPair(access_token=access, refresh_token=refresh, expires_in=s.access_token_minutes * 60)  # type: ignore[attr-defined]

    async def register(self, req: RegisterRequest) -> User:
        email = req.email.lower()
        if await self.session.scalar(select(User.id).where(User.email == email)):
            raise ConflictError("An account with this email already exists")
        role = await self.session.scalar(select(RoleModel).where(RoleModel.name == Role.CUSTOMER))
        user = User(
            email=email,
            password_hash=hash_password(req.password),
            full_name=req.full_name,
            phone=req.phone,
            roles=[role] if role else [],
            addresses=[],
        )
        user.profile = CustomerProfile(preferred_categories=[], budget_hints={})
        self.session.add(user)
        await self.session.flush()
        self.session.add(ShoppingCart(user_id=user.id))
        await audit(self.session, principal_for(user), "auth.register", "user", user.id)
        return user

    async def login(self, email: str, password: str) -> User:
        user = await self.session.scalar(select(User).where(User.email == email.lower()))
        if user is None:
            verify_password(password, _dummy_hash())  # equalise timing to avoid account enumeration
            raise AuthenticationError("Invalid email or password")
        if not user.is_active or not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid email or password")
        await audit(self.session, principal_for(user), "auth.login", "user", user.id)
        return user

    async def refresh(self, refresh_token: str) -> User:
        payload = decode_token(refresh_token, secret=self.s.jwt_secret, algorithm=self.s.jwt_algorithm, expected_type="refresh")  # type: ignore[attr-defined]
        user = await self.session.get(User, int(payload["sub"]))
        if user is None or not user.is_active:
            raise AuthenticationError("Account disabled")
        return user
