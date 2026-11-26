from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.database.session import get_session
from app.models.user import Address
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenPair, UserOut
from app.schemas.commerce import AddressIn, AddressOut
from app.security.dependencies import get_principal, rate_limit
from app.security.permissions import Principal
from app.services.auth_service import AuthService, user_out

router = APIRouter(prefix="/auth", tags=["Authentication"])
login_limit = Depends(rate_limit("auth", "chat_rate_limit_per_minute"))


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED, dependencies=[login_limit])
async def register(req: RegisterRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    svc = AuthService(session, get_settings())
    return svc.tokens(await svc.register(req))


@router.post("/login", response_model=TokenPair, dependencies=[login_limit])
async def login(req: LoginRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    svc = AuthService(session, get_settings())
    return svc.tokens(await svc.login(req.email, req.password))


@router.post("/refresh", response_model=TokenPair)
async def refresh(req: RefreshRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    svc = AuthService(session, get_settings())
    return svc.tokens(await svc.refresh(req.refresh_token))


@router.get("/me", response_model=UserOut)
async def me(principal: Principal = Depends(get_principal), session: AsyncSession = Depends(get_session)) -> UserOut:
    from app.models.user import User

    user = await session.get(User, principal.user_id)
    assert user is not None
    return user_out(user)


# ---------- Address book ----------
async def _own_address(session: AsyncSession, user_id: int | None, address_id: int) -> Address:
    addr = await session.scalar(select(Address).where(Address.id == address_id, Address.user_id == user_id))
    if addr is None:
        raise NotFoundError("Address not found")
    return addr


async def _clear_default(session: AsyncSession, user_id: int | None, keep_id: int | None = None) -> None:
    stmt = update(Address).where(Address.user_id == user_id, Address.is_default.is_(True))
    if keep_id is not None:
        stmt = stmt.where(Address.id != keep_id)
    await session.execute(stmt.values(is_default=False))


async def _flush_unique(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        raise ConflictError("You already have an address with this label — pick a different label (e.g. Work, Home 2)") from e


@router.get("/me/addresses", response_model=list[AddressOut])
async def my_addresses(principal: Principal = Depends(get_principal), session: AsyncSession = Depends(get_session)) -> list[AddressOut]:
    rows = (
        await session.scalars(select(Address).where(Address.user_id == principal.user_id).order_by(Address.is_default.desc(), Address.id))
    ).all()
    return [AddressOut.model_validate(a) for a in rows]


@router.post("/me/addresses", response_model=AddressOut, status_code=201)
async def add_address(
    body: AddressIn, principal: Principal = Depends(get_principal), session: AsyncSession = Depends(get_session)
) -> AddressOut:
    data = body.model_dump()
    has_any = await session.scalar(select(Address.id).where(Address.user_id == principal.user_id).limit(1))
    if not has_any:
        data["is_default"] = True  # first address is always the default
    if data["is_default"]:
        await _clear_default(session, principal.user_id)
    addr = Address(user_id=principal.user_id, **data)
    session.add(addr)
    await _flush_unique(session)
    return AddressOut.model_validate(addr)


@router.put("/me/addresses/{address_id}", response_model=AddressOut)
async def update_address(
    address_id: int, body: AddressIn, principal: Principal = Depends(get_principal), session: AsyncSession = Depends(get_session)
) -> AddressOut:
    addr = await _own_address(session, principal.user_id, address_id)
    data = body.model_dump()
    if addr.is_default and not data["is_default"]:
        data["is_default"] = True  # can't un-default; set another address as default instead
    for k, v in data.items():
        setattr(addr, k, v)
    if data["is_default"]:
        await _clear_default(session, principal.user_id, keep_id=addr.id)
    await _flush_unique(session)
    return AddressOut.model_validate(addr)


@router.post("/me/addresses/{address_id}/default", response_model=AddressOut)
async def set_default_address(
    address_id: int, principal: Principal = Depends(get_principal), session: AsyncSession = Depends(get_session)
) -> AddressOut:
    addr = await _own_address(session, principal.user_id, address_id)
    await _clear_default(session, principal.user_id, keep_id=addr.id)
    addr.is_default = True
    await session.flush()
    return AddressOut.model_validate(addr)


@router.delete("/me/addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_address(
    address_id: int, principal: Principal = Depends(get_principal), session: AsyncSession = Depends(get_session)
) -> None:
    addr = await _own_address(session, principal.user_id, address_id)
    was_default = addr.is_default
    await session.delete(addr)  # past orders keep their own address snapshot, so history is unaffected
    await session.flush()
    if was_default:
        nxt = await session.scalar(select(Address).where(Address.user_id == principal.user_id).order_by(Address.id).limit(1))
        if nxt is not None:
            nxt.is_default = True
            await session.flush()
