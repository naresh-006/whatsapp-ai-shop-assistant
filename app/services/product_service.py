"""Product Service: authoritative catalog operations and seeding."""

import json
import logging
from pathlib import Path
from typing import Any

from app.database import get_products_collection
from app.models.product import ProductCreate, ProductInDB, ProductUpdate

logger = logging.getLogger(__name__)

REAL_SEED_FILE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "seed" / "real_products.json"
DUMMY_SEED_FILE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "seed" / "dummy_products.json"
SEED_FILE_PATH = REAL_SEED_FILE_PATH


def upsert_product(product_data: ProductCreate | dict[str, Any]) -> ProductInDB:
    """
    Insert or update a product by its canonical product_id.
    Validates input using Pydantic before writing to MongoDB.
    """
    if isinstance(product_data, dict):
        product = ProductCreate(**product_data)
    else:
        product = product_data

    collection = get_products_collection()
    doc = product.model_dump()

    collection.update_one(
        {"product_id": product.product_id},
        {"$set": doc},
        upsert=True,
    )
    logger.info("Upserted product: %s (%s)", product.product_id, product.canonical_name)
    return ProductInDB(**doc)


def get_product_by_id(product_id: str) -> ProductInDB | None:
    """Retrieve authoritative product by unique canonical product_id."""
    clean_id = product_id.strip().upper()
    collection = get_products_collection()
    doc = collection.find_one({"product_id": clean_id})
    if not doc:
        return None
    doc.pop("_id", None)
    return ProductInDB(**doc)


def list_products(
    category: str | None = None,
    is_dummy: bool | None = None,
    active_only: bool = True,
) -> list[ProductInDB]:
    """List products with optional category, dummy flag, and active filters."""
    query: dict[str, Any] = {}
    if active_only:
        query["active"] = True
    if category:
        query["category"] = category
    if is_dummy is not None:
        query["is_dummy"] = is_dummy

    collection = get_products_collection()
    results = []
    for doc in collection.find(query).sort("canonical_name", 1):
        doc.pop("_id", None)
        results.append(ProductInDB(**doc))
    return results


def search_products(
    query: str,
    limit: int = 10,
    active_only: bool = True,
    is_dummy: bool | None = None,
) -> list[dict[str, Any]]:
    """
    Search products using authoritative ID, canonical name, and alias matching.
    Returns ranked search result dictionaries with match scores.
    """
    clean = query.strip()
    if not clean:
        return []

    clean_lower = clean.lower()
    clean_upper = clean.upper()

    all_products = list_products(is_dummy=is_dummy, active_only=active_only)
    scored_results = []

    for prod in all_products:
        score = 0
        matched_on = None

        # 1. Exact ID match (KINGS == KINGS)
        if prod.product_id == clean_upper:
            score = 100
            matched_on = f"product_id: {prod.product_id}"

        # 2. Exact Canonical Name match
        elif prod.canonical_name.lower() == clean_lower:
            score = 90
            matched_on = f"canonical_name: {prod.canonical_name}"

        # 3. Exact Alias match (English or Tamil)
        else:
            for alias in prod.aliases:
                if alias.lower() == clean_lower:
                    score = 85
                    matched_on = f"alias: {alias}"
                    break
            if score == 0:
                for t_alias in prod.tamil_aliases:
                    if t_alias.lower() == clean_lower:
                        score = 85
                        matched_on = f"tamil_alias: {t_alias}"
                        break

        # 4. Prefix match
        if score == 0:
            if prod.canonical_name.lower().startswith(clean_lower):
                score = 75
                matched_on = f"name_prefix: {prod.canonical_name}"
            else:
                for alias in prod.aliases + prod.tamil_aliases:
                    if alias.lower().startswith(clean_lower):
                        score = 70
                        matched_on = f"alias_prefix: {alias}"
                        break

        # 5. Substring / Word contains match
        if score == 0:
            if clean_lower in prod.canonical_name.lower():
                score = 60
                matched_on = f"name_contains: {prod.canonical_name}"
            else:
                for alias in prod.aliases + prod.tamil_aliases:
                    if clean_lower in alias.lower():
                        score = 55
                        matched_on = f"alias_contains: {alias}"
                        break

        # 6. Variant or token match
        if score == 0:
            if prod.variant and clean_lower in prod.variant.lower():
                score = 40
                matched_on = f"variant: {prod.variant}"
            else:
                query_tokens = [t for t in clean_lower.split() if len(t) > 1]
                name_tokens = prod.canonical_name.lower().split()
                if any(qt in name_tokens for qt in query_tokens):
                    score = 30
                    matched_on = "token_overlap"

        if score > 0:
            retail_unit_val = prod.retail_unit.value if hasattr(prod.retail_unit, "value") else str(prod.retail_unit)
            base_unit_val = prod.base_unit.value if hasattr(prod.base_unit, "value") else str(prod.base_unit)
            rules = {
                k: v.model_dump() if hasattr(v, "model_dump") else v
                for k, v in prod.conversion_rules.items()
            }
            scored_results.append({
                "product_id": prod.product_id,
                "name": prod.canonical_name,
                "canonical_name": prod.canonical_name,
                "brand": prod.brand,
                "category": prod.category,
                "variant": prod.variant,
                "rate": prod.retail_rate,
                "retail_rate": prod.retail_rate,
                "unit": retail_unit_val,
                "retail_unit": retail_unit_val,
                "base_unit": base_unit_val,
                "conversion_rules": rules,
                "is_dummy": prod.is_dummy,
                "match_score": score,
                "matched_on": matched_on,
            })

    # Sort: highest score first, real before dummy, then name
    scored_results.sort(key=lambda x: (-x["match_score"], x["is_dummy"], x["name"]))
    return scored_results[:limit]



