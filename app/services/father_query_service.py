"""Father's Natural-Language Sales Query Service (Phase 14).

Understands Father's questions naturally, executes controlled, safe database queries,
and formats respectful, human-friendly WhatsApp responses.
"""

from datetime import datetime, timezone, timedelta, date
import logging
import re
from typing import Any

from app.models.father_query import (
    QueryIntent,
    ParsedFatherQuery,
    FatherQueryResponse,
)
from app.models.sale import Sale, DailySalesSummary
from app.services.sales_service import (
    search_sales_by_customer,
    get_sale_by_invoice,
    get_sales_by_product,
    get_daily_sales_summary,
    get_sales_for_today,
)
from app.config import settings

logger = logging.getLogger(__name__)


def parse_father_query_intent(query_text: str) -> ParsedFatherQuery:
    """
    Parse Father's query into a controlled structured intent.
    Uses LLM if available with API keys, or deterministic rule heuristics.
    """
    cleaned = query_text.strip()
    lower = cleaned.lower()

    # Rule 1: Invoice lookup ("Show bill INV-001", "INV 001", "bill 1")
    inv_match = re.search(r"\b(inv[- ]?\d+|\bbill\s*#?\s*\d+)\b", lower)
    if inv_match:
        raw_inv = inv_match.group(1).replace(" ", "-").replace("bill-", "inv-").replace("bill", "inv-").upper()
        if not raw_inv.startswith("INV-"):
            # format like bill 1 -> INV-001
            digits = re.findall(r"\d+", raw_inv)
            if digits:
                raw_inv = f"INV-{int(digits[0]):03d}"
        return ParsedFatherQuery(
            intent=QueryIntent.INVOICE_LOOKUP,
            invoice_number=raw_inv,
        )

    # Rule 2: Daily Revenue / Summary ("How much sales today?", "Today's collection?", "How many bills today?")
    if any(k in lower for k in [
        "today total", "today's total", "today sales", "today's sales",
        "how much sales", "how much collection", "collection today", "total collection",
        "how many bills", "how many sales", "daily summary", "report today",
        "iniku evlo", "iniku collection", "iniku sales"
    ]):
        return ParsedFatherQuery(
            intent=QueryIntent.DAILY_REVENUE,
            date_filter="today",
        )

    # Rule 3: Product buyers ("Who bought Bingo?", "How much Filter sold?", "Who took kings?")
    product_query_match = re.search(
        r"(?:who bought|who took|how much|how many)\s+([a-zA-Z0-9\s₹]+?)(?:\s+sold|\s+today|\s*\?|$)",
        lower,
    )
    if product_query_match:
        candidate_prod = product_query_match.group(1).strip()
        # Filter out stopwords
        if candidate_prod not in {"sales", "money", "collection", "bills"}:
            return ParsedFatherQuery(
                intent=QueryIntent.PRODUCT_SALES,
                product_identifier=candidate_prod.capitalize(),
                date_filter="today",
            )

    # Rule 4: Customer sales ("What did Satya buy today?", "Satya purchase", "Satya bill")
    cust_match = re.search(
        r"(?:what did|did|what has)\s+([a-zA-Z]+)\s+(?:buy|take|purchase|order)|([a-zA-Z]+)(?:'s|\s+)(?:bill|sales|purchase)",
        lower,
    )
    if cust_match:
        name = cust_match.group(1) or cust_match.group(2)
        if name and name.lower() not in {"today", "we", "the", "our", "shop"}:
            return ParsedFatherQuery(
                intent=QueryIntent.CUSTOMER_SALES,
                customer_name=name.capitalize(),
                date_filter="today",
            )

    # Shorthand: Single word like "Satya" -> Customer sales
    words = cleaned.split()
    if len(words) == 1 and words[0].isalpha() and words[0].lower() not in {"today", "sales", "report", "help"}:
        return ParsedFatherQuery(
            intent=QueryIntent.CUSTOMER_SALES,
            customer_name=words[0].capitalize(),
            date_filter="today",
        )

    # If LLM API is available and heuristic didn't match, attempt LLM structured parsing
    if settings.OPENAI_API_KEY or settings.GEMINI_API_KEY:
        try:
            return _llm_parse_father_query(cleaned)
        except Exception as exc:
            logger.warning("LLM query parsing failed, defaulting: %s", exc)

    return ParsedFatherQuery(intent=QueryIntent.UNKNOWN)


def _llm_parse_father_query(query: str) -> ParsedFatherQuery:
    """Use Gemini or OpenAI to extract controlled query parameters."""
    if settings.GEMINI_API_KEY:
        from google import genai
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        prompt = (
            "You are a sales query parser for an Indian shop assistant. "
            "Extract the query intent and entities into JSON:\n"
            "Query: " + query + "\n"
            "Allowed intents: customer_sales, daily_revenue, product_sales, invoice_lookup, unknown.\n"
            "Date filter: today, yesterday, or YYYY-MM-DD."
        )
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config={"response_mime_type": "application/json", "response_schema": ParsedFatherQuery},
        )
        return ParsedFatherQuery.model_validate_json(response.text)

    if settings.OPENAI_API_KEY:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.beta.chat.completions.parse(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Extract sales query intent for an Indian shop assistant."},
                {"role": "user", "content": query},
            ],
            response_format=ParsedFatherQuery,
        )
        return response.choices[0].message.parsed  # type: ignore

    return ParsedFatherQuery(intent=QueryIntent.UNKNOWN)


