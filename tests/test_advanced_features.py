"""Comprehensive Test Suite for Advanced Phases 14 through 23:

- Phase 14: Father's Natural-Language Queries
- Phase 15: Voice Input Processing & Transcription
- Phase 16: Tamil, English & Tanglish Phonetic Normalization
- Phase 17: WhatsApp Webhook Routing & Life-cycle
- Phase 18: Formatted WhatsApp Customer Invoice Delivery
- Phase 21: Automatic Stock Deduction & Alerts
- Phase 22: Wholesale vs Retail Dual Pricing
- Phase 23: Sale Voiding, Restocking & Immutable Audit Logs
"""

import pytest
import mongomock
from fastapi.testclient import TestClient

from app.main import app
from app.models.billing import BillItemInput
from app.models.father_query import QueryIntent
from app.services.product_service import seed_real_products, get_product_by_id
from app.services.billing_service import calculate_item_amount, calculate_bill
from app.services.language_service import normalize_tamil_tanglish_text
from app.services.audio_service import transcribe_audio_bytes, transcribe_base64_audio
from app.services.pipeline_service import process_natural_language_order
from app.services.order_service import confirm_order
from app.services.sales_service import (
    save_confirmed_sale,
    cancel_or_void_sale,
    get_product_stock,
    update_product_stock,
)
from app.services.father_query_service import (
    parse_father_query_intent,
    answer_father_query,
)
from app.services.whatsapp_service import (
    format_whatsapp_invoice,
    handle_incoming_whatsapp_message,
    get_outbound_messages_log,
    clear_outbound_messages_log,
)
import app.database as db_module

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_mock_db(monkeypatch):
    """Seed real products in in-memory MongoDB before each test."""
    mock_client = mongomock.MongoClient()
    monkeypatch.setattr(db_module, "_client", mock_client)
    monkeypatch.setattr(db_module, "_db", mock_client["shop_assistant_test"])
    seed_real_products()
    clear_outbound_messages_log()
    return mock_client


# ==============================================================================
# PHASE 14: Father's Natural-Language Sales Queries
# ==============================================================================

def test_phase14_father_queries_intent_parsing():
    """Verify natural phrases map accurately to controlled query intents."""
    # 1. Customer query
    q1 = parse_father_query_intent("What did Satya buy today?")
    assert q1.intent == QueryIntent.CUSTOMER_SALES
    assert q1.customer_name == "Satya"

    # 2. Daily collection query
    q2 = parse_father_query_intent("What is today's total sales?")
    assert q2.intent == QueryIntent.DAILY_REVENUE

    q2_tamil = parse_father_query_intent("iniku collection evlo?")
    assert q2_tamil.intent == QueryIntent.DAILY_REVENUE

    # 3. Product query
    q3 = parse_father_query_intent("Who bought Bingo today?")
    assert q3.intent == QueryIntent.PRODUCT_SALES
    assert "Bingo" in (q3.product_identifier or "")

    # 4. Invoice lookup
    q4 = parse_father_query_intent("Show bill INV-001")
    assert q4.intent == QueryIntent.INVOICE_LOOKUP
    assert q4.invoice_number == "INV-001"


def test_phase14_father_query_execution_and_formatting():
    """Verify end-to-end execution of Father's query against stored sales."""
    # Seed a sale for Satya
    order = process_natural_language_order("Satya, 3 Filter, 1 Scissor, 2 Kings", "test_f14")
    save_confirmed_sale(confirm_order(order.order_id))

    # Father asks: What did Satya buy today?
    response = answer_father_query("What did Satya buy today?")
    assert response.intent == QueryIntent.CUSTOMER_SALES
    assert "Satya" in response.answer_text
    assert "Filter" in response.answer_text
    assert "898.00" in response.answer_text

    # Father asks via API
    api_res = client.post("/sales/query", json={"query": "What is today's total sales?"})
    assert api_res.status_code == 200
    data = api_res.json()
    assert data["intent"] == "daily_revenue"
    assert "898.00" in data["answer_text"]


# ==============================================================================
# PHASE 15: Voice Input Processing
# ==============================================================================

def test_phase15_voice_input_offline_transcription():
    """Verify audio transcription and voice-to-order pipeline."""
    # Test encoded mock audio payload
    mock_audio_bytes = b"MOCK_AUDIO:Satya, three Filter, one Scissor, two Kings"
    transcript = transcribe_audio_bytes(mock_audio_bytes)
    assert transcript == "Satya, three Filter, one Scissor, two Kings"

    # Voice to draft bill endpoint
    response = client.post(
        "/audio/order",
        files={"file": ("speech.ogg", mock_audio_bytes, "audio/ogg")},
        data={"session_id": "mother_voice_session"},
    )
    assert response.status_code == 200
    order_data = response.json()
    assert order_data["customer_name"] == "Satya"
    assert order_data["calculated_bill"]["grand_total"] == 898.0


