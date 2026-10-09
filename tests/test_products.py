import json
from pathlib import Path
import pytest
import mongomock
from pydantic import ValidationError

from app.models.product import (
    ProductCreate,
    ProductInDB,
    UnitType,
    ConversionRule,
)
from app.services.product_service import (
    upsert_product,
    get_product_by_id,
    list_products,
    seed_real_products,
    SEED_FILE_PATH,
)
import app.database as db_module


@pytest.fixture(autouse=True)
def mock_mongo(monkeypatch):
    """Provide isolated in-memory MongoDB for all product tests."""
    client = mongomock.MongoClient()
    monkeypatch.setattr(db_module, "_client", client)
    monkeypatch.setattr(db_module, "_db", client["shop_assistant_test"])
    return client


def test_product_schema_validation():
    """Verify validation constraints on Product model."""
    # Valid product
    p = ProductCreate(
        product_id="kings",
        canonical_name="Kings Triple Two",
        category="Tobacco",
        retail_unit=UnitType.PIECE,
        base_unit=UnitType.PIECE,
        retail_rate=222.0,
        conversion_rules={"bundle": ConversionRule(pieces=20, rate=4440.0)},
    )
    # product_id normalized to uppercase
    assert p.product_id == "KINGS"
    assert p.retail_rate == 222.0
    assert p.conversion_rules["bundle"].pieces == 20
    assert p.conversion_rules["bundle"].rate == 4440.0

    # Negative retail_rate should fail
    with pytest.raises(ValidationError):
        ProductCreate(
            product_id="TEST",
            canonical_name="Test",
            category="Tobacco",
            retail_unit=UnitType.PIECE,
            base_unit=UnitType.PIECE,
            retail_rate=-50.0,
        )

    # Empty product_id should fail
    with pytest.raises(ValidationError):
        ProductCreate(
            product_id="   ",
            canonical_name="Test",
            category="Tobacco",
            retail_unit=UnitType.PIECE,
            base_unit=UnitType.PIECE,
            retail_rate=100.0,
        )


def test_seed_file_integrity():
    """Verify that real_products.json is valid and parseable by Pydantic."""
    assert SEED_FILE_PATH.exists()
    with open(SEED_FILE_PATH, "r", encoding="utf-8") as f:
        items = json.load(f)

    assert len(items) == 12
    product_ids = set()
    for item in items:
        prod = ProductCreate(**item)
        assert prod.product_id not in product_ids, f"Duplicate product_id: {prod.product_id}"
        product_ids.add(prod.product_id)

    # Verify key family products are in the seed
    expected_ids = {
        "FILTER",
        "KINGS",
        "SCISSOR",
        "INTIMATE",
        "FLAG",
        "MARIE_LIGHT_5",
        "MARIE_LIGHT_10",
        "YIPPEE_NOODLES",
        "YIPPEE_FAMILY_PACK",
        "BEEDI",
        "BINGO_5",
        "BINGO_10",
    }
    assert expected_ids.issubset(product_ids)


def test_seed_and_retrieval_service():
    """Verify seeding into database and querying by ID and category."""
    count = seed_real_products()
    assert count == 12

    # Query KINGS
    kings = get_product_by_id("kings")
    assert kings is not None
    assert kings.product_id == "KINGS"
    assert kings.canonical_name == "Kings Triple Two"
    assert kings.retail_rate == 222.0
    assert kings.retail_unit == UnitType.PIECE
    assert "bundle" in kings.conversion_rules
    assert kings.conversion_rules["bundle"].pieces == 20
    assert kings.conversion_rules["bundle"].rate == 4440.0

    # Query Filter
    filter_prod = get_product_by_id("FILTER")
    assert filter_prod is not None
    assert filter_prod.retail_rate == 118.0
    assert filter_prod.retail_unit == UnitType.PACKET

    # Query Marie Light 5 and 10
    m5 = get_product_by_id("MARIE_LIGHT_5")
    m10 = get_product_by_id("MARIE_LIGHT_10")
    assert m5.retail_rate == 55.0
    assert m10.retail_rate == 110.0

    # Query Bingo 5 and 10
    b5 = get_product_by_id("BINGO_5")
    b10 = get_product_by_id("BINGO_10")
    assert b5.retail_rate == 76.0
    assert b10.retail_rate == 110.0

    # Category filtering
    tobacco_products = list_products(category="Tobacco")
    assert len(tobacco_products) >= 5
    for p in tobacco_products:
        assert p.category == "Tobacco"

    # Non-existent product
    assert get_product_by_id("UNKNOWN_XYZ") is None
