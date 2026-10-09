"""Billing routes for deterministic bill calculation."""

from fastapi import APIRouter, HTTPException
from app.models.billing import (
    BillCalculationRequest,
    CalculatedBill,
    InvalidUnitError,
    InvalidQuantityError,
    BillingError,
)
from app.services.billing_service import calculate_bill

router = APIRouter(prefix="/billing", tags=["Billing"])


@router.post("/calculate", response_model=CalculatedBill)
def calculate_bill_endpoint(payload: BillCalculationRequest):
    """
    Calculate an authoritative bill deterministically.
    Takes order items, validates each against database rates and conversion rules,
    and returns exact arithmetic amounts.
    """
    try:
        bill = calculate_bill(items=payload.items, customer_name=payload.customer_name)
        return bill
    except (InvalidUnitError, InvalidQuantityError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except BillingError as exc:
        raise HTTPException(status_code=400, detail=f"Billing error: {exc}")
