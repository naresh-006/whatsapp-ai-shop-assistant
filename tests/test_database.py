import mongomock
from app.database import (
    check_db_connection,
    get_products_collection,
    get_sales_collection,
    get_users_collection,
    get_audit_logs_collection,
)
import app.database as db_module


def test_db_connection_offline_behavior():
    """Verify check_db_connection returns clean status even when MongoDB is offline."""
    status = check_db_connection()
    assert isinstance(status, dict)
    assert "connected" in status
    assert "database" in status
    assert "error" in status


def test_crud_with_mocked_mongo(monkeypatch):
    """
    Test MongoDB CRUD operations across the initial collections
    (products, sales, users, audit_logs) using mongomock.
    """
    mock_client = mongomock.MongoClient()
    monkeypatch.setattr(db_module, "_client", mock_client)
    monkeypatch.setattr(db_module, "_db", mock_client["shop_assistant_test"])

    # 1. Products collection test
    products_col = get_products_collection()
    product_doc = {
        "product_id": "KINGS",
        "canonical_name": "Kings Triple Two",
        "retail_rate": 222,
        "base_unit": "piece",
        "active": True,
    }
    insert_result = products_col.insert_one(product_doc)
    assert insert_result.inserted_id is not None

    found_product = products_col.find_one({"product_id": "KINGS"})
    assert found_product is not None
    assert found_product["canonical_name"] == "Kings Triple Two"
    assert found_product["retail_rate"] == 222

    # 2. Sales collection test
    sales_col = get_sales_collection()
    sale_doc = {
        "sale_id": "SALE-001",
        "customer_name": "Satya",
        "total": 898,
        "status": "confirmed",
    }
    sales_col.insert_one(sale_doc)
    found_sale = sales_col.find_one({"customer_name": "Satya"})
    assert found_sale is not None
    assert found_sale["total"] == 898

    # 3. Users collection test
    users_col = get_users_collection()
    users_col.insert_one({"user_id": "USER-001", "name": "Mother", "role": "billing"})
    found_user = users_col.find_one({"role": "billing"})
    assert found_user["name"] == "Mother"

    # 4. Audit logs collection test
    audit_col = get_audit_logs_collection()
    audit_col.insert_one({"action": "create_sale", "sale_id": "SALE-001"})
    assert audit_col.count_documents({}) == 1