def seed_real_products(file_path: Path = REAL_SEED_FILE_PATH) -> int:
    """
    Load real family shop catalog from JSON and upsert into MongoDB.
    Ensures is_dummy=False for all real items.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Real seed file not found at: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    count = 0
    for item in data:
        item["is_dummy"] = False
        upsert_product(item)
        count += 1

    logger.info("Successfully seeded %d real products into MongoDB.", count)
    return count


def seed_dummy_products(
    file_path: Path = DUMMY_SEED_FILE_PATH,
    clear_existing_dummy: bool = False,
) -> int:
    """
    Load large realistic dummy catalog and upsert into MongoDB.
    Strictly forces is_dummy=True on all items to prevent mixing with real rates.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Dummy seed file not found at: {file_path}")

    collection = get_products_collection()
    if clear_existing_dummy:
        deleted = collection.delete_many({"is_dummy": True})
        logger.info("Cleared %d existing dummy products.", deleted.deleted_count)

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    count = 0
    for item in data:
        item["is_dummy"] = True
        upsert_product(item)
        count += 1

    logger.info("Successfully seeded %d dummy products into MongoDB.", count)
    return count


def clear_dummy_products() -> int:
    """Delete all dummy products from MongoDB, leaving only real family items."""
    collection = get_products_collection()
    result = collection.delete_many({"is_dummy": True})
    logger.info("Deleted %d dummy products from MongoDB.", result.deleted_count)
    return result.deleted_count


def seed_all(include_dummy: bool = True) -> dict[str, int]:
    """Seed both real family catalog and dummy catalog."""
    real_count = seed_real_products()
    dummy_count = seed_dummy_products() if include_dummy else 0
    return {"real": real_count, "dummy": dummy_count, "total": real_count + dummy_count}


if __name__ == "__main__":
    import sys
    from app.database import check_db_connection

    print("Verifying MongoDB connection before seeding...")
    status = check_db_connection()
    if not status["connected"]:
        print(f"ERROR: Cannot connect to MongoDB at: {status['database']}")
        print(f"Detail: {status['error']}")
        sys.exit(1)

    args = sys.argv[1:]
    if "--clear-dummy" in args:
        deleted = clear_dummy_products()
        print(f"SUCCESS: Cleared {deleted} dummy products from database.")
    elif "--real-only" in args:
        count = seed_real_products()
        print(f"SUCCESS: Seeded {count} real products.")
    else:
        results = seed_all(include_dummy=True)
        print(f"SUCCESS: Seeded {results['real']} real products and {results['dummy']} dummy products. Total: {results['total']}.")
