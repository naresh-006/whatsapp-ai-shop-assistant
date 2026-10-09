import json
from pathlib import Path
import pytest
import mongomock

from app.models.product import ProductCreate
from app.services.product_service import (
    seed_real_products,
    seed_dummy_products,
    seed_all,
    clear_dummy_products,
    list_products,
    get_product_by_id,
    REAL_SEED_FILE_PATH,
    DUMMY_SEED_FILE_PATH,
)
import app.database as db_module


@pytest.fixture(autouse=True)
def mock_mongo(monkeypatch):
    """Provide isolated in-memory MongoDB for dummy catalog tests."""
    client = mongomock.MongoClient()
    monkeypatch.setattr(db_module, "_client", client)
    monkeypatch.setattr(db_module, "_db", client["shop_assistant_test"])
    return client


def test_dummy_catalog_file_integrity():
    """Verify dummy_products.json is valid, parsed by Pydantic, and has 100+ items."""
    assert DUMMY_SEED_FILE_PATH.exists(), "Dummy catalog file must exist"
    with open(DUMMY_SEED_FILE_PATH, "r", encoding="utf-8") as f:
        items = json.load(f)

    assert len(items) >= 100, f"Expected 100+ dummy items, got {len(items)}"

    dummy_ids = set()
    for item in items:
        # Pydantic schema validation
        product = ProductCreate(**item)
        assert product.is_dummy is True, f"Product {product.product_id} must have is_dummy=True"
        assert product.product_id not in dummy_ids, f"Duplicate dummy product_id: {product.product_id}"
        dummy_ids.add(product.product_id)
        assert len(product.aliases) >= 1, f"Product {product.product_id} should have aliases"


def test_no_id_collision_between_real_and_dummy():
    """Verify that no dummy product ID collides with real family product IDs."""
    with open(REAL_SEED_FILE_PATH, "r", encoding="utf-8") as f:
        real_items = json.load(f)
    with open(DUMMY_SEED_FILE_PATH, "r", encoding="utf-8") as f:
        dummy_items = json.load(f)

    real_ids = {item["product_id"].upper() for item in real_items}
    dummy_ids = {item["product_id"].upper() for item in dummy_items}

    overlap = real_ids.intersection(dummy_ids)
    assert len(overlap) == 0, f"ID collision between real and dummy products: {overlap}"


def test_seed_isolation_and_clearing():
    """Verify that dummy data can be seeded and cleared without affecting real data."""
    results = seed_all(include_dummy=True)
    assert results["real"] == 12
    assert results["dummy"] >= 100
    assert results["total"] == results["real"] + results["dummy"]

    # Filter by real only
    real_products = list_products(is_dummy=False)
    assert len(real_products) == 12
    for p in real_products:
        assert p.is_dummy is False

    # Filter by dummy only
    dummy_products = list_products(is_dummy=True)
    assert len(dummy_products) == results["dummy"]
    for p in dummy_products:
        assert p.is_dummy is True

    # Real product KINGS exists with real price
    kings = get_product_by_id("KINGS")
    assert kings is not None
    assert kings.retail_rate == 222.0
    assert kings.is_dummy is False

    # Clear dummy data
    deleted_count = clear_dummy_products()
    assert deleted_count == results["dummy"]

    # Only real products remain
    remaining = list_products()
    assert len(remaining) == 12
    assert get_product_by_id("KINGS") is not None
    assert get_product_by_id("PARLE_G_5") is None


def test_realistic_ambiguity_in_catalog():
    """Verify that catalog contains realistic product ambiguity (e.g. multiple Bingos, Maries)."""
    seed_all(include_dummy=True)
    all_products = list_products()

    # Ambiguity 1: Multiple Bingo snack products
    bingo_items = [p for p in all_products if "bingo" in p.canonical_name.lower()]
    assert len(bingo_items) >= 4, "Expected at least 4 Bingo items to stress-test ambiguity"

    # Ambiguity 2: Multiple Marie products
    marie_items = [p for p in all_products if "marie" in p.canonical_name.lower()]
    assert len(marie_items) >= 3, "Expected at least 3 Marie items to stress-test ambiguity"

    # Ambiguity 3: Multiple Lays products
    lays_items = [p for p in all_products if "lay's" in p.canonical_name.lower() or "lays" in p.canonical_name.lower()]
    assert len(lays_items) >= 3, "Expected at least 3 Lay's variants"
