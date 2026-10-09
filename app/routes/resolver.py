"""Product Resolver API Router."""

from fastapi import APIRouter, Query
from app.models.order import RawExtractedOrder
from app.services.resolver_service import (
    resolve_product_text,
    resolve_extracted_order,
    ResolutionResult,
)

router = APIRouter(prefix="/resolver", tags=["Product Resolver"])


@router.get("/resolve", response_model=ResolutionResult)
def resolve_single_endpoint(
    q: str = Query(..., min_length=1, description="Raw product phrase to resolve (e.g. 'Kings', 'Bingo')"),
):
    """
    Resolve raw spoken product text into a canonical product record.
    Detects ambiguity and prompts for clarification if needed.
    """
    return resolve_product_text(q)


@router.post("/resolve-order", response_model=list[ResolutionResult])
def resolve_order_endpoint(payload: RawExtractedOrder):
    """Resolve all items in an extracted order."""
    return resolve_extracted_order(payload)
