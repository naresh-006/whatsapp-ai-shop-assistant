"""AI Service for extracting structured orders from natural language transcripts."""

import json
import logging
import re
from typing import Any

from app.config import settings
from app.models.order import RawExtractedOrder, RawOrderItem

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an accurate Order Extraction Assistant for a retail + wholesale family shop in Tamil Nadu, India.
Your SOLE job is to extract customer name, product items, quantities, and units from spoken or typed customer orders.
The input may be in English, Tamil, Tanglish, or mixed phrasing (e.g., "Satya, three Filter, one Scissor, two Kings" or "Satya-ku 3 Filter, 1 Scissor kudunga").

CRITICAL INSTRUCTIONS:
1. Extract ONLY what the user said.
2. NEVER invent, guess, or hallucinate prices, rates, stock, or totals. Rates and math are strictly computed by the database.
3. Convert number words to numeric values (e.g., "one" -> 1, "two" / "rendu" -> 2, "three" / "moonu" -> 3, "four" -> 4, "five" / "anju" -> 5, "ten" / "pathu" -> 10).
4. Preserve product variants if spoken (e.g., "Marie Light five rupees" -> "Marie Light ₹5", "Bingo five" -> "Bingo ₹5", "Bingo ten" -> "Bingo ₹10").
5. Identify units if spoken (packet, piece, dozen, saram, bundle). If no unit is mentioned, infer reasonably (e.g. Filter is usually 'packet', Kings is usually 'piece', Marie Light ₹5 is usually 'dozen', Bingo is usually 'saram', default is 'piece').
6. Output MUST strictly match the requested JSON schema with keys: "customer_name" (string or null) and "items" (array of {"product_text", "quantity", "unit"}).
"""

# Number words mapping for heuristic parsing
NUMBER_WORDS: dict[str, float] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9, "10": 10,
    "oru": 1, "onnu": 1, "rendu": 2, "moonu": 3, "naalu": 4, "anju": 5, "aaru": 6, "pathu": 10,
    "ஒன்று": 1, "இரண்டு": 2, "மூன்று": 3, "நான்கு": 4, "ஐந்து": 5, "பத்து": 10,
}

UNIT_WORDS: dict[str, str] = {
    "packet": "packet", "packets": "packet", "pkt": "packet",
    "piece": "piece", "pieces": "piece", "pcs": "piece",
    "dozen": "dozen", "dozens": "dozen",
    "saram": "saram", "sarams": "saram",
    "bundle": "bundle", "bundles": "bundle", "kattu": "bundle",
}


def extract_order_from_text(transcript: str) -> RawExtractedOrder:
    """
    Extract structured customer name and line items from an unstructured transcript.
    Uses LLM (Gemini / OpenAI) if API keys are configured, falling back to a robust
    heuristic parser for offline testing and network fault tolerance.
    """
    clean_text = transcript.strip()
    if not clean_text:
        return RawExtractedOrder(customer_name=None, items=[], raw_transcript="")

    # Try Gemini if API key configured
    if settings.GEMINI_API_KEY:
        try:
            return _extract_with_gemini(clean_text)
        except Exception as exc:
            logger.warning("Gemini extraction failed (%s), falling back...", exc)

    # Try OpenAI if API key configured
    if settings.OPENAI_API_KEY:
        try:
            return _extract_with_openai(clean_text)
        except Exception as exc:
            logger.warning("OpenAI extraction failed (%s), falling back...", exc)

    # Heuristic fallback (fast, offline, deterministic)
    return _extract_heuristic(clean_text)


def _extract_with_gemini(text: str) -> RawExtractedOrder:
    """Extract order using Google GenAI SDK with structured output."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    prompt = f"{SYSTEM_PROMPT}\n\nTranscript to extract:\n\"\"\"{text}\"\"\""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RawExtractedOrder,
            temperature=0.0,
        ),
    )

    data = json.loads(response.text)
    order = RawExtractedOrder(**data)
    order.raw_transcript = text
    return order