# ==============================================================================
# PHASE 16: Tamil, English, Tanglish Normalization
# ==============================================================================

def test_phase16_tamil_tanglish_normalization():
    """Verify colloquial Tamil words, verbs, and cases are cleanly normalized."""
    raw_phrase = "Satya-ku three Filter kudunga, rendu Scissor podunga, oru Kings venum"
    normalized = normalize_tamil_tanglish_text(raw_phrase)
    # Satya-ku -> Satya, kudunga/podunga/venum stripped, rendu -> 2, oru -> 1
    assert "Satya" in normalized
    assert "2 Scissor" in normalized
    assert "1 Kings" in normalized
    assert "kudunga" not in normalized

    # Pass directly through pipeline
    order = process_natural_language_order("Satya-ku rendu Kings, oru Scissor", "session_tanglish")
    assert order.customer_name == "Satya"
    # Kings: 2 * 222 = 444, Scissor: 1 * 100 = 100 -> Total = 544
    assert order.calculated_bill.grand_total == 544.0


# ==============================================================================
# PHASE 17 & 18: WhatsApp Webhook & Invoice Delivery
# ==============================================================================

def test_phase17_whatsapp_order_lifecycle():
    """
    Verify complete WhatsApp interaction loop:
    1. Mother texts order
    2. System drafts bill and replies
    3. Mother replies 'OK'
    4. System confirms, saves sale, and replies with formatted receipt card
    """
    phone = "+919876500001"

    # Step 1: Mother sends order via WhatsApp webhook
    res1 = client.post(
        "/webhook/whatsapp",
        json={"from_number": phone, "message": "Satya, 3 Filter, 1 Scissor, 2 Kings"},
    )
    assert res1.status_code == 200
    assert "DRAFT BILL" in res1.json()["reply"]
    assert "898.00" in res1.json()["reply"]

    # Step 2: Mother confirms by sending 'OK'
    res2 = client.post(
        "/webhook/whatsapp",
        json={"from_number": phone, "message": "OK"},
    )
    assert res2.status_code == 200
    reply = res2.json()["reply"]
    assert "Bill Confirmed" in reply
    assert "SRI MURUGAN STORES" in reply
    assert "INV-001" in reply
    assert "898.00" in reply


def test_whatsapp_ambiguity_clarification_loop_and_resolution():
    """
    Verify the ambiguity conversation loop:
    1. User sends ambiguous product 'bingo'
    2. Bot asks for clarification
    3. User says 'continue' (non-variant) -> Bot preserves cart and asks again
    4. User says 'bingo 5rs' -> Bot resolves variant and prints draft bill
    5. User says 'OK' -> Bill confirmed
    """
    phone = "+919876500099"

    # 1. Order ambiguous item
    r1 = client.post("/webhook/whatsapp", json={"from_number": phone, "message": "bingo"})
    assert r1.status_code == 200
    assert "Clarification Needed" in r1.json()["reply"]
    assert "Bingo ₹5" in r1.json()["reply"]

    # 2. User replies with filler text 'continue'
    r2 = client.post("/webhook/whatsapp", json={"from_number": phone, "message": "continue"})
    assert r2.status_code == 200
    assert "Clarification Needed" in r2.json()["reply"]

    # 3. User provides variant 'bingo 5rs'
    r3 = client.post("/webhook/whatsapp", json={"from_number": phone, "message": "bingo 5rs"})
    assert r3.status_code == 200
    reply3 = r3.json()["reply"]
    assert "DRAFT BILL" in reply3
    assert "Bingo ₹5" in reply3
    assert "76.00" in reply3

    # 4. Confirm bill
    r4 = client.post("/webhook/whatsapp", json={"from_number": phone, "message": "OK"})
    assert r4.status_code == 200
    assert "Bill Confirmed" in r4.json()["reply"]
    assert "76.00" in r4.json()["reply"]


def test_whatsapp_retail_shorthand_notation_with_currency_and_hyphen():
    """
    Verify retail shorthand: 'naru,filter 56,scissor 45,bingo $5-50'
    - Customer: Naru
    - Filter 56 packets = ₹6,608.00
    - Scissor 45 pieces = ₹4,500.00
    - Bingo ₹5 (typed as $5-50) 50 sarams = ₹3,800.00
    - Grand Total = ₹14,908.00
    """
    phone = "+919876500088"
    res = client.post(
        "/webhook/whatsapp",
        json={"from_number": phone, "message": "naru,filter 56,scissor 45,bingo $5-50"},
    )
    assert res.status_code == 200
    reply = res.json()["reply"]
    assert "DRAFT BILL" in reply
    assert "Naru" in reply
    assert "Filter: 56 packet = ₹6,608.00" in reply
    assert "Scissor: 45 piece = ₹4,500.00" in reply
    assert "Bingo ₹5: 50 saram = ₹3,800.00" in reply
    assert "14,908.00" in reply


