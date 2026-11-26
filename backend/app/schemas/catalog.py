from __future__ import annotations

from decimal import Decimal

from pydantic import Field, field_validator

from app.schemas.common import DTO


class ProductFilter(DTO):
    query: str | None = Field(None, max_length=200)
    category: str | None = Field(None, max_length=80)
    brand: str | None = Field(None, max_length=80)
    min_price: Decimal | None = Field(None, ge=0)
    max_price: Decimal | None = Field(None, ge=0)
    size: str | None = Field(None, max_length=20)
    colour: str | None = Field(None, max_length=30)
    in_stock_only: bool = False
    sort: str = Field("relevance", pattern="^(relevance|price_asc|price_desc|rating|newest)$")
    limit: int = Field(10, ge=1, le=50)
    offset: int = Field(0, ge=0)

    @field_validator("colour", "category", "brand", "size")
    @classmethod
    def _norm(cls, v: str | None) -> str | None:
        return v.strip().lower() if v else v


class VariantOut(DTO):
    id: int
    sku: str
    size: str | None = None
    colour: str | None = None
    price: Decimal
    stock_available: int = 0


class ProductSummary(DTO):
    id: int
    name: str
    slug: str
    brand: str
    category: str
    price: Decimal
    mrp: Decimal
    discount_percent: int = 0
    rating: float = 0.0
    image_url: str | None = None
    in_stock: bool = True
    variants: list[VariantOut] = []
    score: float | None = None  # relevance / similarity score when searched


class ProductDetail(ProductSummary):
    description: str = ""
    specifications: dict[str, str] = {}
    images: list[str] = []
    review_count: int = 0


class ProductCreate(DTO):
    name: str = Field(min_length=2, max_length=200)
    brand_id: int
    category_id: int
    description: str = ""
    price: Decimal = Field(gt=0)
    mrp: Decimal = Field(gt=0)
    specifications: dict[str, str] = {}
    image_url: str | None = None
    variants: list[VariantCreate] = []


class VariantCreate(DTO):
    sku: str = Field(min_length=3, max_length=64)
    size: str | None = None
    colour: str | None = None
    price: Decimal | None = None
    initial_stock: int = Field(0, ge=0)


class ProductUpdate(DTO):
    name: str | None = None
    description: str | None = None
    price: Decimal | None = Field(None, gt=0)
    mrp: Decimal | None = Field(None, gt=0)
    is_active: bool | None = None
    specifications: dict[str, str] | None = None


class CategoryOut(DTO):
    id: int
    name: str
    slug: str


class BrandOut(DTO):
    id: int
    name: str
    slug: str


ProductCreate.model_rebuild()