def answer_father_query(query_text: str) -> FatherQueryResponse:
    """
    Main entry point: Executes Father's natural language sales inquiry.
    1. Parses intent.
    2. Runs safe, targeted MongoDB queries.
    3. Formats clear, WhatsApp-ready message.
    """
    parsed = parse_father_query_intent(query_text)
    today = datetime.now(timezone.utc).date()

    # Intent 1: Customer Sales Inquiry ("What did Satya buy today?")
    if parsed.intent == QueryIntent.CUSTOMER_SALES and parsed.customer_name:
        sales = search_sales_by_customer(parsed.customer_name)
        if not sales:
            msg = f"No purchases recorded for *{parsed.customer_name}* today."
            return FatherQueryResponse(
                intent=parsed.intent,
                original_query=query_text,
                answer_text=msg,
                sales=[],
            )

        lines = [f"🛒 *Purchases for {parsed.customer_name} today:*"]
        total_spent = sum(s.total for s in sales)
        for s in sales:
            items_str = ", ".join(f"{int(i.quantity) if i.quantity.is_integer() else i.quantity} {i.product_name_snapshot} ({i.unit})" for i in s.items)
            lines.append(f"• *{s.invoice_number}* ({s.created_at.strftime('%I:%M %p')}): {items_str} — *₹{s.total:,.2f}*")
        lines.append(f"\n*Total for {parsed.customer_name}: ₹{total_spent:,.2f}*")

        return FatherQueryResponse(
            intent=parsed.intent,
            original_query=query_text,
            answer_text="\n".join(lines),
            sales=sales,
        )

    # Intent 2: Daily Revenue / Summary ("What is today's total sales?")
    if parsed.intent == QueryIntent.DAILY_REVENUE:
        summary = get_daily_sales_summary(target_date=today)
        lines = [
            f"📊 *Shop Sales Summary for Today ({summary.date}):*",
            f"• *Total Revenue:* ₹{summary.total_sales:,.2f}",
            f"• *Total Bills:* {summary.total_bills}",
            f"• *Customers Served:* {summary.total_customers}",
        ]
        if summary.product_breakdown:
            lines.append("\n*Top Items Sold:*")
            sorted_items = sorted(summary.product_breakdown, key=lambda x: x["revenue"], reverse=True)
            for item in sorted_items[:5]:
                qty = int(item['quantity']) if float(item['quantity']).is_integer() else item['quantity']
                lines.append(f"• {item['product_name']}: {qty} {item['unit']} (₹{item['revenue']:,.2f})")

        return FatherQueryResponse(
            intent=parsed.intent,
            original_query=query_text,
            answer_text="\n".join(lines),
            daily_summary=summary,
        )

    # Intent 3: Product Sales ("Who bought Bingo today?")
    if parsed.intent == QueryIntent.PRODUCT_SALES and parsed.product_identifier:
        sales = get_sales_by_product(parsed.product_identifier)
        if not sales:
            msg = f"No sales found for '*{parsed.product_identifier}*' today."
            return FatherQueryResponse(
                intent=parsed.intent,
                original_query=query_text,
                answer_text=msg,
                sales=[],
            )

        total_prod_revenue = 0.0
        lines = [f"📦 *Sales of '{parsed.product_identifier}' today:*"]
        for s in sales:
            matched_items = [
                i for i in s.items
                if parsed.product_identifier.upper() in i.product_id.upper() or parsed.product_identifier.upper() in i.product_name_snapshot.upper()
            ]
            for mi in matched_items:
                total_prod_revenue += mi.amount
                qty = int(mi.quantity) if mi.quantity.is_integer() else mi.quantity
                lines.append(f"• *{s.customer_name}* ({s.invoice_number}): {qty} {mi.unit} — ₹{mi.amount:,.2f}")
        lines.append(f"\n*Total Revenue for this product: ₹{total_prod_revenue:,.2f}*")

        return FatherQueryResponse(
            intent=parsed.intent,
            original_query=query_text,
            answer_text="\n".join(lines),
            sales=sales,
        )

    # Intent 4: Invoice Lookup ("Show bill INV-001")
    if parsed.intent == QueryIntent.INVOICE_LOOKUP and parsed.invoice_number:
        sale = get_sale_by_invoice(parsed.invoice_number)
        if not sale:
            msg = f"Invoice *{parsed.invoice_number}* not found."
            return FatherQueryResponse(
                intent=parsed.intent,
                original_query=query_text,
                answer_text=msg,
                sales=[],
            )

        lines = [
            f"🧾 *Invoice Details: {sale.invoice_number}*",
            f"• Customer: *{sale.customer_name}*",
            f"• Time: {sale.created_at.strftime('%d-%b-%Y %I:%M %p')}",
            f"• Payment: {sale.payment_method.upper()}",
            "------------------------------------",
        ]
        for item in sale.items:
            qty = int(item.quantity) if item.quantity.is_integer() else item.quantity
            lines.append(f"• {item.product_name_snapshot} ({qty} {item.unit} @ ₹{item.rate}): ₹{item.amount:,.2f}")
        lines.append("------------------------------------")
        lines.append(f"*GRAND TOTAL: ₹{sale.total:,.2f}*")

        return FatherQueryResponse(
            intent=parsed.intent,
            original_query=query_text,
            answer_text="\n".join(lines),
            sales=[sale],
        )

    # Fallback
    return FatherQueryResponse(
        intent=QueryIntent.UNKNOWN,
        original_query=query_text,
        answer_text="Sorry, I could not understand the question. You can ask me:\n"
                    "• 'What did Satya buy today?'\n"
                    "• 'What is today's total sales?'\n"
                    "• 'Who bought Bingo today?'\n"
                    "• 'Show bill INV-001'",
    )
