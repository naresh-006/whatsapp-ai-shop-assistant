# 🛒 AI WhatsApp Shop Assistant

> **Deterministic Billing & Conversational Assistant for Family Retail + Wholesale Business.**
> AI understands natural customer orders, MongoDB serves as the source of truth, and deterministic Python arithmetic guarantees 100% price accuracy.

---

## 🌟 Core Architecture Principle

```text
Spoken Speech (Voice Note / Audio)
         ↓
Transcription & Tanglish Normalization (oru/rendu -> 1/2, strip colloquial verbs)
         ↓
AI Structured Understanding (Item names & quantities extracted)
         ↓
Resolver & Ambiguity Engine (Catalog aliases, fuzzy matching, variant disambiguation)
         ↓
Authoritative MongoDB Rates (Live product master data)
         ↓
Deterministic Billing Engine (Zero AI hallucinations; pure Python Decimal arithmetic)
         ↓
Draft Bill Presentation & Conversational Edits ("Change Filter to 5", "Remove Kings")
         ↓
Mother Confirms ("OK")
         ↓
Permanent Sale Recorded (Invoice INV-001, rate snapshotting, auto stock reduction)
         ↓
Father's Natural-Language Search & Daily Business Reports ("What did Satya buy today?")
         ↓
Automated WhatsApp Invoice Delivery to Customer
```

---

## 🚀 Quick Start

### 1. Requirements
- Python 3.12+
- MongoDB 7.0+ (or run via Docker)

### 2. Local Setup
```bash
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Run all 64 automated tests
pytest -v

# Start FastAPI backend
uvicorn app.main:app --reload --port 8000
```

Interactive Swagger documentation is available at: `http://localhost:8000/docs`

### 3. Docker Deployment
```bash
docker-compose up --build -d
```

---

## 📱 Daily Family Workflow

### 1. Mother Selling at Counter (Voice or Text)
1. **Speaks order**:
   > *"Satya-ku three Filter kudunga, one Scissor, two Kings."*
2. **System responds with Draft Bill**:
   ```text
   📋 DRAFT BILL - Review Required
   Customer: Satya
   ────────────────────────────
   1. Filter: 3 packet = ₹354.00
   2. Scissor: 1 piece = ₹100.00
   3. Kings Triple Two: 2 piece = ₹444.00
   ────────────────────────────
   *TOTAL: ₹898.00*
   👉 Reply OK to confirm or say 'Change Filter to 5'
   ```
3. **Mother confirms**:
   > *"OK"*
4. **Permanent Sale Recorded**:
   - Invoice `INV-001` created.
   - Prices frozen immutably.
   - Inventory automatically deducted (Filter -3, Scissor -1, Kings -2).
   - Formatted WhatsApp bill generated.

### 2. Father Monitoring Shop & Sales
- **Customer Inquiry**:
  - *"What did Satya buy today?"*
  - 🛒 *Satya bought 1 bill today:*
    `• INV-001 at 04:30 PM: 3 Filter (packet), 1 Scissor (piece), 2 Kings (piece) — ₹898.00`
- **Daily Revenue Inquiry**:
  - *"What is today's total collection?"*
  - 📊 *Total Revenue: ₹898.00 | Total Bills: 1 | Customers: 1*
- **Product Sales Inquiry**:
  - *"Who bought Bingo today?"*
- **Invoice Voiding & Cancellation**:
  - Cancelling an invoice automatically restores inventory and creates an immutable audit trail entry in `audit_logs`.

---

## 📦 Verified Product Catalog (Family Shop Rates)

| Product ID | Canonical Name | Retail Unit | Retail Rate | Wholesale Unit | Wholesale Rate | Conversion Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `FILTER` | Filter | Packet | ₹118.00 | — | ₹115.00 | Bundle: 50 pieces |
| `KINGS` | Kings Triple Two | Piece | ₹222.00 | Bundle | — | 1 bundle = 20 pieces (₹4,440.00) |
| `SCISSOR` | Scissor | Piece | ₹100.00 | — | — | — |
| `INTIMATE` | Intimate | Piece | ₹118.00 | — | — | — |
| `FLAG` | Gold Flake (Flag) | Piece | ₹110.00 | — | — | — |
| `MARIE_LIGHT_5` | Marie Light ₹5 | Packet | ₹5.00 | Dozen | ₹55.00 | 1 dozen = 12 packets |
| `MARIE_LIGHT_10`| Marie Light ₹10 | Packet | ₹10.00 | Dozen | ₹110.00 | 1 dozen = 12 packets |
| `YIPPEE_NOODLES` | Yippee Noodles Regular | Packet | ₹12.00 | — | — | — |
| `YIPPEE_FAMILY_PACK` | Yippee Family Pack | Packet | ₹48.00 | — | — | 1 pack = 4 units |
| `BEEDI` | Beedi Bundle | Bundle | ₹30.00 | — | — | 1 bundle = 25 beedis |
| `BINGO_5` | Bingo ₹5 | Saram | ₹76.00 | — | ₹73.00 | 1 saram = 16 packets |
| `BINGO_10` | Bingo ₹10 | Saram | ₹152.00 | — | ₹146.00 | 1 saram = 16 packets |

---

## 🧪 Automated Test Suite (64 Tests)

```powershell
pytest -v
```

- **`test_health.py`**: Health checks & root ping.
- **`test_database.py`**: MongoDB connectivity, mock DB layer & CRUD.
- **`test_products.py`**: Real family product master catalog validation.
- **`test_dummy_catalog.py`**: 103-item realistic synthetic dataset isolation.
- **`test_search_api.py`**: Hierarchical alias search & fuzzy matching.
- **`test_billing.py`**: Strict deterministic arithmetic, unit conversions & bundle calculations.
- **`test_orders.py`**: Pydantic draft order life-cycle & state transitions.
- **`test_ai_extraction.py`**: Multi-variant extraction from unstructured spoken text.
- **`test_resolver.py`**: Automatic ambiguity detection (`Bingo` -> prompts for ₹5 vs ₹10).
- **`test_mvp_pipeline_and_sales.py`**: End-to-end fastest MVP verification (Phases 9 to 13).
- **`test_advanced_features.py`**: Father queries, audio input, Tanglish normalization, WhatsApp webhooks, stock tracking, wholesale rates, and bill voiding.
