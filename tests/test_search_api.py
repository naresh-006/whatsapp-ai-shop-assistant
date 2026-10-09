import pytest
import mongomock
from fastapi.testclient import TestClient

from app.main import app
from app.services.product_service import seed_all
import app.database as db_module

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_mock_db(monkeypatch):
    """Seed fresh in-memory MongoDB before each search test."""
    mock_client = mongomock.MongoClient()
    monkeypatch.setattr(db_module, "_client", mock_client)
    monkeypatch.setattr(db_module, "_db", mock_client["shop_assistant_test"])
    seed_all(include_dummy=True)
    return mock_client


def test_search_by_exact_product_id():
    """Verify searching by exact product_id returns top score 100."""
    response = client.get("/products/search?q=KINGS")
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "KINGS"
    assert data["total_matches"] >= 1

    top = data["results"][0]
    assert top["product_id"] == "KINGS"
    assert top["canonical_name"] == "Kings Triple Two"
    assert top["rate"] == 222.0
    assert top["unit"] == "piece"
    assert top["match_score"] == 100
    assert "bundle" in top["conversion_rules"]
    assert top["conversion_rules"]["bundle"]["pieces"] == 20
    assert top["conversion_rules"]["bundle"]["rate"] == 4440.0


def test_search_by_alias():
    """Verify searching by spoken alias finds the canonical product."""
    # Search by alias "Triple Two"
    response = client.get("/products/search?q=Triple Two")
    assert response.status_code == 200
    data = response.json()
    assert data["total_matches"] >= 1
    assert data["results"][0]["product_id"] == "KINGS"

    # Search by Tamil alias "கிங்ஸ்"
    response_ta = client.get("/products/search?q=கிங்ஸ்")
    assert response_ta.status_code == 200
    data_ta = response_ta.json()
    assert data_ta["total_matches"] >= 1
    assert data_ta["results"][0]["product_id"] == "KINGS"


def test_search_filter_and_scissor():
    """Verify real family products Filter and Scissor search accurately."""
    # Filter
    res_filter = client.get("/products/search?q=filter")
    assert res_filter.status_code == 200
    top_filter = res_filter.json()["results"][0]
    assert top_filter["product_id"] == "FILTER"
    assert top_filter["rate"] == 118.0
    assert top_filter["unit"] == "packet"

    # Scissor
    res_scissor = client.get("/products/search?q=scissor")
    assert res_scissor.status_code == 200
    top_scissor = res_scissor.json()["results"][0]
    assert top_scissor["product_id"] == "SCISSOR"
    assert top_scissor["rate"] == 100.0
    assert top_scissor["unit"] == "piece"


def test_search_ambiguity_returns_multiple_matches():
    """Verify that ambiguous queries (like 'bingo') return multiple candidate products."""
    res = client.get("/products/search?q=bingo")
    assert res.status_code == 200
    data = res.json()
    # Expect Bingo ₹5, Bingo ₹10, Bingo Tedhe Medhe, Bingo Mad Angles
    assert data["total_matches"] >= 3

    matched_ids = [p["product_id"] for p in data["results"]]
    assert "BINGO_5" in matched_ids
    assert "BINGO_10" in matched_ids


def test_get_product_by_id_endpoint():
    """Verify GET /products/{product_id} returns exact record or 404."""
    # Valid product
    res = client.get("/products/KINGS")
    assert res.status_code == 200
    prod = res.json()
    assert prod["product_id"] == "KINGS"
    assert prod["retail_rate"] == 222.0

    # Non-existent product
    res_404 = client.get("/products/DOES_NOT_EXIST")
    assert res_404.status_code == 404
    assert "not found" in res_404.json()["detail"].lower()


def test_list_products_filtering():
    """Verify GET /products filters by category and dummy flag."""
    # Category filter
    res_tobacco = client.get("/products?category=Tobacco")
    assert res_tobacco.status_code == 200
    for p in res_tobacco.json():
        assert p["category"] == "Tobacco"

    # Real only
    res_real = client.get("/products?is_dummy=false")
    assert res_real.status_code == 200
    assert len(res_real.json()) == 12
