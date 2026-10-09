"""Sales API Router: Confirming sales, Father's search, and daily business reports."""

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Query
from app.models.sale import Sale, DailySalesSummary
from app.models.father_query import FatherQueryRequest, FatherQueryResponse
from app.services.father_query_service import answer_father_query
from app.services.order_service import get_order, confirm_order
from app.services.sales_service import (
    save_confirmed_sale,
    get_sale_by_invoice,
    search_sales_by_customer,
    get_sales_by_product,
    get_sales_for_today,
    get_daily_sales_summary,
    cancel_or_void_sale,
    get_product_stock,
    update_product_stock,
)

router = APIRouter(prefix="/sales", tags=["Sales & Reports"])


class ConfirmSaleRequest(BaseModel):
    """Payload to confirm an active draft order and save it as a permanent sale."""
    created_by: str = Field(default="Mother", description="Operator name")
    customer_phone: str | None = Field(default=None, description="Customer WhatsApp phone number")
    payment_method: str = Field(default="cash")


@router.post("/confirm/{order_id}", response_model=Sale)
def confirm_and_save_sale_endpoint(order_id: str, payload: ConfirmSaleRequest):
    """
    Phase 11: Confirm draft order and save immutable transaction record in MongoDB.
    Snapshots product prices and line items.
    """
    order = get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"Order '{order_id}' not found.")

    try:
        # Ensure order is marked confirmed
        confirmed = confirm_order(order_id)
        # Record permanently in sales collection
        sale = save_confirmed_sale(
            order=confirmed,
            created_by=payload.created_by,
            customer_phone=payload.customer_phone,
            payment_method=payload.payment_method,
        )
        return sale
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ------------------ Phase 12: Father's Sales Search ------------------

@router.get("/today", response_model=list[Sale])
def get_today_sales_endpoint():
    """Phase 12: Retrieve all bills and sales confirmed today."""
    return get_sales_for_today()


@router.get("/invoice/{invoice_number}", response_model=Sale)
def get_sale_by_invoice_endpoint(invoice_number: str):
    """Phase 12: Retrieve specific sale by invoice ID (e.g. 'INV-001')."""
    sale = get_sale_by_invoice(invoice_number)
    if not sale:
        raise HTTPException(status_code=404, detail=f"Invoice '{invoice_number}' not found.")
    return sale


@router.get("/customer/{customer_name}", response_model=list[Sale])
def search_sales_by_customer_endpoint(customer_name: str):
    """Phase 12: Search sales by customer name (e.g. 'What did Satya buy?')."""
    return search_sales_by_customer(customer_name)


@router.get("/product/{product_id}", response_model=list[Sale])
def search_sales_by_product_endpoint(product_id: str):
    """Phase 12: Search sales containing a specific product (e.g. 'Who bought Bingo today?')."""
    return get_sales_by_product(product_id)


# ------------------ Phase 13: Daily Sales Reports ------------------

@router.get("/reports/daily", response_model=DailySalesSummary)
def get_daily_report_endpoint():
    """
    Phase 13: Retrieve daily sales revenue, customer count, and breakdown for Father.
    All numbers calculated from database records.
    """
    return get_daily_sales_summary()


# ------------------ Phase 14: Natural-Language Sales Queries ------------------

@router.post("/query", response_model=FatherQueryResponse)
def father_sales_query_endpoint(payload: FatherQueryRequest):
    """
    Phase 14: Answer Father's natural language sales questions (e.g. 'What did Satya buy today?').
    Extracts intent, queries MongoDB safely, and formats a human WhatsApp reply.
    """
    try:
        return answer_father_query(payload.query)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ------------------ Phase 21 & 23: Stock & Cancellation ------------------

class CancelSaleRequest(BaseModel):
    reason: str = Field(..., description="Reason for cancelling bill")
    operator: str = Field(default="Father", description="Staff/Family member performing cancellation")


class UpdateStockRequest(BaseModel):
    new_quantity: float = Field(..., ge=0, description="New stock amount")
    operator: str = Field(default="Father")


@router.post("/invoice/{invoice_number}/cancel", response_model=Sale)
def cancel_sale_endpoint(invoice_number: str, payload: CancelSaleRequest):
    """
    Phase 23: Cancel an issued bill, restore product inventory, and record in audit log.
    """
    try:
        return cancel_or_void_sale(
            invoice_number=invoice_number,
            reason=payload.reason,
            operator=payload.operator,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/stock/{product_id}")
def get_stock_endpoint(product_id: str):
    """Phase 21: Check remaining inventory of a product."""
    try:
        return get_product_stock(product_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/stock/{product_id}")
def update_stock_endpoint(product_id: str, payload: UpdateStockRequest):
    """Phase 21: Manually adjust product inventory and record audit trail."""
    try:
        return update_product_stock(
            product_id=product_id,
            new_quantity=payload.new_quantity,
            operator=payload.operator,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
