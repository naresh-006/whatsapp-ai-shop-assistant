"""Sale models for storing immutable confirmed transaction records."""

from datetime import datetime, timezone
from typing import Any
import uuid
from pydantic import BaseModel, Field


class SaleItemSnapshot(BaseModel):
    """
    Permanent snapshot of an item sold at a specific point in time.
    Even if the product master changes prices tomorrow, this snapshot remains immutable.
    """
    product_id: str
    product_name_snapshot: str = Field(..., description="Canonical product name captured at sale time")
    quantity: float
    unit: str
    rate: float = Field(..., description="Authoritative rate captured at sale time")
    amount: float = Field(..., description="Line amount: quantity * rate")
    conversion_applied: str | None = None
    base_quantity: float


class Sale(BaseModel):
    """Authoritative recorded sale stored permanently in MongoDB."""
    sale_id: str = Field(default_factory=lambda: f"SALE-{uuid.uuid4().hex[:8].upper()}")
    invoice_number: str = Field(..., description="Human-readable sequential invoice ID (e.g. INV-001)")
    order_id: str | None = Field(default=None, description="Original conversational draft order ID")
    customer_name: str | None = Field(default="Walking Customer")
    customer_phone: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = Field(default="Mother", description="Operator who recorded the sale")
    items: list[SaleItemSnapshot]
    subtotal: float
    total: float
    status: str = Field(default="confirmed", description="Sale status (confirmed, cancelled, refunded)")
    payment_method: str = Field(default="cash", description="cash, upi, credit")
    metadata: dict[str, Any] = Field(default_factory=dict)


class DailySalesSummary(BaseModel):
    """Summary of daily sales business activity for Father."""
    date: str
    total_sales: float = Field(..., description="Total sales in rupees")
    total_bills: int = Field(..., description="Count of confirmed invoices")
    total_customers: int = Field(..., description="Unique customer count")
    customer_breakdown: list[dict[str, Any]] = Field(default_factory=list)
    product_breakdown: list[dict[str, Any]] = Field(default_factory=list)
