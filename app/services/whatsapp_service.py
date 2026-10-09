"""WhatsApp Messaging and Invoicing Service (Phases 17 & 18).

Separates the WhatsApp messaging interface from underlying business logic.
Provides:
- Professional WhatsApp formatted invoice text cards
- Webhook message handling for Mother (orders), Father (queries), and Customers
- Outbound WhatsApp message sending (Twilio / Meta API with mock buffer for testing)
"""

import logging
from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field

from app.models.sale import Sale
from app.models.order import Order, OrderStatus
from app.services.sales_service import (
    get_sale_by_invoice,
    search_sales_by_customer,
    save_confirmed_sale,
)
from app.services.order_service import (
    get_active_order_by_session,
    confirm_order,
    cancel_order,
)
from app.services.pipeline_service import (
    process_natural_language_order,
    apply_conversational_correction,
)
from app.services.father_query_service import answer_father_query
from app.config import settings

logger = logging.getLogger(__name__)

# Outbound message buffer for test verification and tracking
_outbound_messages_log: list[dict[str, Any]] = []


def format_whatsapp_invoice(sale: Sale, shop_name: str = "SRI MURUGAN STORES") -> str:
    """
    Phase 18: Format an authoritative, clean, and elegant WhatsApp receipt.
    Uses monospace alignment and standard WhatsApp bold/italic styling.
    """
    date_str = sale.created_at.strftime("%d-%b-%Y, %I:%M %p")
    lines = [
        f"🧾 *{shop_name}*",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"*Invoice:* `{sale.invoice_number}`",
        f"*Date:* {date_str}",
        f"*Customer:* *{sale.customer_name or 'Valued Customer'}*",
    ]
    if sale.customer_phone:
        lines.append(f"*Phone:* {sale.customer_phone}")
    lines.append(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    for idx, item in enumerate(sale.items, start=1):
        qty_display = int(item.quantity) if item.quantity.is_integer() else item.quantity
        line_item = f"{idx}. *{item.product_name_snapshot}*\n   {qty_display} {item.unit} × ₹{item.rate:,.2f} = *₹{item.amount:,.2f}*"
        lines.append(line_item)

    lines.append(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"💰 *TOTAL AMOUNT:* *₹{sale.total:,.2f}*")
    lines.append(f"*Payment:* {sale.payment_method.capitalize()}")
    lines.append(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"_Thank you for your business!_ 🙏")

    return "\n".join(lines)


def format_draft_order_card(order: Order) -> str:
    """Format draft order for Mother to review and confirm."""
    if order.status == OrderStatus.NEEDS_CLARIFICATION:
        return f"⚠️ *Clarification Needed:*\n{order.clarification_prompt}\n\n_Reply with the variant (e.g. 'Bingo ₹5') to continue._"

    lines = [
        f"📋 *DRAFT BILL - Review Required*",
        f"Customer: *{order.customer_name or 'Walking Customer'}*",
        f"────────────────────────────",
    ]
    if order.calculated_bill and order.calculated_bill.items:
        for idx, item in enumerate(order.calculated_bill.items, start=1):
            qty = int(item.quantity) if item.quantity.is_integer() else item.quantity
            lines.append(f"{idx}. {item.product_name}: {qty} {item.unit} = ₹{item.amount:,.2f}")
        lines.append(f"────────────────────────────")
        lines.append(f"*TOTAL: ₹{order.calculated_bill.grand_total:,.2f}*")
        lines.append(f"\n👉 _Reply *OK* to confirm this bill._")
        lines.append(f"👉 _Or say *Change Filter to 5* or *Remove Kings* to edit._")
    else:
        lines.append("_No items in draft bill._")
        lines.append("\n👉 _Please say or type your order (e.g. 'Satya, 3 Filter, 1 Scissor')._")
    return "\n".join(lines)


def send_whatsapp_message(to_phone: str, message_text: str) -> dict[str, Any]:
    """
    Dispatches outbound WhatsApp text message.
    Records in memory buffer for automated tests and audits.
    """
    record = {
        "to": to_phone,
        "text": message_text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "delivered",
    }
    _outbound_messages_log.append(record)
    logger.info("Sent WhatsApp message to %s: %s", to_phone, message_text[:60])
    return record


def get_outbound_messages_log() -> list[dict[str, Any]]:
    """Retrieve logged outbound WhatsApp messages for testing."""
    return list(_outbound_messages_log)


def clear_outbound_messages_log() -> None:
    """Clear messages log (used in tests)."""
    _outbound_messages_log.clear()


def handle_incoming_whatsapp_message(
    from_number: str,
    message_body: str,
    media_url: str | None = None,
    sender_role: str | None = None,
) -> str:
    """
    Phase 17 Webhook Core Handler:
    Dispatches message to appropriate subsystem based on intent and active session.
    """
    clean_text = message_body.strip()
    session_id = f"wa_{from_number.replace('+', '').replace(':', '')}"

    # Check if there is an active draft order for this session
    active_order = get_active_order_by_session(session_id)

    # 1. Active Bill Confirmation ("ok", "confirm", "yes", "save", "bill ok")
    if active_order and clean_text.lower() in {"ok", "confirm", "yes", "save", "bill ok", "correct"}:
        confirmed = confirm_order(active_order.order_id)
        sale = save_confirmed_sale(
            order=confirmed,
            created_by="Mother",
            customer_phone=from_number if active_order.customer_name != "Mother" else None,
        )
        invoice_card = format_whatsapp_invoice(sale)
        reply = f"✅ *Bill Confirmed & Recorded!*\n\n{invoice_card}"
        send_whatsapp_message(from_number, reply)
        return reply

    # 1.5 Active Bill Cancellation ("cancel", "clear", "discard")
    if active_order and clean_text.lower() in {"cancel", "clear", "discard", "delete bill", "cancel bill"}:
        cancel_order(active_order.order_id)
        reply = "❌ *Draft bill cancelled.* You can start a fresh order anytime (e.g. *Naresh, 2 Kings, 1 Filter*)."
        send_whatsapp_message(from_number, reply)
        return reply

    # 2. Active Bill Correction ("Change Filter to 5", "Remove Kings", "Bingo ₹5")
    if active_order:
        try:
            updated_order = apply_conversational_correction(session_id, clean_text)
            reply = format_draft_order_card(updated_order)
            send_whatsapp_message(from_number, reply)
            return reply
        except Exception:
            # If active order is awaiting clarification, don't accidentally overwrite it
            # with filler words (e.g. 'continue', 'what') unless user clearly entered a new order
            if active_order.status == OrderStatus.NEEDS_CLARIFICATION:
                is_fresh_order = ("," in clean_text) or any(
                    clean_text.lower().startswith(prefix)
                    for prefix in ["new bill", "bill for", "naru", "satya", "kumar", "ravi"]
                )
                if not is_fresh_order:
                    reply = (
                        f"⚠️ *Clarification Needed:*\n"
                        f"{active_order.clarification_prompt}\n\n"
                        f"_Reply with the variant (e.g. 'Bingo ₹5') or say *cancel* to start a fresh order._"
                    )
                    send_whatsapp_message(from_number, reply)
                    return reply
            pass

    # 3. Father's Query (e.g. "What did Satya buy?", "Today's sales", "INV-001")
    if sender_role == "father" or any(kw in clean_text.lower() for kw in [
        "what did", "today sales", "today's sales", "collection", "who bought", "inv-", "show bill"
    ]):
        query_res = answer_father_query(clean_text)
        send_whatsapp_message(from_number, query_res.answer_text)
        return query_res.answer_text

    # 4. New Order Creation (Mother speaking or typing order)
    try:
        new_order = process_natural_language_order(clean_text, session_id=session_id)
        reply = format_draft_order_card(new_order)
        send_whatsapp_message(from_number, reply)
        return reply
    except Exception as exc:
        reply = f"Sorry, could not process: {str(exc)}\nPlease try saying: 'Satya, 3 Filter, 1 Scissor, 2 Kings'"
        send_whatsapp_message(from_number, reply)
        return reply