def test_phase18_send_invoice_to_customer_endpoint():
    """Verify delivery of confirmed invoice to customer's WhatsApp."""
    # Create and save a sale
    order = process_natural_language_order("Satya, 1 Scissor", "s_inv")
    sale = save_confirmed_sale(confirm_order(order.order_id))

    # Send invoice to customer
    res = client.post(
        f"/webhook/whatsapp/send-invoice/{sale.invoice_number}",
        json={"recipient_phone": "+919944001122"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "sent"
    assert "SRI MURUGAN STORES" in res.json()["message"]

    # Check outbound logs
    logs = client.get("/webhook/whatsapp/logs").json()
    assert len(logs) >= 1
    assert logs[-1]["to"] == "+919944001122"


# ==============================================================================
# PHASE 21: Stock Management & Automatic Deduction
# ==============================================================================

def test_phase21_stock_auto_deduction_and_replenishment():
    """Verify that confirming a sale automatically reduces inventory in base units."""
    # Initialize Kings stock to 50
    update_product_stock("KINGS", 50.0)
    stock_before = get_product_stock("KINGS")["stock_quantity"]
    assert stock_before == 50.0

    # Sell 2 pieces of Kings
    order = process_natural_language_order("Ravi 2 Kings", "stock_s1")
    sale = save_confirmed_sale(confirm_order(order.order_id))

    # Stock should now be 48
    stock_after = get_product_stock("KINGS")["stock_quantity"]
    assert stock_after == 48.0

    # Replenish stock via API
    api_res = client.post("/sales/stock/KINGS", json={"new_quantity": 100.0, "operator": "Father"})
    assert api_res.status_code == 200
    assert api_res.json()["new_stock"] == 100.0


# ==============================================================================
# PHASE 22: Wholesale vs Retail Pricing Mode
# ==============================================================================

def test_phase22_wholesale_vs_retail_calculations():
    """
    Verify wholesale pricing when requested.
    Product: FILTER (retail_rate: 118, wholesale_rate: 115)
    Product: BINGO_5 (retail_rate: 76/saram, wholesale_rate: 73/saram)
    """
    from app.services.product_service import upsert_product
    filter_prod = get_product_by_id("FILTER")
    assert filter_prod is not None
    filter_prod.wholesale_rate = 115.0
    upsert_product(filter_prod)
    filter_prod = get_product_by_id("FILTER")
    assert filter_prod.retail_rate == 118.0
    assert filter_prod.wholesale_rate == 115.0

    # Retail calculation: 2 packets @ 118 = 236
    retail_item = calculate_item_amount(filter_prod, quantity=2, unit="packet", is_wholesale=False)
    assert retail_item.rate == 118.0
    assert retail_item.amount == 236.0
    assert retail_item.is_wholesale is False

    # Wholesale calculation: 2 packets @ 115 = 230
    wholesale_item = calculate_item_amount(filter_prod, quantity=2, unit="packet", is_wholesale=True)
    assert wholesale_item.rate == 115.0
    assert wholesale_item.amount == 230.0
    assert wholesale_item.is_wholesale is True

    # Order calculation with wholesale mode
    wh_bill = calculate_bill(
        items=[BillItemInput(product_id="FILTER", quantity=2, unit="packet")],
        customer_name="Wholesale Buyer",
        is_wholesale=True,
    )
    assert wh_bill.grand_total == 230.0
    assert wh_bill.is_wholesale is True


# ==============================================================================
# PHASE 23: Audit Logs and Sale Cancellation
# ==============================================================================

def test_phase23_sale_cancellation_and_restocking():
    """Verify cancelling an invoice restores stock and records audit log."""
    update_product_stock("SCISSOR", 20.0)

    # 1. Sell 2 pieces of Scissor
    order = process_natural_language_order("Kumar 2 Scissor", "s_cancel_test")
    sale = save_confirmed_sale(confirm_order(order.order_id))
    assert get_product_stock("SCISSOR")["stock_quantity"] == 18.0

    # 2. Cancel the sale via API
    cancel_res = client.post(
        f"/sales/invoice/{sale.invoice_number}/cancel",
        json={"reason": "Customer cancelled item", "operator": "Father"},
    )
    assert cancel_res.status_code == 200
    cancelled_sale = cancel_res.json()
    assert cancelled_sale["status"] == "cancelled"

    # 3. Stock must be restored to 20
    assert get_product_stock("SCISSOR")["stock_quantity"] == 20.0

    # 4. Check audit logs
    audit_col = db_module.get_audit_logs_collection()
    cancel_audit = audit_col.find_one({"action": "sale_cancelled", "invoice_number": sale.invoice_number})
    assert cancel_audit is not None
    assert cancel_audit["reason"] == "Customer cancelled item"
    assert cancel_audit["operator"] == "Father"
