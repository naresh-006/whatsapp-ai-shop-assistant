"""Pydantic models for Father's Natural-Language Sales Queries (Phase 14)."""

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field
from app.models.sale import Sale, DailySalesSummary


class QueryIntent(str, Enum):
    CUSTOMER_SALES = "customer_sales"      # "What did Satya buy today?"
    DAILY_REVENUE = "daily_revenue"        # "What is today's total sales?" / "How many bills today?"
    PRODUCT_SALES = "product_sales"        # "Who bought Bingo today?" / "How much Filter sold?"
    INVOICE_LOOKUP = "invoice_lookup"      # "Show bill INV-001"
    UNKNOWN = "unknown"


class FatherQueryRequest(BaseModel):
    query: str = Field(..., description="Father's spoken or typed natural query")
    requester_phone: str | None = Field(default=None, description="Sender WhatsApp phone number")


class ParsedFatherQuery(BaseModel):
    intent: QueryIntent
    customer_name: str | None = None
    product_identifier: str | None = None
    invoice_number: str | None = None
    date_filter: str | None = Field(default="today", description="'today', 'yesterday', or 'YYYY-MM-DD'")


class FatherQueryResponse(BaseModel):
    intent: QueryIntent
    original_query: str
    answer_text: str = Field(..., description="Respectful, clear WhatsApp-ready response message")
    sales: list[Sale] = Field(default_factory=list)
    daily_summary: DailySalesSummary | None = None
