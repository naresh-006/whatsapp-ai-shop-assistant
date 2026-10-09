"""Automated tests for Phases 9 through 13: End-to-end MVP, sales persistence, search, and daily reports."""

import pytest
import mongomock
from fastapi.testclient import TestClient

from app.main import app
from app.models.order import OrderStatus
from app.services.product_service import seed_real_products, get_product_by_id, upsert_product
from app.services.pipeline_service import (
    process_natural_language_order,
    apply_conversational_correction,
)
from app.services.sales_service import (
    save_confirmed_sale,
    get_sale_by_invoice,
    search_sales_by_customer,
    get_sales_by_product,
    get_sales_for_today,
    get_daily_sales_summary,
)
import app.database as db_module

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_mock_db(monkeypatch):
    """Seed real products in in-memory MongoDB before each pipeline/sales test."""
    mock_client = mongomock.MongoClient()
    monkeypatch.setattr(db_module, "_client", mock_client)
    monkeypatch.setattr(db_module, "_db", mock_client["shop_assistant_test"])
    seed_real_products()
    return mock_client


# ==============================================================================
# PHASE 9: AI Order -> Database -> Draft Bill Pipeline
# ==============================================================================

def test_phase9_canonical_order_pipeline():
    """
    Verify Phase 9 input:
    'Satya, three Filter, one Scissor, two Kings'
    -> Filter: 3 x 118 = 354
    -> Scissor: 1 x 100 = 100
    -> Kings: 2 x 222 = 444
    -> Total = 898
    """
    order = process_natural_language_order(
        transcript="Satya, three Filter, one Scissor, two Kings",
        session_id="session_satya",
    )

    assert order.customer_name == "Satya"
    assert order.status == OrderStatus.PENDING_CONFIRMATION
    assert len(order.items) == 3
    assert order.calculated_bill is not None
    assert order.calculated_bill.grand_total == 898.0

    # Test via HTTP endpoint
    response = client.post(
        "/pipeline/process",
        json={
            "transcript": "Satya, three Filter, one Scissor, two Kings",
            "session_id": "session_http",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["customer_name"] == "Satya"
    assert data["calculated_bill"]["grand_total"] == 898.0


# ==============================================================================
# PHASE 10: Draft Bill and Conversational Corrections
# ==============================================================================

def test_phase10_conversational_corrections():
    """
    Verify Phase 10: Mother corrects the draft bill naturally:
    1. 'Change Filter to 5' -> Grand Total updates from 898 to 1134.
    2. 'Remove Kings' -> Grand Total updates from 1134 to 690.
    """
    session = "session_correction_test"
    order = process_natural_language_order(
        transcript="Satya, three Filter, one Scissor, two Kings",
        session_id=session,
    )
    assert order.calculated_bill.grand_total == 898.0

    # 1. Correction: Change Filter to five
    updated_order = apply_conversational_correction(
        session_id=session,
        correction_text="Change Filter to five",
    )
    # Filter 5 * 118 = 590; Scissor 100; Kings 444 = 1134
    assert updated_order.calculated_bill.grand_total == 1134.0

    # 2. Correction: Remove Kings
    updated_order_2 = apply_conversational_correction(
        session_id=session,
        correction_text="Remove Kings",
    )
    assert len(updated_order_2.items) == 2
    # Filter 590 + Scissor 100 = 690
    assert updated_order_2.calculated_bill.grand_total == 690.0

    # Test HTTP endpoint
    res = client.post(
        "/pipeline/correct",
        json={"session_id": session, "correction": "Change Scissor to 2"},
    )
    assert res.status_code == 200
    # Filter 590 + Scissor 2*100 = 790
    assert res.json()["calculated_bill"]["grand_total"] == 790.0


def test_phase10_ambiguity_clarification_loop():
    """
    Verify Phase 10 Ambiguity loop:
    1. Order contains ambiguous product 'Bingo' without variant.
    2. Order pauses with status NEEDS_CLARIFICATION.
    3. User clarifies 'Bingo ₹5'.
    4. Order resumes with status PENDING_CONFIRMATION and exact bill calculated.
    """
    session = "session_ambiguity_loop"
    order = process_natural_language_order(
        transcript="Kumar 1 Bingo saram",
        session_id=session,
    )
    assert order.status == OrderStatus.NEEDS_CLARIFICATION
    assert order.clarification_prompt is not None

    # Clarification provided by user
    clarified = apply_conversational_correction(
        session_id=session,
        correction_text="Bingo ₹5",
    )
    assert clarified.status == OrderStatus.PENDING_CONFIRMATION
    assert clarified.calculated_bill is not None
    assert clarified.calculated_bill.grand_total == 76.0


# ==============================================================================
# PHASE 11: Save Confirmed Sale & Snapshot Immutability
# ==============================================================================

def test_phase11_save_confirmed_sale_and_price_snapshot_immutability():
    """
    Verify Phase 11:
    1. Confirm order and save to sales collection.
    2. Receives sequential invoice number INV-001.
    3. Price snapshot test: If product rate changes tomorrow, yesterday's bill MUST NOT change.
    """
    order = process_natural_language_order(
        transcript="Satya, three Filter, one Scissor, two Kings",
        session_id="session_save_test",
    )
    from app.services.order_service import confirm_order
    confirmed_order = confirm_order(order.order_id)

    sale = save_confirmed_sale(confirmed_order, created_by="Mother", customer_phone="+919876543210")
    assert sale.invoice_number == "INV-001"
    assert sale.customer_name == "Satya"
    assert sale.total == 898.0
    assert len(sale.items) == 3

    # Snapshot check: Kings rate is 222 in the sale
    kings_snapshot = next(item for item in sale.items if item.product_id == "KINGS")
    assert kings_snapshot.rate == 222.0

    # SIMULATE TOMORROW: Product rate for Kings increases to ₹300 in MongoDB
    kings_prod = get_product_by_id("KINGS")
    kings_prod.retail_rate = 300.0
    upsert_product(kings_prod)

    # Verify yesterday's saved sale retains original rate ₹222 and original total ₹898
    retrieved_sale = get_sale_by_invoice("INV-001")
    assert retrieved_sale is not None
    assert retrieved_sale.total == 898.0
    retrieved_kings = next(item for item in retrieved_sale.items if item.product_id == "KINGS")
    assert retrieved_kings.rate == 222.0


# ==============================================================================
# PHASE 12: Father's Sales Search
# ==============================================================================

def test_phase12_fathers_sales_search():
    """
    Verify Phase 12:
    Father queries:
    - 'What did Satya buy today?'
    - 'Show invoice INV-001'
    - 'Who bought Bingo today?'
    """
    # Create and save 2 sales
    order1 = process_natural_language_order("Satya, three Filter, one Scissor, two Kings", "s1")
    from app.services.order_service import confirm_order
    save_confirmed_sale(confirm_order(order1.order_id))  # INV-001

    order2 = process_natural_language_order("Ravi 2 Bingo ₹5", "s2")
    save_confirmed_sale(confirm_order(order2.order_id))  # INV-002

    # Query 1: Father asks for Satya
    satya_sales = search_sales_by_customer("Satya")
    assert len(satya_sales) == 1
    assert satya_sales[0].customer_name == "Satya"
    assert satya_sales[0].total == 898.0
    assert len(satya_sales[0].items) == 3

    # Query 2: Search by Invoice
    sale_inv1 = get_sale_by_invoice("INV-001")
    assert sale_inv1 is not None
    assert sale_inv1.invoice_number == "INV-001"

    # Query 3: Search who bought Bingo
    bingo_sales = get_sales_by_product("BINGO_5")
    assert len(bingo_sales) == 1
    assert bingo_sales[0].customer_name == "Ravi"

    # Test HTTP endpoint
    res_customer = client.get("/sales/customer/Satya")
    assert res_customer.status_code == 200
    assert len(res_customer.json()) == 1
    assert res_customer.json()[0]["total"] == 898.0


# ==============================================================================
# PHASE 13: Daily Sales Reports
# ==============================================================================

def test_phase13_daily_sales_reports():
    """
    Verify Phase 13:
    Father asks: 'How many sales today? What is today's total sales?'
    Database aggregates:
    - Total Revenue
    - Total Bills
    - Total Customers
    - Customer and Product breakdowns
    """
    from app.services.order_service import confirm_order

    # Bill 1: Satya (₹898)
    o1 = process_natural_language_order("Satya, three Filter, one Scissor, two Kings", "rep1")
    save_confirmed_sale(confirm_order(o1.order_id))

    # Bill 2: Kumar (₹100)
    o2 = process_natural_language_order("Kumar 1 Scissor", "rep2")
    save_confirmed_sale(confirm_order(o2.order_id))

    # Bill 3: Ravi (₹152)
    o3 = process_natural_language_order("Ravi 2 Bingo ₹5", "rep3")
    save_confirmed_sale(confirm_order(o3.order_id))

    # Daily Summary
    summary = get_daily_sales_summary()
    # 898 + 100 + 152 = 1150
    assert summary.total_sales == 1150.0
    assert summary.total_bills == 3
    assert summary.total_customers == 3
    assert len(summary.customer_breakdown) == 3

    # Test HTTP endpoint
    res = client.get("/sales/reports/daily")
    assert res.status_code == 200
    report = res.json()
    assert report["total_sales"] == 1150.0
    assert report["total_bills"] == 3
    assert report["total_customers"] == 3


# ==============================================================================
# COMPLETE MVP DEFINITION OF DONE END-TO-END TEST
# ==============================================================================

def test_complete_mvp_definition_of_done():
    """
    The Full Finish Line Test as defined in SHOP_ASSISTANT_PHASE_BY_PHASE.md (Lines 1378-1432):
    1. Mother speaks: 'Satya, three Filter, one Scissor, two Kings.'
    2. System understands order & rates: Filter (354) + Scissor (100) + Kings (444) = 898.
    3. Mother confirms bill.
    4. Sale is permanently recorded.
    5. Father asks: 'What did Satya buy today?'
    6. System retrieves exact saved sale: Filter 3 Packet, Scissor 1 Piece, Kings 2 Piece, Total ₹898.
    """
    # 1 & 2: Mother speaks -> Draft Bill
    process_res = client.post(
        "/pipeline/process",
        json={
            "transcript": "Satya, three Filter, one Scissor, two Kings",
            "session_id": "whatsapp_mother",
        },
    )
    assert process_res.status_code == 200
    draft_order = process_res.json()
    order_id = draft_order["order_id"]
    assert draft_order["calculated_bill"]["grand_total"] == 898.0

    # 3 & 4: Mother confirms bill -> Sale saved
    confirm_res = client.post(
        f"/sales/confirm/{order_id}",
        json={"created_by": "Mother", "customer_phone": "+919876543210"},
    )
    assert confirm_res.status_code == 200
    saved_sale = confirm_res.json()
    assert saved_sale["status"] == "confirmed"
    assert saved_sale["total"] == 898.0

    # 5 & 6: Father asks -> What did Satya buy today?
    father_res = client.get("/sales/customer/Satya")
    assert father_res.status_code == 200
    father_data = father_res.json()
    assert len(father_data) == 1
    found = father_data[0]

    assert found["customer_name"] == "Satya"
    assert found["total"] == 898.0
    item_names = [i["product_name_snapshot"] for i in found["items"]]
    assert "Filter" in item_names
    assert "Scissor" in item_names
    assert "Kings Triple Two" in item_names