def _extract_with_openai(text: str) -> RawExtractedOrder:
    """Extract order using OpenAI with response_format json_object."""
    from openai import OpenAI

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Extract order from: {text}"},
        ],
        response_format={"type": "json_object"},
        temperature=0.0,
    )

    raw_json = response.choices[0].message.content or "{}"
    data = json.loads(raw_json)
    order = RawExtractedOrder(**data)
    order.raw_transcript = text
    return order


def _extract_heuristic(text: str) -> RawExtractedOrder:
    """
    Deterministic rule-based extractor for common shop patterns and offline test suites.
    Handles phrases like:
    - 'Satya, three Filter, one Scissor, two Kings'
    - 'naresh, kings 1, filter 2'
    - 'naresh,kings-1,filter-2'
    - 'Satya-ku 3 Filter, 1 Scissor'
    """
    customer_name: str | None = None
    clean_text = text.strip()

    # Normalize currency symbol $ before digits to ₹ (e.g. $5 -> ₹5)
    clean_text = re.sub(r"\$(\d+)", r"₹\1", clean_text)

    # Normalize spoken price variants (e.g. "Bingo five rupees" -> "Bingo ₹5", "Marie Light 10 rupees" -> "Marie Light ₹10")
    clean_text = re.sub(r"\b(five|5)\s*(?:rupees|rs|r|roobai|ரூபாய்)\b", "₹5", clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r"\b(ten|10)\s*(?:rupees|rs|r|roobai|ரூபாய்)\b", "₹10", clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r"\b(\d+)\s*(?:rupees|rs|r|roobai|ரூபாய்)\b", r"₹\1", clean_text, flags=re.IGNORECASE)

    # Normalize hyphens/colons connecting words and digits (e.g. 'kings-1' -> 'kings 1')
    clean_text = re.sub(r"([a-zA-Z])[-:]+(\d+)", r"\1 \2", clean_text)
    clean_text = re.sub(r"(\d+)[-:]+([a-zA-Z])", r"\1 \2", clean_text)
    remaining_text = clean_text

    # Extract customer name if specified at the start (e.g. "Satya, ...", "naresh, ...", "Ravi 2 Kings", "Satya-ku ...")
    name_match = re.match(r"^([a-zA-Z]+)(?:-ku|[-–,:]|\s*ku\b)?\s+(.*)$", remaining_text, flags=re.IGNORECASE)
    if not name_match:
        name_match = re.match(r"^([a-zA-Z]+)(?:-ku|[-–,:])\s*(.*)$", remaining_text, flags=re.IGNORECASE)

    if name_match:
        potential_name, rest = name_match.groups()
        known_products = {"filter", "scissor", "kings", "marie", "bingo", "beedi", "yippee", "flag", "gold"}
        if potential_name.lower() not in known_products and potential_name.lower() not in NUMBER_WORDS:
            customer_name = potential_name.capitalize()
            remaining_text = rest

    # Normalize punctuation into comma separation
    normalized = re.sub(r"[,;]+", ",", remaining_text)
    chunks = [c.strip() for c in normalized.split(",") if c.strip()]

    # If no commas, split on number boundaries
    if len(chunks) <= 1:
        pattern = r"(?=(?:^|\s)(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+)"
        raw_parts = re.split(pattern, remaining_text, flags=re.IGNORECASE)
        chunks = [p.strip() for p in raw_parts if p.strip()]

    items: list[RawOrderItem] = []
    for chunk in chunks:
        item = _parse_item_chunk(chunk)
        if item:
            items.append(item)

    return RawExtractedOrder(
        customer_name=customer_name,
        items=items,
        raw_transcript=text,
    )


