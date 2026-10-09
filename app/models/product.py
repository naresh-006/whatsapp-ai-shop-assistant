"""Product schema and data models for the Product Master Database."""

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, field_validator


class UnitType(str, Enum):
    """Standard business units for the shop."""
    PIECE = "piece"
    PACKET = "packet"
    DOZEN = "dozen"
    SARAM = "saram"
    BUNDLE = "bundle"


class ConversionRule(BaseModel):
    """
    Defines how a higher-level unit (e.g., bundle, dozen, saram)
    converts to pieces or has a dedicated fixed rate.
    """
    pieces: int | None = Field(default=None, description="Number of pieces in this unit")
    rate: float | None = Field(default=None, description="Fixed authoritative price for this unit, if not calculated")
    notes: str | None = Field(default=None, description="Clarifications or restrictions on conversion")


class ProductBase(BaseModel):
    """Base schema for product records."""
    product_id: str = Field(..., description="Unique canonical identifier, e.g. KINGS, FILTER")
    canonical_name: str = Field(..., description="Official product display name")
    brand: str | None = Field(default=None, description="Brand name, e.g. ITC, Britannia")
    category: str = Field(..., description="Category, e.g. Tobacco, Biscuits, Snacks, Noodles")
    variant: str | None = Field(default=None, description="Variant name or price point, e.g. Triple Two, ₹5, ₹10")
    tamil_name: str | None = Field(default=None, description="Tamil display script name")
    aliases: list[str] = Field(default_factory=list, description="Common spoken or typed aliases in English")
    tamil_aliases: list[str] = Field(default_factory=list, description="Tamil/Tanglish phonetic aliases")
    retail_unit: UnitType = Field(..., description="Primary unit sold at retail")
    wholesale_unit: UnitType | None = Field(default=None, description="Primary unit sold at wholesale")
    base_unit: UnitType = Field(..., description="Atomic inventory unit")
    retail_rate: float = Field(..., ge=0, description="Authoritative retail rate per retail_unit")
    wholesale_rate: float | None = Field(default=None, ge=0, description="Authoritative wholesale rate")
    conversion_rules: dict[str, ConversionRule] = Field(
        default_factory=dict,
        description="Conversion logic per unit (e.g. bundle -> 20 pieces)"
    )
    stock_quantity: float = Field(default=100.0, ge=0, description="Current stock in base units")
    low_stock_threshold: float = Field(default=10.0, ge=0, description="Minimum stock before warning")
    track_stock: bool = Field(default=True, description="Whether stock auto-deduction is active")
    active: bool = Field(default=True, description="Whether product is active for sales")
    is_dummy: bool = Field(default=False, description="Flag indicating dummy/dev data vs real family rates")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional custom attributes")

    @field_validator("product_id")
    @classmethod
    def normalize_product_id(cls, v: str) -> str:
        cleaned = v.strip().upper()
        if not cleaned:
            raise ValueError("product_id cannot be empty")
        return cleaned


class ProductCreate(ProductBase):
    """Schema for creating a new product."""
    pass


class ProductUpdate(BaseModel):
    """Schema for updating product details."""
    canonical_name: str | None = None
    brand: str | None = None
    category: str | None = None
    variant: str | None = None
    tamil_name: str | None = None
    aliases: list[str] | None = None
    tamil_aliases: list[str] | None = None
    retail_unit: UnitType | None = None
    wholesale_unit: UnitType | None = None
    retail_rate: float | None = Field(default=None, ge=0)
    wholesale_rate: float | None = Field(default=None, ge=0)
    conversion_rules: dict[str, ConversionRule] | None = None
    stock_quantity: int | None = Field(default=None, ge=0)
    active: bool | None = None
    is_dummy: bool | None = None
    metadata: dict[str, Any] | None = None


class ProductInDB(ProductBase):
    """Schema representing product stored in MongoDB."""
    pass
