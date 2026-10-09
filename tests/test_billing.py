import pytest
import mongomock
from fastapi.testclient import TestClient

from app.main import app
from app.models.billing import (
    BillItemInput,
    InvalidUnitError,
    InvalidQuantityError,
)
from app.services.product_service import seed_real_products, get_product_by_id
from app.services.billing_service import (
    calculate_item_amount,
    calculate_bundle_amount,
    calculate_total,
    calculate_bill,
)
import app.database as db_module

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_mock_db(monkeypatch):
    """Seed real products in in-memory MongoDB before each billing test."""
    mock_client = mongomock.MongoClient()
    monkeypatch.setattr(db_module, "_client", mock_client)
    monkeypatch.setattr(db_module, "_db", mock_client["shop_assistant_test"])
    seed_real_products()
    return mock_client


def test_kings_piece_calculations():
    """Verify Kings piece rates: 1 piece = ₹222, 2 pieces = ₹444."""
    kings = get_product_by_id("KINGS")
    assert kings is not None

    # 1 piece
    item_1 = calculate_item_amount(kings, quantity=1, unit="piece")
    assert item_1.quantity == 1
    assert item_1.rate == 222.0
    assert item_1.amount == 222.0

    # 2 pieces
    item_2 = calculate_item_amount(kings, quantity=2, unit="piece")
    assert item_2.quantity == 2
    assert item_2.rate == 222.0
    assert item_2.amount == 444.0


def test_kings_bundle_calculations():
    """Verify Kings bundle conversion: 1 bundle = 20 pieces = ₹4,440."""
    kings = get_product_by_id("KINGS")

    # 1 bundle
    bundle_1 = calculate_bundle_amount(kings, quantity=1)
    assert bundle_1.quantity == 1
    assert bundle_1.unit == "bundle"
    assert bundle_1.rate == 4440.0
    assert bundle_1.amount == 4440.0
    assert bundle_1.base_quantity == 20

    # 2 bundles
    bundle_2 = calculate_bundle_amount(kings, quantity=2)
    assert bundle_2.amount == 8880.0
    assert bundle_2.base_quantity == 40


def test_kings_mixed_order():
    """
    Verify Section 10 example:
    2 pieces + 3 bundles of Kings = (2 * 222) + (3 * 20 * 222) = 444 + 13,320 = ₹13,764.
    """
    kings = get_product_by_id("KINGS")
    item_pieces = calculate_item_amount(kings, quantity=2, unit="piece")
    item_bundles = calculate_item_amount(kings, quantity=3, unit="bundle")

    total = calculate_total([item_pieces, item_bundles])
    assert item_pieces.amount == 444.0
    assert item_bundles.amount == 13320.0
    assert total == 13764.0


def test_filter_packet_and_bundle_restriction():
    """
    Verify Filter:
    3 packets = 3 * 118 = ₹354.
    Bundle calculation MUST raise error because packet-bundle relationship is undefined.
    """
    filter_prod = get_product_by_id("FILTER")

    # 3 packets
    item_filter = calculate_item_amount(filter_prod, quantity=3, unit="packet")
    assert item_filter.amount == 354.0

    # Bundle price should be blocked
    with pytest.raises(InvalidUnitError) as exc_info:
        calculate_item_amount(filter_prod, quantity=1, unit="bundle")
    assert "undefined" in str(exc_info.value).lower() or "not defined" in str(exc_info.value).lower()


def test_scissor_and_intimate():
    """Verify Scissor and Intimate rates and bundle conversions."""
    scissor = get_product_by_id("SCISSOR")
    intimate = get_product_by_id("INTIMATE")

    # Scissor: 1 piece = ₹100, 1 bundle (50 pcs) = ₹5000
    sc_piece = calculate_item_amount(scissor, quantity=1, unit="piece")
    sc_bundle = calculate_item_amount(scissor, quantity=1, unit="bundle")
    assert sc_piece.amount == 100.0
    assert sc_bundle.amount == 5000.0

    # Intimate: 1 piece = ₹117, 1 bundle (20 pcs) = ₹2340
    int_piece = calculate_item_amount(intimate, quantity=1, unit="piece")
    int_bundle = calculate_item_amount(intimate, quantity=1, unit="bundle")
    assert int_piece.amount == 117.0
    assert int_bundle.amount == 2340.0


