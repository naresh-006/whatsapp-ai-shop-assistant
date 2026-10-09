"""Order service for managing structured draft orders and conversational state."""

from datetime import datetime, timezone
import logging
from typing import Any

from app.models.order import (
    Order,
    OrderStatus,
    RawOrderItem,
    ResolvedOrderItem,
)
from app.models.billing import BillItemInput
from app.services.product_service import get_product_by_id, search_products
from app.services.billing_service import calculate_item_amount, calculate_bill

logger = logging.getLogger(__name__)

# In-memory session order store (persisted to MongoDB in sales phase when confirmed)
_active_orders: dict[str, Order] = {}


def create_order(
    session_id: str = "default_session",
    customer_name: str | None = None,
    raw_items: list[RawOrderItem] | None = None,
) -> Order:
    """Initialize a new structured order for a session."""
    order = Order(
        session_id=session_id,
        customer_name=customer_name,
        raw_items=raw_items or [],
        status=OrderStatus.DRAFT,
    )

    if raw_items:
        for raw_item in raw_items:
            _resolve_and_add_item(order, raw_item)
        _recalculate_order_totals(order)

    # Cancel previous unconfirmed drafts for this session
    for prev in _active_orders.values():
        if prev.session_id == session_id and prev.status in {
            OrderStatus.DRAFT,
            OrderStatus.PENDING_CONFIRMATION,
            OrderStatus.NEEDS_CLARIFICATION,
        }:
            prev.status = OrderStatus.CANCELLED

    _active_orders[order.order_id] = order
    logger.info("Created order %s for session %s", order.order_id, session_id)
    return order


def get_order(order_id: str) -> Order | None:
    """Retrieve an active order by order_id."""
    return _active_orders.get(order_id)


def get_active_order_by_session(session_id: str) -> Order | None:
    """Retrieve the most recent unconfirmed/uncancelled order for a session."""
    active_statuses = {OrderStatus.DRAFT, OrderStatus.PENDING_CONFIRMATION, OrderStatus.NEEDS_CLARIFICATION}
    for order in reversed(list(_active_orders.values())):
        if order.session_id == session_id and order.status in active_statuses:
            return order
    return None


def add_item_to_order(order_id: str, raw_item: RawOrderItem) -> Order:
    """Add a new item to an existing order and recalculate."""
    order = _get_or_fail(order_id)
    order.raw_items.append(raw_item)
    _resolve_and_add_item(order, raw_item)
    _recalculate_order_totals(order)
    order.updated_at = datetime.now(timezone.utc)
    return order


def update_item_quantity(
    order_id: str,
    product_id_or_text: str,
    new_quantity: float,
) -> Order:
    """
    Update the quantity of an item in the order (e.g. 'Change Filter to 5').
    Matches by canonical product_id or raw text.
    """
    if new_quantity <= 0:
        raise ValueError("Quantity must be greater than 0.")

    order = _get_or_fail(order_id)
    target = product_id_or_text.strip().lower()
    updated = False

    # Update in resolved items
    for item in order.items:
        if (
            item.product_id.lower() == target
            or item.canonical_name.lower() == target
            or target in item.canonical_name.lower()
        ):
            item.quantity = new_quantity
            # Recalculate line total
            prod = get_product_by_id(item.product_id)
            if prod:
                calc = calculate_item_amount(prod, new_quantity, item.unit)
                item.line_total = calc.amount
                item.retail_rate = calc.rate
            updated = True
            break

    if not updated:
        raise ValueError(f"Item matching '{product_id_or_text}' not found in order {order_id}")

    _recalculate_order_totals(order)
    order.updated_at = datetime.now(timezone.utc)
    return order


def remove_item_from_order(order_id: str, product_id_or_text: str) -> Order:
    """Remove an item from the order (e.g. 'Remove Kings')."""
    order = _get_or_fail(order_id)
    target = product_id_or_text.strip().lower()

    original_count = len(order.items)
    order.items = [
        item for item in order.items
        if not (
            item.product_id.lower() == target
            or item.canonical_name.lower() == target
            or target in item.canonical_name.lower()
        )
    ]

    if len(order.items) == original_count:
        raise ValueError(f"Item matching '{product_id_or_text}' not found in order {order_id}")

    _recalculate_order_totals(order)
    order.updated_at = datetime.now(timezone.utc)
    return order


