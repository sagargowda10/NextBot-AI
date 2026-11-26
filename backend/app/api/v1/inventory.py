from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_state, page_params
from app.core.state import AppState
from app.database.session import get_session
from app.schemas.commerce import InventoryAdjust, InventoryAdjustResult, StockLevel
from app.schemas.common import PageParams
from app.security.dependencies import require
from app.security.permissions import Principal
from app.services.inventory_service import InventoryService

router = APIRouter(prefix="/inventory", tags=["Inventory"])


def svc(session: AsyncSession = Depends(get_session), state: AppState = Depends(get_state)) -> InventoryService:
    return InventoryService(session, state)


@router.get("", response_model=list[StockLevel], dependencies=[Depends(require("inventory:read"))])
async def list_inventory(
    low_only: bool = False, p: PageParams = Depends(page_params), s: InventoryService = Depends(svc)
) -> list[StockLevel]:
    return await s.low_stock(s.threshold) if low_only else await s.all_levels(p.offset, p.size)


@router.get("/product/{product_id}", response_model=list[StockLevel])
async def product_inventory(product_id: int, s: InventoryService = Depends(svc)) -> list[StockLevel]:
    return await s.for_products([product_id])


@router.put("/{inventory_id}", response_model=InventoryAdjustResult)
async def adjust(
    inventory_id: int, body: InventoryAdjust, principal: Principal = Depends(require("inventory:write")), s: InventoryService = Depends(svc)
) -> InventoryAdjustResult:
    """Apply a stock delta. Adjustments ≥ INVENTORY_ADJUSTMENT_APPROVAL_UNITS create an approval request instead."""
    return await s.adjust(principal, inventory_id, body.delta, body.reason)
