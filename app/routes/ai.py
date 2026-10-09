"""AI endpoints for natural language order understanding."""

from pydantic import BaseModel, Field
from fastapi import APIRouter
from app.models.order import RawExtractedOrder
from app.services.ai_service import extract_order_from_text

router = APIRouter(prefix="/ai", tags=["AI Order Extraction"])


class OrderExtractionRequest(BaseModel):
    """Input payload containing transcribed or typed speech from customer/shopkeeper."""
    transcript: str = Field(..., min_length=1, description="Spoken or typed sentence to extract")


@router.post("/extract-order", response_model=RawExtractedOrder)
def extract_order_endpoint(payload: OrderExtractionRequest):
    """
    Extract structured items, quantities, units, and customer name from natural language.
    Does NOT calculate totals or invent prices.
    """
    return extract_order_from_text(payload.transcript)