def confirm_order(order_id: str) -> Order:
    """Mark an order as confirmed by the user (ready for sale storage)."""
    order = _get_or_fail(order_id)
    if not order.items:
        raise ValueError("Cannot confirm an order with zero items.")
    if order.status == OrderStatus.NEEDS_CLARIFICATION:
        raise ValueError("Cannot confirm order: ambiguity requires clarification first.")

    order.status = OrderStatus.CONFIRMED
    order.updated_at = datetime.now(timezone.utc)
    logger.info("Order %s confirmed.", order_id)
    return order


def cancel_order(order_id: str) -> Order:
    """Mark an order as cancelled."""
    order = _get_or_fail(order_id)
    order.status = OrderStatus.CANCELLED
    order.updated_at = datetime.now(timezone.utc)
    logger.info("Order %s cancelled.", order_id)
    return order


# ------------------ Internal Helpers ------------------

def _get_or_fail(order_id: str) -> Order:
    order = get_order(order_id)
    if not order:
        raise ValueError(f"Order '{order_id}' not found.")
    return order


def _resolve_and_add_item(order: Order, raw_item: RawOrderItem) -> None:
    """Resolve a raw order item into a resolved database item using the central resolver."""
    from app.services.resolver_service import resolve_product_text, ResolutionStatus

    # 1. Resolve via the authoritative resolver service
    res = resolve_product_text(raw_item.product_text)

    if res.status in {ResolutionStatus.EXACT_MATCH, ResolutionStatus.CONFIDENT_MATCH} and res.product_id:
        product = get_product_by_id(res.product_id)
        if product:
            unit_to_use = raw_item.unit
            ret_unit = product.retail_unit.value if hasattr(product.retail_unit, "value") else str(product.retail_unit).lower()
            if unit_to_use == "piece" and ret_unit != "piece":
                unit_to_use = ret_unit

            try:
                calculated = calculate_item_amount(
                    product=product,
                    quantity=raw_item.quantity,
                    unit=unit_to_use,
                )
                resolved_item = ResolvedOrderItem(
                    product_id=product.product_id,
                    canonical_name=product.canonical_name,
                    quantity=calculated.quantity,
                    unit=calculated.unit,
                    retail_rate=calculated.rate,
                    line_total=calculated.amount,
                    conversion_applied=calculated.conversion_applied,
                    resolved=True,
                )
                order.items.append(resolved_item)
                return
            except Exception as calc_err:
                order.status = OrderStatus.NEEDS_CLARIFICATION
                order.clarification_prompt = (
                    f"Pricing for '{raw_item.product_text} ({raw_item.unit})' requires clarification: {str(calc_err)}"
                )
                order.items.append(
                    ResolvedOrderItem(
                        product_id="UNRESOLVED",
                        canonical_name=f"{product.canonical_name} ({raw_item.unit})",
                        quantity=raw_item.quantity,
                        unit=raw_item.unit,
                        retail_rate=0.0,
                        line_total=0.0,
                        resolved=False,
                    )
                )
                return

    if res.status == ResolutionStatus.AMBIGUOUS:
        order.status = OrderStatus.NEEDS_CLARIFICATION
        order.clarification_prompt = (
            f"Did you mean {', or '.join(res.candidate_names)} for '{raw_item.product_text}'?"
        )
        order.items.append(
            ResolvedOrderItem(
                product_id="UNRESOLVED",
                canonical_name=raw_item.product_text,
                quantity=raw_item.quantity,
                unit=raw_item.unit,
                retail_rate=0.0,
                line_total=0.0,
                resolved=False,
                candidate_options=res.candidate_options,
            )
        )
        return

    # Product not found / not identified
    order.status = OrderStatus.NEEDS_CLARIFICATION
    order.clarification_prompt = f"Product '{raw_item.product_text}' could not be identified."
    order.items.append(
        ResolvedOrderItem(
            product_id="UNRESOLVED",
            canonical_name=raw_item.product_text,
            quantity=raw_item.quantity,
            unit=raw_item.unit,
            retail_rate=0.0,
            line_total=0.0,
            resolved=False,
            candidate_options=[],
        )
    )


def _recalculate_order_totals(order: Order) -> None:
    """Recalculate complete bill using billing engine."""
    valid_items = [item for item in order.items if item.resolved]
    if not valid_items:
        order.calculated_bill = None
        return

    bill_inputs = [
        BillItemInput(
            product_id=item.product_id,
            quantity=item.quantity,
            unit=item.unit,
        )
        for item in valid_items
    ]

    bill = calculate_bill(items=bill_inputs, customer_name=order.customer_name)
    order.calculated_bill = bill

    if order.status != OrderStatus.NEEDS_CLARIFICATION:
        order.status = OrderStatus.PENDING_CONFIRMATION
