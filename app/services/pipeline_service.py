"""End-to-End Pipeline Service.

Connects:
1. Speech / Text Transcript
2. AI Structured Extraction
3. Product Resolution & Ambiguity Detection
4. Deterministic Billing Engine
5. Draft Bill Presentation & Conversational Corrections
"""

import logging
import re
from typing import Any

from app.models.order import (
    Order,
    OrderStatus,
    RawOrderItem,
    ResolvedOrderItem,
)
from app.models.billing import BillItemInput
from app.services.ai_service import extract_order_from_text
from app.services.resolver_service import resolve_product_text, ResolutionStatus
from app.services.billing_service import calculate_item_amount, calculate_bill
from app.services.language_service import normalize_tamil_tanglish_text
from app.services.order_service import (
    create_order,
    get_order,
    get_active_order_by_session,
    update_item_quantity,
    remove_item_from_order,
    add_item_to_order,
)

logger = logging.getLogger(__name__)


def process_natural_language_order(
    transcript: str,
    session_id: str = "default_session",
) -> Order:
    """
    Phase 9: Full End-to-End Pipeline
    Natural speech -> LLM Extraction -> Resolver -> MongoDB Rates -> Billing Engine -> Draft Bill.
    """
    clean_transcript = transcript.strip()
    if not clean_transcript:
        raise ValueError("Transcript cannot be empty.")

    # Phase 16: Normalize Tamil & Tanglish colloquial speech
    normalized_transcript = normalize_tamil_tanglish_text(clean_transcript)

    # 1. AI Extraction (Structured understanding)
    extracted = extract_order_from_text(normalized_transcript)
    logger.info("Extracted order for customer '%s' with %d items.", extracted.customer_name, len(extracted.items))

    # 2. Initialize Order
    order = create_order(
        session_id=session_id,
        customer_name=extracted.customer_name,
        raw_items=extracted.items,
    )

    return order


def apply_conversational_correction(
    session_id: str,
    correction_text: str,
) -> Order:
    """
    Phase 10: Natural Conversational Corrections on an active Draft Bill.
    Handles phrases like:
    - 'Change Filter to five' or 'Filter 5'
    - 'Remove Kings' or 'Cancel Kings'
    - 'Add two Marie Light'
    - 'Bingo ₹5' (answering an ambiguity question)
    """
    order = get_active_order_by_session(session_id)
    if not order:
        raise ValueError(f"No active draft order found for session '{session_id}'.")

    text = correction_text.strip()
    text_lower = text.lower()

    # Case A: Answer to ambiguity question (e.g. user previously asked about Bingo, now replies "Bingo ₹5" or "5")
    if order.status == OrderStatus.NEEDS_CLARIFICATION:
        return _resolve_ambiguity_response(order, text)

    # Case B: Removal ("Remove Kings", "Delete Scissor")
    remove_match = re.match(r"^(?:remove|delete|cancel|no)\s+(.*?)$", text_lower)
    if remove_match:
        target = remove_match.group(1).strip()
        return remove_item_from_order(order.order_id, target)

    # Case C: Addition ("Add two Marie Light", "Add 1 Kings")
    add_match = re.match(r"^(?:add|plus)\s+(.*?)$", text_lower)
    if add_match:
        addition_text = add_match.group(1).strip()
        # Extract item from addition text
        extracted_add = extract_order_from_text(addition_text)
        if extracted_add.items:
            for item in extracted_add.items:
                add_item_to_order(order.order_id, item)
            return get_order(order.order_id) or order
        raise ValueError(f"Could not parse item to add from '{addition_text}'.")

    # Case D: Change quantity ("Change Filter to 5", "Change Kings to two", "Filter to 5")
    change_match = re.match(
        r"^(?:change|update|make)?\s*(.*?)\s+(?:from\s+\w+\s+)?(?:to|=)\s+(\w+|\d+)$",
        text_lower,
    )
    if change_match:
        target_prod, qty_str = change_match.groups()
        target_prod = target_prod.replace("change", "").strip()
        qty = _parse_number(qty_str)
        return update_item_quantity(order.order_id, target_prod, qty)

    # Case E: Direct shorthand quantity adjustment (e.g. "Filter 5")
    shorthand_match = re.match(r"^([a-zA-Z\s₹]+)\s+(\d+|\w+)$", text_lower)
    if shorthand_match:
        target_prod, qty_str = shorthand_match.groups()
        try:
            qty = _parse_number(qty_str)
            return update_item_quantity(order.order_id, target_prod.strip(), qty)
        except ValueError:
            pass

    raise ValueError(f"Could not interpret correction phrase: '{correction_text}'")


