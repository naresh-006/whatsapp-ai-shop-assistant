import pytest
import mongomock
from fastapi.testclient import TestClient

from app.main import app
from app.models.order import (
    OrderStatus,
    RawOrderItem,
    RawExtractedOrder,
)
from app.services.product_service import seed_real_products
from app.services.order_service import (
    create_order,
    get_order,
    add_item_to_order,
    update_item_quantity,
    remove_item_from_order,
    confirm_order,
    cancel_order,
)
import app.database as db_module

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_mock_db(monkeypatch):
    """Seed real products in in-memory MongoDB before each order test."""
    mock_client = mongomock.MongoClient()
    monkeypatch.setattr(db_module, "_client", mock_client)
    monkeypatch.setattr(db_module, "_db", mock_client["shop_assistant_test"])
    seed_real_products()
    return mock_client


def test_raw_order_models_validation():
    """Verify RawOrderItem and RawExtractedOrder models parse accurately."""
    extracted = RawExtractedOrder(
        customer_name="Satya",
        items=[
            RawOrderItem(product_text="Filter", quantity=3, unit="packet"),
            RawOrderItem(product_text="Scissor", quantity=1, unit="piece"),
            RawOrderItem(product_text="Kings", quantity=2, unit="piece"),
        ],
        raw_transcript="Satya three Filter one Scissor two Kings",
    )
    assert extracted.customer_name == "Satya"
    assert len(extracted.items) == 3
    assert extracted.items[0].product_text == "Filter"
    assert extracted.items[0].quantity == 3


def test_order_lifecycle_creation_and_resolution():
    """Verify order creation resolves canonical IDs and calculates initial bill."""
    raw_items = [
        RawOrderItem(product_text="Filter", quantity=3, unit="packet"),
        RawOrderItem(product_text="Scissor", quantity=1, unit="piece"),
        RawOrderItem(product_text="Kings", quantity=2, unit="piece"),
    ]

    order = create_order(session_id="9876543210", customer_name="Satya", raw_items=raw_items)
    assert order.status == OrderStatus.PENDING_CONFIRMATION
    assert order.customer_name == "Satya"
    assert len(order.items) == 3

    # Check calculated bill
    assert order.calculated_bill is not None
    # Filter 354 + Scissor 100 + Kings 444 = 898
    assert order.calculated_bill.grand_total == 898.0


def test_conversational_corrections_flow():
    """
    Test Phase 10 & 13 conversational modifications on a structured order:
    1. Start: Filter (3), Scissor (1), Kings (2) = ₹898
    2. 'Change Filter to five' -> Filter (5) = ₹590, Total = ₹1,134
    3. 'Remove Kings' -> Total = 590 + 100 = ₹690
    4. 'Add one Marie Light ₹5' -> Total = 690 + 55 = ₹745
    """
    order = create_order(
        session_id="test_session",
        customer_name="Satya",
        raw_items=[
            RawOrderItem(product_text="Filter", quantity=3, unit="packet"),
            RawOrderItem(product_text="Scissor", quantity=1, unit="piece"),
            RawOrderItem(product_text="Kings", quantity=2, unit="piece"),
        ],
    )
    assert order.calculated_bill.grand_total == 898.0

    # Step 2: Change Filter to 5
    order = update_item_quantity(order.order_id, product_id_or_text="Filter", new_quantity=5.0)
    # 5 * 118 = 590; 590 + 100 + 444 = 1134
    assert order.calculated_bill.grand_total == 1134.0

    # Step 3: Remove Kings
    order = remove_item_from_order(order.order_id, product_id_or_text="Kings")
    assert len(order.items) == 2
    # 590 + 100 = 690
    assert order.calculated_bill.grand_total == 690.0

    # Step 4: Add Marie Light ₹5
    order = add_item_to_order(
        order.order_id,
        RawOrderItem(product_text="Marie Light ₹5", quantity=1, unit="dozen"),
    )
    assert len(order.items) == 3
    # 690 + 55 = 745
    assert order.calculated_bill.grand_total == 745.0


def test_order_confirmation_and_cancellation():
    """Verify order state transitions to CONFIRMED or CANCELLED."""
    order = create_order(
        session_id="session_confirm",
        customer_name="Kumar",
        raw_items=[RawOrderItem(product_text="Scissor", quantity=2, unit="piece")],
    )
    assert order.status == OrderStatus.PENDING_CONFIRMATION

    # Confirm
    confirmed = confirm_order(order.order_id)
    assert confirmed.status == OrderStatus.CONFIRMED

    # Cancel a second order
    order2 = create_order(
        session_id="session_cancel",
        raw_items=[RawOrderItem(product_text="Filter", quantity=1, unit="packet")],
    )
    cancelled = cancel_order(order2.order_id)
    assert cancelled.status == OrderStatus.CANCELLED


def test_orders_api_endpoints():
    """Verify full HTTP lifecycle on /orders endpoints."""
    # 1. Create order
    create_payload = {
        "session_id": "whatsapp:+919876543210",
        "customer_name": "Ravi",
        "raw_items": [
            {"product_text": "Scissor", "quantity": 1, "unit": "piece"},
            {"product_text": "Kings", "quantity": 1, "unit": "piece"},
        ],
    }
    res = client.post("/orders", json=create_payload)
    assert res.status_code == 200
    order_data = res.json()
    order_id = order_data["order_id"]
    # 100 + 222 = 322
    assert order_data["calculated_bill"]["grand_total"] == 322.0

    # 2. Patch item quantity
    patch_res = client.patch(
        f"/orders/{order_id}/items",
        json={"product_id_or_text": "Kings", "new_quantity": 2.0},
    )
    assert patch_res.status_code == 200
    # 100 + (2 * 222) = 544
    assert patch_res.json()["calculated_bill"]["grand_total"] == 544.0

    # 3. Confirm order
    confirm_res = client.post(f"/orders/{order_id}/confirm")
    assert confirm_res.status_code == 200
    assert confirm_res.json()["status"] == "confirmed"
