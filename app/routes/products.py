"""Product API Routes."""

from typing import Any
from fastapi import APIRouter, HTTPException, Query
from app.models.product import ProductInDB
from app.services.product_service import (
    get_product_by_id,
    list_products,
    search_products,
)

router = APIRouter(prefix="/products", tags=["Products"])


@router.get("/search")
def search_products_endpoint(
    q: str = Query(..., min_length=1, description="Search query string (e.g. 'kings', 'filter', 'bingo')"),
    limit: int = Query(default=10, ge=1, le=50, description="Maximum number of matches to return"),
    is_dummy: bool | None = Query(default=None, description="Filter by dummy/dev products (True/False/None)"),
) -> dict[str, Any]:
    """
    Search products by canonical name, product ID, and spoken aliases (English & Tamil).
    Returns ranked matches with authoritative rates, units, and conversion rules.
    """
    matches = search_products(query=q, limit=limit, is_dummy=is_dummy)
    return {
        "query": q,
        "total_matches": len(matches),
        "results": matches,
    }


@router.get("/{product_id}", response_model=ProductInDB)
def get_product_endpoint(product_id: str):
    """Retrieve authoritative product details by canonical product_id."""
    product = get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail=f"Product not found: '{product_id}'")
    return product


@router.get("", response_model=list[ProductInDB])
def list_products_endpoint(
    category: str | None = Query(default=None, description="Filter by product category"),
    is_dummy: bool | None = Query(default=None, description="Filter by dummy data status"),
    limit: int = Query(default=50, ge=1, le=200, description="Max products to return"),
):
    """List all active products in the catalog with optional filters."""
    products = list_products(category=category, is_dummy=is_dummy, active_only=True)
    return products[:limit]