def _resolve_ambiguity_response(order: Order, answer_text: str) -> Order:
    """Resolve an ambiguous item in the order using the user's clarification answer."""
    from app.services.product_service import get_product_by_id
    from app.services.order_service import _recalculate_order_totals

    # Find the first unresolved item
    unresolved_idx = -1
    for idx, item in enumerate(order.items):
        if not item.resolved:
            unresolved_idx = idx
            break

    if unresolved_idx == -1:
        # None unresolved, check if answer was a general product addition
        res = resolve_product_text(answer_text)
        if res.status in {ResolutionStatus.EXACT_MATCH, ResolutionStatus.CONFIDENT_MATCH} and res.product_id:
            prod = get_product_by_id(res.product_id)
            if prod:
                unit_to_use = str(prod.retail_unit) if hasattr(prod, "retail_unit") else "piece"
                calc = calculate_item_amount(prod, 1.0, unit_to_use)
                order.items.append(
                    ResolvedOrderItem(
                        product_id=prod.product_id,
                        canonical_name=prod.canonical_name,
                        quantity=calc.quantity,
                        unit=calc.unit,
                        retail_rate=calc.rate,
                        line_total=calc.amount,
                        conversion_applied=calc.conversion_applied,
                        resolved=True,
                    )
                )
                order.status = OrderStatus.PENDING_CONFIRMATION
                order.clarification_prompt = None
                _recalculate_order_totals(order)
                return order
        if order.calculated_bill and order.calculated_bill.items:
            order.status = OrderStatus.PENDING_CONFIRMATION
            return order
        raise ValueError(f"No active ambiguous items to resolve with '{answer_text}'.")

    unresolved_item = order.items[unresolved_idx]

    # 1. Direct resolution
    res = resolve_product_text(answer_text)

    # 2. Contextual resolution against candidate options (e.g. user answered "5", "5rs", "$5", "10" for Bingo)
    if (res.status not in {ResolutionStatus.EXACT_MATCH, ResolutionStatus.CONFIDENT_MATCH} or not res.product_id) and unresolved_item.candidate_options:
        clean_ans = answer_text.strip().lower().replace("$", "").replace("₹", "").replace("rs", "").strip()
        word_to_num = {"five": "5", "ten": "10", "one": "1", "two": "2"}
        clean_num = word_to_num.get(clean_ans, clean_ans)
        for cand_id in unresolved_item.candidate_options:
            cand_prod = get_product_by_id(cand_id)
            if cand_prod:
                cand_str = f"{cand_prod.product_id} {cand_prod.variant or ''} {cand_prod.canonical_name}".lower()
                if clean_num and clean_num in cand_str:
                    res = resolve_product_text(cand_prod.canonical_name)
                    break

    # 3. Combined query: canonical item name + answer text (e.g. "bingo" + "5rs" -> "bingo 5rs")
    if res.status not in {ResolutionStatus.EXACT_MATCH, ResolutionStatus.CONFIDENT_MATCH} or not res.product_id:
        combined_query = f"{unresolved_item.canonical_name} {answer_text}"
        res = resolve_product_text(combined_query)

    if res.status in {ResolutionStatus.EXACT_MATCH, ResolutionStatus.CONFIDENT_MATCH} and res.product_id:
        prod = get_product_by_id(res.product_id)
        if prod:
            unit_to_use = unresolved_item.unit
            ret_unit = prod.retail_unit.value if hasattr(prod.retail_unit, "value") else str(prod.retail_unit).lower()
            if unit_to_use == "piece" and ret_unit != "piece":
                unit_to_use = ret_unit

            calculated = calculate_item_amount(prod, unresolved_item.quantity, unit_to_use)
            order.items[unresolved_idx] = ResolvedOrderItem(
                product_id=prod.product_id,
                canonical_name=prod.canonical_name,
                quantity=calculated.quantity,
                unit=calculated.unit,
                retail_rate=calculated.rate,
                line_total=calculated.amount,
                conversion_applied=calculated.conversion_applied,
                resolved=True,
            )

            # Check if any remaining items are unresolved
            still_unresolved = [it for it in order.items if not it.resolved]
            if not still_unresolved:
                order.status = OrderStatus.PENDING_CONFIRMATION
                order.clarification_prompt = None
            else:
                next_item = still_unresolved[0]
                order.clarification_prompt = (
                    f"Product '{next_item.canonical_name}' still needs clarification."
                )

            # Recalculate bill
            _recalculate_order_totals(order)
            return order

    raise ValueError(f"Clarification '{answer_text}' could not resolve ambiguous item.")


def _parse_number(num_str: str) -> float:
    """Parse number words or digits."""
    word_map = {
        "one": 1.0, "two": 2.0, "three": 3.0, "four": 4.0, "five": 5.0,
        "six": 6.0, "seven": 7.0, "eight": 8.0, "nine": 9.0, "ten": 10.0,
        "oru": 1.0, "rendu": 2.0, "moonu": 3.0, "naalu": 4.0, "anju": 5.0,
    }
    cleaned = num_str.strip().lower()
    if cleaned in word_map:
        return word_map[cleaned]
    try:
        return float(cleaned)
    except ValueError:
        raise ValueError(f"Invalid quantity: '{num_str}'")
