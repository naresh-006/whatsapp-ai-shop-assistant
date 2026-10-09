"""Orders API Router."""

from fastapi import APIRouter, HTTPException
from app.models.order import (
    Order,
    CreateOrderRequest,
    RawOrderItem,
    UpdateOrderItemRequest,
)
from app.services.order_service import (
    create_order,
    get_order,
    get_active_order_by_session,
    add_item_to_order,
    update_item_quantity,
    remove_item_from_order,
    confirm_order,
    cancel_order,
)

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post("", response_model=Order)
def create_order_endpoint(payload: CreateOrderRequest):
    """Create a new structured draft order."""
    order = create_order(
        session_id=payload.session_id,
        customer_name=payload.customer_name,
        raw_items=payload.raw_items,
    )
    return order


@router.get("/{order_id}", response_model=Order)
def get_order_endpoint(order_id: str):
    """Retrieve an order by ID."""
    order = get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"Order '{order_id}' not found.")
    return order


@router.get("/active/{session_id}", response_model=Order)
def get_active_session_order(session_id: str):
    """Retrieve the current active draft order for a session/phone."""
    order = get_active_order_by_session(session_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"No active draft order found for session '{session_id}'.")
    return order


@router.post("/{order_id}/items", response_model=Order)
def add_item_endpoint(order_id: str, item: RawOrderItem):
    """Add an item to an existing order (e.g. 'Add two Marie Light')."""
    try:
        return add_item_to_order(order_id=order_id, raw_item=item)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/{order_id}/items", response_model=Order)
def update_item_endpoint(order_id: str, payload: UpdateOrderItemRequest):
    """Update item quantity in an order (e.g. 'Change Filter to 5')."""
    try:
        if payload.new_quantity is None:
            raise HTTPException(status_code=400, detail="new_quantity must be provided.")
        return update_item_quantity(
            order_id=order_id,
            product_id_or_text=payload.product_id_or_text,
            new_quantity=payload.new_quantity,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{order_id}/items/{product_text}", response_model=Order)
def delete_item_endpoint(order_id: str, product_text: str):
    """Remove an item from an order (e.g. 'Remove Kings')."""
    try:
        return remove_item_from_order(order_id=order_id, product_id_or_text=product_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{order_id}/confirm", response_model=Order)
def confirm_order_endpoint(order_id: str):
    """Confirm a draft order (human-in-the-loop approval)."""
    try:
        return confirm_order(order_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{order_id}/cancel", response_model=Order)
def cancel_order_endpoint(order_id: str):
    """Discard or cancel a draft order."""
    try:
        return cancel_order(order_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
