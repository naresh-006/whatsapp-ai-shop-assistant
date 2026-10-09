import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.order import RawExtractedOrder
from app.services.ai_service import extract_order_from_text

client = TestClient(app)


def test_standard_phase7_example_extraction():
    """
    Verify Phase 7 input specification:
    'Satya, three Filter, one Scissor, two Kings'
    """
    transcript = "Satya, three Filter, one Scissor, two Kings"
    extracted = extract_order_from_text(transcript)

    assert isinstance(extracted, RawExtractedOrder)
    assert extracted.customer_name == "Satya"
    assert len(extracted.items) == 3

    # 1. Filter
    filter_item = extracted.items[0]
    assert filter_item.product_text.lower() == "filter"
    assert filter_item.quantity == 3.0
    assert filter_item.unit in {"packet", "piece"}

    # 2. Scissor
    scissor_item = extracted.items[1]
    assert scissor_item.product_text.lower() == "scissor"
    assert scissor_item.quantity == 1.0

    # 3. Kings
    kings_item = extracted.items[2]
    assert kings_item.product_text.lower() == "kings"
    assert kings_item.quantity == 2.0


def test_unpunctuated_speech_extraction():
    """Verify natural speech without commas is parsed correctly."""
    transcript = "Satya three Filter one Scissor two Kings"
    extracted = extract_order_from_text(transcript)

    assert extracted.customer_name == "Satya"
    assert len(extracted.items) == 3
    assert extracted.items[0].quantity == 3.0
    assert extracted.items[1].quantity == 1.0
    assert extracted.items[2].quantity == 2.0


def test_tanglish_colloquial_phrasing():
    """Verify Tamil/Tanglish order: 'Satya-ku 3 Filter, 1 Scissor'."""
    transcript = "Satya-ku 3 Filter, 1 Scissor"
    extracted = extract_order_from_text(transcript)

    assert extracted.customer_name == "Satya"
    assert len(extracted.items) == 2
    assert extracted.items[0].product_text.lower() == "filter"
    assert extracted.items[0].quantity == 3.0
    assert extracted.items[1].product_text.lower() == "scissor"
    assert extracted.items[1].quantity == 1.0


def test_complex_order_with_variants():
    """
    Verify Architecture Section 5 full natural-language order:
    'Satya, three Filter, one Scissor, two Kings, Marie Light five rupees one, ten rupees one, Bingo five rupees one, ten rupees one'
    """
    transcript = (
        "Satya, three Filter, one Scissor, two Kings, "
        "Marie Light five rupees one, ten rupees one, "
        "Bingo five rupees one, ten rupees one"
    )
    extracted = extract_order_from_text(transcript)

    assert extracted.customer_name == "Satya"
    assert len(extracted.items) >= 6

    product_names = [item.product_text.lower() for item in extracted.items]
    assert any("filter" in name for name in product_names)
    assert any("scissor" in name for name in product_names)
    assert any("kings" in name for name in product_names)
    assert any("marie" in name for name in product_names)
    assert any("bingo" in name for name in product_names)


def test_ai_extraction_api_endpoint():
    """Verify POST /ai/extract-order HTTP endpoint."""
    payload = {"transcript": "Satya, two Kings, one Scissor"}
    response = client.post("/ai/extract-order", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["customer_name"] == "Satya"
    assert len(data["items"]) == 2
    assert data["items"][0]["product_text"].lower() == "kings"
    assert data["items"][0]["quantity"] == 2.0
    assert data["items"][1]["product_text"].lower() == "scissor"
    assert data["items"][1]["quantity"] == 1.0
    assert data["raw_transcript"] == "Satya, two Kings, one Scissor"