def test_bingo_and_marie_light():
    """Verify Bingo and Marie Light rates."""
    b5 = get_product_by_id("BINGO_5")
    b10 = get_product_by_id("BINGO_10")
    m5 = get_product_by_id("MARIE_LIGHT_5")
    m10 = get_product_by_id("MARIE_LIGHT_10")

    assert calculate_item_amount(b5, 1, "saram").amount == 76.0
    assert calculate_item_amount(b5, 3, "saram").amount == 228.0
    assert calculate_item_amount(b10, 1, "saram").amount == 110.0

    assert calculate_item_amount(m5, 1, "dozen").amount == 55.0
    assert calculate_item_amount(m10, 1, "dozen").amount == 110.0


def test_complete_satya_example_bill():
    """
    Verify full real-world Satya order from Architecture Section 5 & 12:
    - Filter 3 Packet: ₹354
    - Scissor 1 Piece: ₹100
    - Kings 2 Piece: ₹444
    - Intimate 1 Piece: ₹117
    - Marie Light ₹5 1 Dozen: ₹55
    - Marie Light ₹10 1 Dozen: ₹110
    - Bingo ₹5 1 Saram: ₹76
    - Bingo ₹10 1 Saram: ₹110
    Grand Total = ₹1,366 exactly.
    """
    items = [
        BillItemInput(product_id="FILTER", quantity=3, unit="packet"),
        BillItemInput(product_id="SCISSOR", quantity=1, unit="piece"),
        BillItemInput(product_id="KINGS", quantity=2, unit="piece"),
        BillItemInput(product_id="INTIMATE", quantity=1, unit="piece"),
        BillItemInput(product_id="MARIE_LIGHT_5", quantity=1, unit="dozen"),
        BillItemInput(product_id="MARIE_LIGHT_10", quantity=1, unit="dozen"),
        BillItemInput(product_id="BINGO_5", quantity=1, unit="saram"),
        BillItemInput(product_id="BINGO_10", quantity=1, unit="saram"),
    ]

    bill = calculate_bill(items=items, customer_name="Satya")
    assert bill.customer_name == "Satya"
    assert bill.total_items == 8
    assert bill.subtotal == 1366.0
    assert bill.grand_total == 1366.0


def test_invalid_quantity_handling():
    """Verify negative and zero quantities raise InvalidQuantityError."""
    kings = get_product_by_id("KINGS")
    with pytest.raises(InvalidQuantityError):
        calculate_item_amount(kings, quantity=0, unit="piece")

    with pytest.raises(InvalidQuantityError):
        calculate_item_amount(kings, quantity=-3, unit="piece")


def test_unknown_unit_handling():
    """Verify unknown or unmapped units raise InvalidUnitError."""
    kings = get_product_by_id("KINGS")
    with pytest.raises(InvalidUnitError):
        calculate_item_amount(kings, quantity=2, unit="litre")

    with pytest.raises(InvalidUnitError):
        calculate_item_amount(kings, quantity=1, unit="meter")


def test_billing_api_endpoint():
    """Verify POST /billing/calculate endpoint."""
    payload = {
        "customer_name": "Satya",
        "items": [
            {"product_id": "FILTER", "quantity": 3, "unit": "packet"},
            {"product_id": "SCISSOR", "quantity": 1, "unit": "piece"},
            {"product_id": "KINGS", "quantity": 2, "unit": "piece"},
        ],
    }
    response = client.post("/billing/calculate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["customer_name"] == "Satya"
    assert data["total_items"] == 3
    # 354 + 100 + 444 = 898
    assert data["grand_total"] == 898.0

    # Error case: unknown unit
    bad_payload = {
        "customer_name": "Test",
        "items": [{"product_id": "KINGS", "quantity": 1, "unit": "kilogram"}],
    }
    bad_res = client.post("/billing/calculate", json=bad_payload)
    assert bad_res.status_code == 400
    assert "not valid" in bad_res.json()["detail"].lower()
