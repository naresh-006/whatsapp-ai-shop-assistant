import pytest
import mongomock
from fastapi.testclient import TestClient

from app.main import app
from app.models.order import RawExtractedOrder, RawOrderItem
from app.services.product_service import seed_real_products
from app.services.resolver_service import (
    resolve_product_text,
    resolve_extracted_order,
    ResolutionStatus,
)
import app.database as db_module

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_mock_db(monkeypatch):
    """Seed real products in in-memory MongoDB before each resolver test."""
    mock_client = mongomock.MongoClient()
    monkeypatch.setattr(db_module, "_client", mock_client)
    monkeypatch.setattr(db_module, "_db", mock_client["shop_assistant_test"])
    seed_real_products()
    return mock_client


def test_exact_id_and_alias_resolution():
    """Verify exact ID and alias mappings (English and Tamil)."""
    # 1. Exact ID
    res_id = resolve_product_text("KINGS")
    assert res_id.status == ResolutionStatus.EXACT_MATCH
    assert res_id.product_id == "KINGS"
    assert res_id.confidence_score == 100

    # 2. English Alias "Kings"
    res_alias = resolve_product_text("Kings")
    assert res_alias.status == ResolutionStatus.EXACT_MATCH
    assert res_alias.product_id == "KINGS"

    # 3. English Alias "Triple Two"
    res_t2 = resolve_product_text("Triple Two")
    assert res_t2.status == ResolutionStatus.EXACT_MATCH
    assert res_t2.product_id == "KINGS"

    # 4. Tamil Alias "கிங்ஸ்"
    res_ta = resolve_product_text("கிங்ஸ்")
    assert res_ta.status == ResolutionStatus.EXACT_MATCH
    assert res_ta.product_id == "KINGS"


def test_staple_products_resolution():
    """Verify Filter and Scissor resolve accurately."""
    res_filter = resolve_product_text("Filter")
    assert res_filter.product_id == "FILTER"
    assert res_filter.retail_rate == 118.0

    res_scissor = resolve_product_text("Scissor")
    assert res_scissor.product_id == "SCISSOR"
    assert res_scissor.retail_rate == 100.0


def test_ambiguity_detection_for_bingo():
    """
    Verify Phase 8 Critical Ambiguity Rule:
    'Bingo' (without ₹5 or ₹10) MUST NOT guess.
    It must return AMBIGUOUS and ask for clarification.
    """
    res_bingo = resolve_product_text("Bingo")
    assert res_bingo.status == ResolutionStatus.AMBIGUOUS
    assert "BINGO_5" in res_bingo.candidate_options
    assert "BINGO_10" in res_bingo.candidate_options
    assert res_bingo.clarification_prompt is not None
    assert "Bingo ₹5" in res_bingo.clarification_prompt
    assert "Bingo ₹10" in res_bingo.clarification_prompt


def test_ambiguity_detection_for_marie_light():
    """Verify 'Marie Light' without ₹5 or ₹10 triggers ambiguity."""
    res_marie = resolve_product_text("Marie Light")
    assert res_marie.status == ResolutionStatus.AMBIGUOUS
    assert "MARIE_LIGHT_5" in res_marie.candidate_options
    assert "MARIE_LIGHT_10" in res_marie.candidate_options


def test_explicit_variant_disambiguation():
    """Verify that specifying the variant (₹5 vs ₹10) resolves unambiguously."""
    res_b5 = resolve_product_text("Bingo ₹5")
    assert res_b5.product_id == "BINGO_5"
    assert res_b5.retail_rate == 76.0

    res_b10 = resolve_product_text("Bingo ₹10")
    assert res_b10.product_id == "BINGO_10"
    assert res_b10.retail_rate == 110.0

    res_m5 = resolve_product_text("Marie Light 5")
    assert res_m5.product_id == "MARIE_LIGHT_5"

    res_m10 = resolve_product_text("Marie Light 10")
    assert res_m10.product_id == "MARIE_LIGHT_10"


def test_fuzzy_matching_handles_typos():
    """Verify fuzzy matching resolves typos like 'Scisor' to SCISSOR."""
    res_typo = resolve_product_text("Scisor")
    assert res_typo.product_id == "SCISSOR"
    assert res_typo.confidence_score >= 75


def test_not_found_handling():
    """Verify completely unknown product returns NOT_FOUND status."""
    res_unknown = resolve_product_text("Unobtainium Widget XYZ")
    assert res_unknown.status == ResolutionStatus.NOT_FOUND
    assert res_unknown.product_id is None
    assert res_unknown.clarification_prompt is not None


def test_batch_extracted_order_resolution():
    """Verify resolve_extracted_order resolves a multi-item extracted order."""
    extracted = RawExtractedOrder(
        customer_name="Satya",
        items=[
            RawOrderItem(product_text="Filter", quantity=3, unit="packet"),
            RawOrderItem(product_text="Kings", quantity=2, unit="piece"),
            RawOrderItem(product_text="Bingo", quantity=1, unit="saram"),  # ambiguous
        ],
    )
    resolved_list = resolve_extracted_order(extracted)
    assert len(resolved_list) == 3
    assert resolved_list[0].product_id == "FILTER"
    assert resolved_list[1].product_id == "KINGS"
    assert resolved_list[2].status == ResolutionStatus.AMBIGUOUS


def test_resolver_api_endpoints():
    """Verify GET /resolver/resolve HTTP endpoint."""
    # 1. Unambiguous query
    res = client.get("/resolver/resolve?q=Kings")
    assert res.status_code == 200
    data = res.json()
    assert data["product_id"] == "KINGS"
    assert data["status"] == "exact_match"

    # 2. Ambiguous query
    res_amb = client.get("/resolver/resolve?q=Bingo")
    assert res_amb.status_code == 200
    amb_data = res_amb.json()
    assert amb_data["status"] == "ambiguous"
    assert len(amb_data["candidate_options"]) >= 2
