"""Product Resolver: maps raw spoken/typed text into canonical product IDs with ambiguity detection."""

from difflib import SequenceMatcher
from enum import Enum
import logging
from typing import Any
from pydantic import BaseModel, Field

from app.models.product import ProductInDB
from app.models.order import RawOrderItem, RawExtractedOrder
from app.services.product_service import list_products, get_product_by_id

logger = logging.getLogger(__name__)


class ResolutionStatus(str, Enum):
    """Classification of resolution outcome."""
    EXACT_MATCH = "exact_match"
    CONFIDENT_MATCH = "confident_match"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"


class ResolutionResult(BaseModel):
    """Outcome of resolving a single product text query."""
    query_text: str
    status: ResolutionStatus
    product_id: str | None = None
    canonical_name: str | None = None
    retail_rate: float | None = None
    retail_unit: str | None = None
    confidence_score: int
    matched_by: str | None = None
    candidate_options: list[str] = Field(default_factory=list, description="Product IDs of candidate options")
    candidate_names: list[str] = Field(default_factory=list, description="Display names of candidate options")
    clarification_prompt: str | None = None


def resolve_product_text(query: str, active_only: bool = True) -> ResolutionResult:
    """
    Deterministically resolve raw product text into a canonical product record.

    Resolution Hierarchy:
    1. Exact Canonical ID (case-insensitive)
    2. Exact Canonical Name (case-insensitive)
    3. Exact English or Tamil Alias
    4. Explicit Variant Matching (e.g. 'Bingo 5' -> BINGO_5)
    5. Ambiguity Detection (e.g. 'Bingo' -> BINGO_5 vs BINGO_10)
    6. Fuzzy / Typo Matching (e.g. 'Scisor' -> SCISSOR)
    7. Not Found
    """
    clean = query.strip()
    if not clean:
        return ResolutionResult(
            query_text=query,
            status=ResolutionStatus.NOT_FOUND,
            confidence_score=0,
            clarification_prompt="Empty product query provided.",
        )

    import re

    clean_lower = clean.lower()
    clean_upper = clean.upper()

    # Normalize currency symbols and spoken price variants:
    norm_text = clean_lower.replace("$", "₹")

    # Convert spoken price numbers (five rupees, 5 rupees, ten rs) to standard ₹5, ₹10
    word_to_num = {
        "five": "5", "ten": "10", "ainthu": "5", "pathu": "10", "ஐந்து": "5", "பத்து": "10"
    }
    for w, n in word_to_num.items():
        norm_text = re.sub(rf"\b{w}\s*(?:rs|rupees|r|roobai|ரூபாய்)?\b", rf"₹{n}", norm_text, flags=re.IGNORECASE)
    norm_text = re.sub(r"\b(\d+)\s*(?:rs|rupees|r|roobai|ரூபாய்)\b", r"₹\1", norm_text, flags=re.IGNORECASE)

    # If phrasing is "5 rupees bingo" or "five rupees bingo", canonicalize to "bingo ₹5"
    if "bingo" in norm_text:
        if "₹5" in norm_text or re.search(r"\b5\b", norm_text):
            norm_text = "bingo ₹5"
        elif "₹10" in norm_text or re.search(r"\b10\b", norm_text):
            norm_text = "bingo ₹10"
    elif "marie" in norm_text:
        if "₹5" in norm_text or re.search(r"\b5\b", norm_text):
            norm_text = "marie light ₹5"
        elif "₹10" in norm_text or re.search(r"\b10\b", norm_text):
            norm_text = "marie light ₹10"

    all_products = list_products(active_only=active_only)

    # 1. Exact Product ID
    for prod in all_products:
        if prod.product_id == clean_upper:
            return _build_match(clean, prod, 100, ResolutionStatus.EXACT_MATCH, "exact_product_id")

    # 2. Exact Canonical Name (original or normalized)
    for prod in all_products:
        p_canon = prod.canonical_name.lower()
        if p_canon in {clean_lower, norm_text}:
            return _build_match(clean, prod, 95, ResolutionStatus.EXACT_MATCH, "exact_canonical_name")

    # 3. Exact Alias (English & Tamil)
    for prod in all_products:
        for alias in prod.aliases:
            a_low = alias.lower()
            if a_low in {clean_lower, norm_text}:
                return _build_match(clean, prod, 90, ResolutionStatus.EXACT_MATCH, f"exact_alias: '{alias}'")
        for t_alias in prod.tamil_aliases:
            t_low = t_alias.lower()
            if t_low in {clean_lower, norm_text}:
                return _build_match(clean, prod, 90, ResolutionStatus.EXACT_MATCH, f"exact_tamil_alias: '{t_alias}'")

    # 4. Check for Ambiguity among close family candidates (e.g. 'Bingo', 'Marie Light', 'Yippee')
    ambiguity_candidates = _check_known_ambiguities(clean_lower, all_products)
    if ambiguity_candidates:
        cand_ids = [c.product_id for c in ambiguity_candidates]
        cand_names = [c.canonical_name for c in ambiguity_candidates]
        options_text = " or ".join(cand_names)
        return ResolutionResult(
            query_text=clean,
            status=ResolutionStatus.AMBIGUOUS,
            confidence_score=50,
            matched_by="multiple_candidates",
            candidate_options=cand_ids,
            candidate_names=cand_names,
            clarification_prompt=f"Do you mean {options_text}?",
        )

    # 5. Fuzzy and Word-Boundary Matching
    best_prod = None
    best_score = 0
    matched_reason = None

    for prod in all_products:
        # Check similarity with canonical name
        sim_name = int(SequenceMatcher(None, clean_lower, prod.canonical_name.lower()).ratio() * 100)
        if sim_name > best_score and sim_name >= 75:
            best_score = sim_name
            best_prod = prod
            matched_reason = f"fuzzy_name ({sim_name}%)"

        # Check similarity with all aliases
        for alias in prod.aliases + prod.tamil_aliases:
            sim_alias = int(SequenceMatcher(None, clean_lower, alias.lower()).ratio() * 100)
            if sim_alias > best_score and sim_alias >= 75:
                best_score = sim_alias
                best_prod = prod
                matched_reason = f"fuzzy_alias: '{alias}' ({sim_alias}%)"

    if best_prod and best_score >= 75:
        status = ResolutionStatus.CONFIDENT_MATCH if best_score < 90 else ResolutionStatus.EXACT_MATCH
        return _build_match(clean, best_prod, best_score, status, matched_reason)

    # 6. Fallback: Not Found
    return ResolutionResult(
        query_text=clean,
        status=ResolutionStatus.NOT_FOUND,
        confidence_score=0,
        clarification_prompt=f"Could not identify product '{clean}'. Please verify product name.",
    )


