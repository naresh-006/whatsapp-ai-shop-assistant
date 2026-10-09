"""Billing models and exception types."""

from pydantic import BaseModel, Field
from typing import Any


class BillingError(Exception):
    """Base class for billing calculation exceptions."""
    pass


class InvalidUnitError(BillingError):
    """Raised when an invalid or unsupported unit is provided for a product."""
    pass


class InvalidQuantityError(BillingError):
    """Raised when quantity is non-positive or invalid."""
    pass


class BillItemInput(BaseModel):
    """Input payload representing a single item in an order."""
    product_id: str = Field(..., description="Canonical product ID or recognized query name")
    quantity: float = Field(..., gt=0, description="Order quantity (must be > 0)")
    unit: str = Field(..., min_length=1, description="Unit of sale (e.g. piece, packet, dozen, saram, bundle)")
    is_wholesale: bool = Field(default=False, description="Whether to apply wholesale rate if available")


class CalculatedBillItem(BaseModel):
    """Authoritative calculated item with snapshot rates and arithmetic breakdown."""
    product_id: str
    product_name: str
    quantity: float
    unit: str
    rate: float = Field(..., description="Authoritative unit rate applied")
    amount: float = Field(..., description="Exact calculated amount: quantity * rate")
    conversion_applied: str | None = Field(default=None, description="Conversion explanation if unit converted")
    base_quantity: float = Field(..., description="Equivalent quantity in product base units")
    is_wholesale: bool = Field(default=False, description="Whether item was charged at wholesale rate")


class BillCalculationRequest(BaseModel):
    """Request payload to calculate a full bill deterministically."""
    customer_name: str | None = Field(default=None, description="Customer name if available")
    items: list[BillItemInput] = Field(..., min_length=1, description="List of items to calculate")
    is_wholesale: bool = Field(default=False, description="Default wholesale pricing mode for whole order")


class CalculatedBill(BaseModel):
    """Complete calculated bill with deterministic totals."""
    customer_name: str | None = None
    items: list[CalculatedBillItem]
    total_items: int
    subtotal: float
    grand_total: float
    is_wholesale: bool = Field(default=False, description="Whether bill used wholesale pricing")
    notes: list[str] = Field(default_factory=list)
