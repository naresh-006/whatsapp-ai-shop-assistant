"""Sales Service for persistent sale recording, search, and daily business reports."""

from datetime import datetime, timezone, date
from decimal import Decimal, ROUND_HALF_UP
import logging
import re
from typing import Any

from app.database import (
    get_sales_collection,
    get_audit_logs_collection,
    get_products_collection,
)
from app.models.order import Order, OrderStatus
from app.models.sale import Sale, SaleItemSnapshot, DailySalesSummary

logger = logging.getLogger(__name__)


def _round_currency(amount: float | Decimal) -> float:
    """Accurately round financial values to two decimal places."""
    return float(Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def get_next_invoice_number() -> str:
    """Generate sequential invoice number (e.g. INV-001, INV-002)."""
    sales_col = get_sales_collection()
    count = sales_col.count_documents({})
    return f"INV-{count + 1:03d}"


def save_confirmed_sale(
    order: Order,
    created_by: str = "Mother",
    customer_phone: str | None = None,
    payment_method: str = "cash",
) -> Sale:
    """
    Phase 11: Save a confirmed draft order as a permanent sale in MongoDB.
    Snapshots product names and prices at the moment of sale.
    """
    if order.status != OrderStatus.CONFIRMED and not order.calculated_bill:
        raise ValueError(f"Cannot save unconfirmed order (status: {order.status}).")

    sales_col = get_sales_collection()
    audit_col = get_audit_logs_collection()
    products_col = get_products_collection()

    invoice_no = get_next_invoice_number()

    # Build snapshot items & Phase 21: Auto-deduct inventory
    snapshot_items: list[SaleItemSnapshot] = []
    bill = order.calculated_bill
    assert bill is not None

    low_stock_warnings: list[str] = []

    for item in bill.items:
        snapshot_items.append(
            SaleItemSnapshot(
                product_id=item.product_id,
                product_name_snapshot=item.product_name,
                quantity=item.quantity,
                unit=item.unit,
                rate=item.rate,
                amount=item.amount,
                conversion_applied=item.conversion_applied,
                base_quantity=item.base_quantity,
            )
        )

        # Deduct inventory in base units
        prod_doc = products_col.find_one({"product_id": item.product_id})
        if prod_doc and prod_doc.get("track_stock", True):
            new_stock = max(0.0, float(prod_doc.get("stock_quantity", 100.0)) - item.base_quantity)
            products_col.update_one(
                {"product_id": item.product_id},
                {"$set": {"stock_quantity": new_stock}},
            )
            threshold = float(prod_doc.get("low_stock_threshold", 10.0))
            if new_stock <= threshold:
                warn_msg = f"Low stock alert for {item.product_name}: {new_stock} remaining (threshold: {threshold})"
                low_stock_warnings.append(warn_msg)
                logger.warning(warn_msg)

    metadata: dict[str, Any] = {}
    if low_stock_warnings:
        metadata["low_stock_warnings"] = low_stock_warnings

    sale = Sale(
        invoice_number=invoice_no,
        order_id=order.order_id,
        customer_name=order.customer_name or "Walking Customer",
        customer_phone=customer_phone,
        created_at=datetime.now(timezone.utc),
        created_by=created_by,
        items=snapshot_items,
        subtotal=bill.subtotal,
        total=bill.grand_total,
        status="confirmed",
        payment_method=payment_method,
        metadata=metadata,
    )

    doc = sale.model_dump()
    # Serialize datetime to ISO string for Mongo storage
    doc["created_at"] = sale.created_at.isoformat()

    sales_col.insert_one(doc)

    # Log to audit trail
    audit_col.insert_one({
        "action": "sale_confirmed",
        "sale_id": sale.sale_id,
        "invoice_number": sale.invoice_number,
        "customer_name": sale.customer_name,
        "total": sale.total,
        "created_by": created_by,
        "timestamp": sale.created_at.isoformat(),
        "items_count": len(snapshot_items),
    })

    logger.info("Successfully recorded sale %s (%s) for %s - Total ₹%s", sale.sale_id, invoice_no, sale.customer_name, sale.total)
    return sale


def cancel_or_void_sale(
    invoice_number: str,
    reason: str,
    operator: str = "Father",
) -> Sale:
    """
    Phase 23: Cancel/Void a confirmed bill.
    Restores deducted product stock, marks bill 'cancelled', and writes immutable audit log.
    """
    sales_col = get_sales_collection()
    audit_col = get_audit_logs_collection()
    products_col = get_products_collection()

    clean_inv = invoice_number.strip().upper()
    doc = sales_col.find_one({"invoice_number": clean_inv})
    if not doc:
        raise ValueError(f"Invoice '{clean_inv}' not found.")

    if doc.get("status") == "cancelled":
        raise ValueError(f"Invoice '{clean_inv}' is already cancelled.")

    doc.pop("_id", None)
    if isinstance(doc.get("created_at"), str):
        doc["created_at"] = datetime.fromisoformat(doc["created_at"])
    sale = Sale(**doc)

    # Restock inventory
    for item in sale.items:
        prod_doc = products_col.find_one({"product_id": item.product_id})
        if prod_doc and prod_doc.get("track_stock", True):
            restocked = float(prod_doc.get("stock_quantity", 0.0)) + item.base_quantity
            products_col.update_one(
                {"product_id": item.product_id},
                {"$set": {"stock_quantity": restocked}},
            )

    # Update sale status
    now_iso = datetime.now(timezone.utc).isoformat()
    sales_col.update_one(
        {"invoice_number": clean_inv},
        {
            "$set": {
                "status": "cancelled",
                "cancellation_reason": reason,
                "cancelled_by": operator,
                "cancelled_at": now_iso,
            }
        },
    )

    # Audit log
    audit_col.insert_one({
        "action": "sale_cancelled",
        "sale_id": sale.sale_id,
        "invoice_number": clean_inv,
        "reason": reason,
        "operator": operator,
        "timestamp": now_iso,
        "original_total": sale.total,
    })

    sale.status = "cancelled"
    return sale


def get_product_stock(product_id: str) -> dict[str, Any]:
    """Retrieve current stock count for a product."""
    products_col = get_products_collection()
    doc = products_col.find_one({"product_id": product_id.strip().upper()})
    if not doc:
        raise ValueError(f"Product '{product_id}' not found.")
    return {
        "product_id": doc["product_id"],
        "canonical_name": doc["canonical_name"],
        "stock_quantity": doc.get("stock_quantity", 0.0),
        "low_stock_threshold": doc.get("low_stock_threshold", 10.0),
        "track_stock": doc.get("track_stock", True),
    }


def update_product_stock(product_id: str, new_quantity: float, operator: str = "Father") -> dict[str, Any]:
    """Manually adjust or replenish product stock."""
    if new_quantity < 0:
        raise ValueError("Stock quantity cannot be negative.")
    products_col = get_products_collection()
    audit_col = get_audit_logs_collection()

    clean_id = product_id.strip().upper()
    doc = products_col.find_one({"product_id": clean_id})
    if not doc:
        raise ValueError(f"Product '{clean_id}' not found.")

    old_stock = doc.get("stock_quantity", 0.0)
    products_col.update_one({"product_id": clean_id}, {"$set": {"stock_quantity": new_quantity}})

    audit_col.insert_one({
        "action": "stock_updated",
        "product_id": clean_id,
        "old_stock": old_stock,
        "new_stock": new_quantity,
        "operator": operator,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "product_id": clean_id,
        "old_stock": old_stock,
        "new_stock": new_quantity,
        "updated_by": operator,
    }


# ------------------ Phase 12: Father's Sales Search ------------------

def get_sale_by_invoice(invoice_number: str) -> Sale | None:
    """Search exact sale by invoice number (e.g. 'INV-001')."""
    clean_inv = invoice_number.strip().upper()
    sales_col = get_sales_collection()
    doc = sales_col.find_one({"invoice_number": clean_inv})
    if not doc:
        return None
    doc.pop("_id", None)
    if isinstance(doc.get("created_at"), str):
        doc["created_at"] = datetime.fromisoformat(doc["created_at"])
    return Sale(**doc)


def search_sales_by_customer(
    customer_name: str,
    target_date: date | None = None,
) -> list[Sale]:
    """
    Search sales made by a specific customer (e.g. 'What did Satya buy today?').
    Matches customer name case-insensitively.
    """
    sales_col = get_sales_collection()
    regex_pattern = f".*{re.escape(customer_name.strip())}.*"
    query: dict[str, Any] = {"customer_name": {"$regex": regex_pattern, "$options": "i"}}

    all_sales = []
    for doc in sales_col.find(query).sort("created_at", -1):
        doc.pop("_id", None)
        if isinstance(doc.get("created_at"), str):
            doc["created_at"] = datetime.fromisoformat(doc["created_at"])
        sale_obj = Sale(**doc)

        if target_date:
            if sale_obj.created_at.date() == target_date:
                all_sales.append(sale_obj)
        else:
            all_sales.append(sale_obj)

    return all_sales


def get_sales_by_product(
    product_identifier: str,
    target_date: date | None = None,
) -> list[Sale]:
    """Search which customers bought a specific product (e.g. 'Who bought Bingo today?')."""
    sales_col = get_sales_collection()
    clean = product_identifier.strip().upper()

    all_sales = []
    for doc in sales_col.find().sort("created_at", -1):
        doc.pop("_id", None)
        if isinstance(doc.get("created_at"), str):
            doc["created_at"] = datetime.fromisoformat(doc["created_at"])
        sale_obj = Sale(**doc)

        # Check if product is in items
        has_product = any(
            item.product_id.upper() == clean or clean in item.product_name_snapshot.upper()
            for item in sale_obj.items
        )

        if has_product:
            if target_date:
                if sale_obj.created_at.date() == target_date:
                    all_sales.append(sale_obj)
            else:
                all_sales.append(sale_obj)

    return all_sales


def get_sales_for_today() -> list[Sale]:
    """Retrieve all sales recorded on today's date."""
    today = datetime.now(timezone.utc).date()
    sales_col = get_sales_collection()

    today_sales = []
    for doc in sales_col.find().sort("created_at", -1):
        doc.pop("_id", None)
        if isinstance(doc.get("created_at"), str):
            doc["created_at"] = datetime.fromisoformat(doc["created_at"])
        sale_obj = Sale(**doc)
        if sale_obj.created_at.date() == today:
            today_sales.append(sale_obj)

    return today_sales


# ------------------ Phase 13: Daily Sales Reports ------------------

def get_daily_sales_summary(target_date: date | None = None) -> DailySalesSummary:
    """
    Generate authoritative daily summary of sales revenue and items.
    All figures are derived directly from stored transactions.
    """
    day = target_date or datetime.now(timezone.utc).date()
    sales_col = get_sales_collection()

    daily_sales = []
    for doc in sales_col.find():
        doc.pop("_id", None)
        if isinstance(doc.get("created_at"), str):
            doc["created_at"] = datetime.fromisoformat(doc["created_at"])
        sale_obj = Sale(**doc)
        if sale_obj.created_at.date() == day:
            daily_sales.append(sale_obj)

    total_amount = _round_currency(sum(s.total for s in daily_sales))
    unique_customers = {s.customer_name for s in daily_sales if s.customer_name}

    # Customer breakdown
    cust_breakdown = [
        {
            "customer_name": s.customer_name,
            "invoice_number": s.invoice_number,
            "total": s.total,
            "items_count": len(s.items),
            "time": s.created_at.strftime("%H:%M:%S"),
        }
        for s in daily_sales
    ]

    # Product breakdown (aggregated volume and revenue)
    product_totals: dict[str, dict[str, Any]] = {}
    for s in daily_sales:
        for item in s.items:
            key = item.product_id
            if key not in product_totals:
                product_totals[key] = {
                    "product_id": key,
                    "product_name": item.product_name_snapshot,
                    "quantity": 0.0,
                    "unit": item.unit,
                    "revenue": 0.0,
                }
            product_totals[key]["quantity"] += item.quantity
            product_totals[key]["revenue"] = _round_currency(
                product_totals[key]["revenue"] + item.amount
            )

    return DailySalesSummary(
        date=day.isoformat(),
        total_sales=total_amount,
        total_bills=len(daily_sales),
        total_customers=len(unique_customers),
        customer_breakdown=cust_breakdown,
        product_breakdown=list(product_totals.values()),
    )