def resolve_extracted_order(extracted_order: RawExtractedOrder) -> list[ResolutionResult]:
    """Resolve all raw items in an extracted order."""
    results = []
    for item in extracted_order.items:
        res = resolve_product_text(item.product_text)
        results.append(res)
    return results


# ------------------ Internal Helpers ------------------

def _build_match(
    query: str,
    prod: ProductInDB,
    score: int,
    status: ResolutionStatus,
    matched_by: str,
) -> ResolutionResult:
    retail_unit_val = prod.retail_unit.value if hasattr(prod.retail_unit, "value") else str(prod.retail_unit)
    return ResolutionResult(
        query_text=query,
        status=status,
        product_id=prod.product_id,
        canonical_name=prod.canonical_name,
        retail_rate=prod.retail_rate,
        retail_unit=retail_unit_val,
        confidence_score=score,
        matched_by=matched_by,
        candidate_options=[prod.product_id],
        candidate_names=[prod.canonical_name],
    )


def _check_known_ambiguities(clean_lower: str, all_products: list[ProductInDB]) -> list[ProductInDB] | None:
    """
    Detect whether query is intentionally ambiguous (e.g. user just said 'Bingo' or 'Marie Light').
    Returns list of candidate products if ambiguous, or None if unambiguous.
    """
    # Case: "bingo" without 5 or 10
    if clean_lower == "bingo" or clean_lower == "bingo saram":
        bingos = [p for p in all_products if p.product_id in {"BINGO_5", "BINGO_10"}]
        if len(bingos) >= 2:
            return bingos

    # Case: "marie" or "marie light" without 5 or 10
    if clean_lower in {"marie", "marie light", "marie biscuit"}:
        maries = [p for p in all_products if p.product_id in {"MARIE_LIGHT_5", "MARIE_LIGHT_10"}]
        if len(maries) >= 2:
            return maries

    # Case: "yippee" without specifying regular or family pack
    if clean_lower == "yippee":
        yippees = [p for p in all_products if p.product_id in {"YIPPEE_NOODLES", "YIPPEE_FAMILY_PACK"}]
        if len(yippees) >= 2:
            return yippees

    return None