def _parse_item_chunk(chunk: str) -> RawOrderItem | None:
    """Parse a single line item chunk like 'three Filter', 'kings 1', '1 Scissor piece', 'bingo $5-50', or 'Marie Light five rupees one'."""
    clean = chunk.strip()
    if not clean:
        return None

    # 0. Spoken variant: "<Product> five/ten rupees [qty] [unit]" (e.g. "Bingo five rupees", "Bingo 5 rupees", "Bingo 5 rupees 2", "Marie Light five rupees")
    m_spoken_var = re.match(
        r"^(.*?)\s+(five|ten|5|10)\s*(?:rs|rupees|r|roobai|ரூபாய்)\s*(\d+(?:\.\d+)?|one|two|three|four|five|rendu|oru|moonu)?\s*([a-zA-Z]*)$",
        clean,
        re.IGNORECASE,
    )
    if m_spoken_var:
        prod_base, v_word, q_word, unit_str = m_spoken_var.groups()
        v_num = "5" if v_word.lower() in {"five", "5"} else "10"
        prod_text = f"{prod_base.strip()} ₹{v_num}"
        qty = 1.0
        if q_word:
            qty = NUMBER_WORDS.get(q_word.lower(), float(q_word) if re.match(r"^\d+", q_word) else 1.0)
        unit = unit_str.strip()
        if unit.lower() in UNIT_WORDS:
            unit = UNIT_WORDS[unit.lower()]
        else:
            p_low = prod_base.lower()
            unit = "dozen" if "marie" in p_low else "saram" if "bingo" in p_low else "piece"
        return RawOrderItem(product_text=prod_text, quantity=qty, unit=unit)

    # 1. Shorthand: "<Product> <variant> - <qty> [unit]" (e.g. "bingo $5-50", "bingo 5-50", "bingo ₹5-50", "bingo 5rs-50", "marie 10-5")
    m_var_hyph = re.match(
        r"^(.*?)\s+[$₹]?(\d+)\s*(?:rs|rupees|r|ரூபாய்)?\s*[-–:]\s*(\d+(?:\.\d+)?)\s*([a-zA-Z]*)$",
        clean,
        re.IGNORECASE,
    )
    if m_var_hyph:
        prod_base, variant_val, qty_str, unit_str = m_var_hyph.groups()
        prod_text = f"{prod_base.strip()} ₹{variant_val}"
        qty = float(qty_str)
        unit = unit_str.strip()
        if unit.lower() in UNIT_WORDS:
            unit = UNIT_WORDS[unit.lower()]
        else:
            p_low = prod_base.lower()
            unit = "dozen" if "marie" in p_low else "saram" if "bingo" in p_low else "piece"
        return RawOrderItem(product_text=prod_text, quantity=qty, unit=unit)

    # 2. Shorthand: "<Product> <currency/variant> <qty> [unit]" (e.g. "bingo $5 50", "bingo ₹5 50", "bingo 5rs 50")
    m_var_sp = re.match(
        r"^(.*?)\s+(?:[$₹](\d+)|(\d+)\s*(?:rs|rupees|r|ரூபாய்))\s+(\d+(?:\.\d+)?)\s*([a-zA-Z]*)$",
        clean,
        re.IGNORECASE,
    )
    if m_var_sp:
        prod_base, v1, v2, qty_str, unit_str = m_var_sp.groups()
        v = v1 or v2
        prod_text = f"{prod_base.strip()} ₹{v}"
        qty = float(qty_str)
        unit = unit_str.strip()
        if unit.lower() in UNIT_WORDS:
            unit = UNIT_WORDS[unit.lower()]
        else:
            p_low = prod_base.lower()
            unit = "dozen" if "marie" in p_low else "saram" if "bingo" in p_low else "piece"
        return RawOrderItem(product_text=prod_text, quantity=qty, unit=unit)

    # 3. Shorthand: "<Product> - <qty> [unit]" (e.g. "bingo -16", "flake-5", "filter-1 bundle")
    m_hyph_qty = re.match(
        r"^(.*?)\s*[-–:]\s*(\d+(?:\.\d+)?)\s*([a-zA-Z]*)$",
        clean,
        re.IGNORECASE,
    )
    if m_hyph_qty:
        prod_base, qty_str, unit_str = m_hyph_qty.groups()
        if prod_base.strip():
            unit = unit_str.strip()
            if unit.lower() in UNIT_WORDS:
                unit = UNIT_WORDS[unit.lower()]
            else:
                p_low = prod_base.lower()
                unit = "packet" if "filter" in p_low else "dozen" if "marie" in p_low else "saram" if "bingo" in p_low else "bundle" if "beedi" in p_low else "piece"
            return RawOrderItem(product_text=prod_base.strip(), quantity=float(qty_str), unit=unit)

    # 4. Spoken variant pattern: "<Product> <price variant> <qty>" (e.g. "Marie Light five rupees one", "Bingo five rupees one")
    price_pattern = re.match(
        r"^(.*?)\s+(five|ten|5|10)\s*(?:rupees|rs|ரூபாய்)?\s+(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|oru|rendu|moonu|naalu|anju)$",
        clean,
        re.IGNORECASE,
    )
    if price_pattern:
        prod_name, variant_num, qty_word = price_pattern.groups()
        qty = NUMBER_WORDS.get(qty_word.lower(), float(qty_word) if re.match(r"^\d+", qty_word) else 1.0)
        var_val = NUMBER_WORDS.get(variant_num.lower(), variant_num)
        var_str = f"₹{int(var_val) if isinstance(var_val, float) and var_val.is_integer() else var_val}"
        return RawOrderItem(
            product_text=f"{prod_name.strip()} {var_str}",
            quantity=qty,
            unit="dozen" if "marie" in prod_name.lower() else "saram" if "bingo" in prod_name.lower() else "piece",
        )

    # 5. Check for suffix quantity pattern: "<product> <quantity> [unit]" (e.g. "kings 1", "filter 2", "filter 2 packet")
    suffix_pattern = re.match(
        r"^(.*?)\s+(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|oru|rendu|moonu|naalu|anju)\s*([a-zA-Z]*)$",
        clean,
        re.IGNORECASE,
    )
    # 6. Check for prefix quantity pattern: "<quantity> [unit] <product>" (e.g. "3 filter", "one scissor")
    prefix_pattern = re.match(
        r"^(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|oru|rendu|moonu|naalu|anju)\s*(.*?)$",
        clean,
        re.IGNORECASE,
    )

    qty = 1.0
    unit = "piece"
    prod_text = clean

    if suffix_pattern and not prefix_pattern:
        prod_part, num_part, unit_part = suffix_pattern.groups()
        num_lower = num_part.lower()
        qty = NUMBER_WORDS.get(num_lower, float(num_lower) if re.match(r"^\d+", num_lower) else 1.0)
        prod_text = prod_part.strip()
        if unit_part and unit_part.lower() in UNIT_WORDS:
            unit = UNIT_WORDS[unit_part.lower()]
    elif prefix_pattern:
        num_part, rest_part = prefix_pattern.groups()
        num_lower = num_part.lower()
        qty = NUMBER_WORDS.get(num_lower, float(num_lower) if re.match(r"^\d+", num_lower) else 1.0)
        tokens = rest_part.strip().split()
        prod_tokens: list[str] = []
        for t in tokens:
            if t.lower() in UNIT_WORDS:
                unit = UNIT_WORDS[t.lower()]
            else:
                prod_tokens.append(t)
        prod_text = " ".join(prod_tokens).strip()
    else:
        # Fallback token loop
        tokens = clean.split()
        prod_tokens = []
        for token in tokens:
            t_low = token.lower()
            if t_low in NUMBER_WORDS:
                qty = NUMBER_WORDS[t_low]
            elif re.match(r"^\d+(\.\d+)?$", t_low):
                qty = float(t_low)
            elif t_low in UNIT_WORDS:
                unit = UNIT_WORDS[t_low]
            else:
                prod_tokens.append(token)
        prod_text = " ".join(prod_tokens).strip()

    if not prod_text:
        return None

    # Infer customary units for staple shop products if default 'piece' was kept
    if unit == "piece":
        p_lower = prod_text.lower()
        if "filter" in p_lower:
            unit = "packet"
        elif "marie" in p_lower:
            unit = "dozen"
        elif "bingo" in p_lower:
            unit = "saram"
        elif "beedi" in p_lower:
            unit = "bundle"

    return RawOrderItem(
        product_text=prod_text,
        quantity=qty,
        unit=unit,
    )
