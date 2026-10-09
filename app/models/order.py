"""Structured Order data models representing orders before and after AI parsing and resolution."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid
from pydantic import BaseModel, Field

from app.models.billing import CalculatedBill


class OrderStatus(str, Enum):
    """Lifecycle statuses of an in-flight order."""
    DRAFT = "draft"
    NEEDS_CLARIFICATION = "needs_clarification"
    PENDING_CONFIRMATION = "pending_confirmation"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class RawOrderItem(BaseModel):
    """
    Direct structured representation of what the user/AI said,
    before exact database ID resolution.
    """
    product_text: str = Field(..., min_length=1, description="Spoken or typed product phrase (e.g. 'Kings', 'Filter')")
    quantity: float = Field(..., gt=0, description="Spoken or numerical quantity")
    unit: str = Field(default="piece", description="Spoken or inferred unit (e.g. 'packet', 'dozen', 'piece', 'saram')")


class RawExtractedOrder(BaseModel):
    """
    Output model produced by the LLM extraction layer.
    Contains customer name and extracted line items.
    """
    customer_name: str | None = Field(default=None, description="Customer name if identified in conversation")
    items: list[RawOrderItem] = Field(default_factory=list, description="List of recognized line items")
    raw_transcript: str | None = Field(default=None, description="Original raw transcript or spoken text")


class ResolvedOrderItem(BaseModel):
    """
    Line item after mapping to a canonical product in the database.
    """
    product_id: str = Field(..., description="Canonical product ID in DB, e.g. KINGS, FILTER")
    canonical_name: str = Field(..., description="Official canonical product name")
    quantity: float = Field(..., gt=0, description="Order quantity")
    unit: str = Field(..., description="Authoritative unit of sale")
    retail_rate: float = Field(..., ge=0, description="Authoritative unit rate from database")
    line_total: float = Field(..., ge=0, description="Deterministic line total: quantity * rate")
    conversion_applied: str | None = Field(default=None, description="Note on unit conversion if applicable")
    resolved: bool = Field(default=True, description="Whether product was resolved unambiguously")
    candidate_options: list[str] = Field(default_factory=list, description="IDs of ambiguous candidates if unresolved")


class Order(BaseModel):
    """
    Active conversational order state entity.
    Tracks draft progression, corrections, and final confirmation.
    """
    order_id: str = Field(default_factory=lambda: f"ORD-{uuid.uuid4().hex[:8].upper()}")
    session_id: str = Field(default="default_session", description="User session / WhatsApp phone number")
    customer_name: str | None = Field(default=None, description="Customer name")
    status: OrderStatus = Field(default=OrderStatus.DRAFT)
    raw_items: list[RawOrderItem] = Field(default_factory=list, description="Raw items from user/AI")
    items: list[ResolvedOrderItem] = Field(default_factory=list, description="Resolved database items")
    calculated_bill: CalculatedBill | None = Field(default=None, description="Deterministic bill calculation")
    clarification_prompt: str | None = Field(default=None, description="Question asked to user if ambiguous")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: list[str] = Field(default_factory=list)


class CreateOrderRequest(BaseModel):
    """Payload to create or initialize a new structured order."""
    session_id: str = Field(default="default_session")
    customer_name: str | None = None
    raw_items: list[RawOrderItem] = Field(default_factory=list)


class UpdateOrderItemRequest(BaseModel):
    """Payload to update an item's quantity or unit in an existing order."""
    product_id_or_text: str = Field(..., description="Product ID or original text to match")
    new_quantity: float | None = Field(default=None, gt=0, description="New quantity if updating quantity")
    new_unit: str | None = Field(default=None, description="New unit if updating unit")
