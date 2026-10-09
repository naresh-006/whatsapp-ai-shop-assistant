"""Deterministic Billing Engine.

Performs pure mathematical calculations and unit conversions.
AI never decides or overrides numbers here.
"""

from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Any

from app.models.product import ProductInDB
from app.models.billing import (
    BillItemInput,
    CalculatedBillItem,
    CalculatedBill,
    InvalidUnitError,
    InvalidQuantityError,
)
from app.services.product_service import get_product_by_id

logger = logging.getLogger(__name__)


def _round_currency(amount: float | Decimal) -> float:
    """Accurately round financial amounts to two decimal places."""
    dec = Decimal(str(amount))
    return float(dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def validate_unit(product: ProductInDB, unit: Any) -> str:
    """
    Validate whether a given unit of sale is supported by the product.
    Returns normalized unit string or raises InvalidUnitError.
    """
    unit_val = unit.value if hasattr(unit, "value") else str(unit)
    clean_unit = unit_val.strip().lower()
    if clean_unit.startswith("unittype."):
        clean_unit = clean_unit.split(".")[-1]

    retail_unit = product.retail_unit.value if hasattr(product.retail_unit, "value") else str(product.retail_unit).lower()
    if retail_unit.startswith("unittype."):
        retail_unit = retail_unit.split(".")[-1]

    base_unit = product.base_unit.value if hasattr(product.base_unit, "value") else str(product.base_unit).lower()
    if base_unit.startswith("unittype."):
        base_unit = base_unit.split(".")[-1]

    supported = {retail_unit, base_unit}
    if product.wholesale_unit:
        wh_unit = product.wholesale_unit.value if hasattr(product.wholesale_unit, "value") else str(product.wholesale_unit).lower()
        supported.add(wh_unit)

    for rule_key in product.conversion_rules.keys():
        supported.add(rule_key.lower())

    # Common colloquial plurals mapping
    plural_map = {
        "pieces": "piece",
        "packets": "packet",
        "dozens": "dozen",
        "sarams": "saram",
        "bundles": "bundle",
        "kattu": "bundle",
        "box": "bundle",
        "boxes": "bundle",
    }
    normalized = plural_map.get(clean_unit, clean_unit)

    if normalized not in supported:
        raise InvalidUnitError(
            f"Unit '{unit}' is not valid for product '{product.canonical_name}'. "
            f"Supported units: {sorted(list(supported))}"
        )

    return normalized


def calculate_item_amount(
    product: ProductInDB,
    quantity: float,
    unit: str,
    is_wholesale: bool = False,
) -> CalculatedBillItem:
    """
    Deterministically calculate the price of an item given product, quantity, and unit.

    Rules:
    1. If unit matches retail_unit, rate is retail_rate.
    2. If unit is a defined conversion_rule (e.g. 'bundle'):
       - If explicit 'rate' exists, apply rule.rate directly.
       - If 'pieces' exists and base_unit is 'piece', bundle_rate = pieces * retail_rate.
       - If conversion rule rate is undefined (e.g. Filter bundle), raise InvalidUnitError.
    3. If unit is 'piece' but retail_unit is 'dozen':
       - calculate piece_rate = retail_rate / 12.
    """
    if quantity <= 0:
        raise InvalidQuantityError(f"Quantity must be greater than 0, got: {quantity}")

    clean_unit = validate_unit(product, unit)
    retail_unit = product.retail_unit.value if hasattr(product.retail_unit, "value") else str(product.retail_unit).lower()
    base_unit = product.base_unit.value if hasattr(product.base_unit, "value") else str(product.base_unit).lower()

    applied_rate: float
    conversion_note: str | None = None
    base_qty: float

    wholesale_applied = False

    # Case 0: Wholesale pricing requested and product has wholesale rate
    if is_wholesale and product.wholesale_rate is not None and product.wholesale_rate > 0:
        applied_rate = product.wholesale_rate
        base_qty = quantity
        wholesale_applied = True
        conversion_note = f"Wholesale rate applied: ₹{product.wholesale_rate}"

    # Case 1: Unit matches primary retail unit
    elif clean_unit == retail_unit:
        applied_rate = product.retail_rate
        base_qty = quantity
        conversion_note = None

    # Case 2: Conversion rule lookup (e.g. bundle, dozen, saram)
    elif clean_unit in product.conversion_rules:
        rule = product.conversion_rules[clean_unit]
        # 2a. Rule has fixed authoritative rate
        if rule.rate is not None and rule.rate > 0:
            applied_rate = rule.rate
            base_qty = quantity * (rule.pieces or 1)
            conversion_note = f"1 {clean_unit} = fixed rate ₹{rule.rate}"

        # 2b. Rule has defined piece count and base_unit is piece
        elif rule.pieces is not None and base_unit == "piece":
            applied_rate = _round_currency(rule.pieces * product.retail_rate)
            base_qty = quantity * rule.pieces
            conversion_note = f"1 {clean_unit} = {rule.pieces} pieces @ ₹{product.retail_rate}/piece"

        # 2c. Rule rate is undefined (e.g. Filter where bundle pricing is unverified)
        else:
            raise InvalidUnitError(
                f"Cannot calculate '{clean_unit}' price for '{product.canonical_name}'. "
                f"Rate is not defined. {rule.notes or 'Requires explicit price confirmation.'}"
            )

    # Case 3: Asking for piece when sold by dozen
    elif clean_unit == "piece" and retail_unit == "dozen":
        rule = product.conversion_rules.get("dozen")
        piece_count = rule.pieces if (rule and rule.pieces) else 12
        applied_rate = _round_currency(product.retail_rate / piece_count)
        base_qty = quantity / piece_count
        conversion_note = f"1 piece = 1/{piece_count} dozen @ ₹{product.retail_rate}/dozen"

    # Case 4: Unit matches base unit directly
    elif clean_unit == base_unit:
        applied_rate = product.retail_rate
        base_qty = quantity
        conversion_note = None

    else:
        raise InvalidUnitError(
            f"Unsupported unit '{clean_unit}' for product '{product.canonical_name}'."
        )

    exact_amount = _round_currency(quantity * applied_rate)

    return CalculatedBillItem(
        product_id=product.product_id,
        product_name=product.canonical_name,
        quantity=quantity,
        unit=clean_unit,
        rate=applied_rate,
        amount=exact_amount,
        conversion_applied=conversion_note,
        base_quantity=round(base_qty, 3),
        is_wholesale=wholesale_applied,
    )


def calculate_bundle_amount(product: ProductInDB, quantity: float) -> CalculatedBillItem:
    """Convenience helper to calculate bundle price for a product."""
    return calculate_item_amount(product, quantity=quantity, unit="bundle")


def calculate_total(items: list[CalculatedBillItem]) -> float:
    """Pure deterministic sum of calculated item amounts."""
    return _round_currency(sum(item.amount for item in items))


def calculate_bill(
    items: list[BillItemInput],
    customer_name: str | None = None,
    is_wholesale: bool = False,
) -> CalculatedBill:
    """
    Given a list of BillItemInput objects, fetch each product and calculate
    all item amounts deterministically, returning the complete CalculatedBill.
    """
    if not items:
        raise ValueError("Cannot calculate a bill with zero items.")

    calculated_items: list[CalculatedBillItem] = []
    notes: list[str] = []

    for item_input in items:
        product = get_product_by_id(item_input.product_id)
        if not product:
            raise ValueError(f"Product '{item_input.product_id}' not found in database.")

        wholesale_flag = item_input.is_wholesale or is_wholesale
        calculated_item = calculate_item_amount(
            product=product,
            quantity=item_input.quantity,
            unit=item_input.unit,
            is_wholesale=wholesale_flag,
        )
        calculated_items.append(calculated_item)
        if calculated_item.conversion_applied:
            notes.append(f"{calculated_item.product_name}: {calculated_item.conversion_applied}")

    grand_total = calculate_total(calculated_items)

    return CalculatedBill(
        customer_name=customer_name,
        items=calculated_items,
        total_items=len(calculated_items),
        subtotal=grand_total,
        grand_total=grand_total,
        is_wholesale=is_wholesale,
        notes=notes,
    )
