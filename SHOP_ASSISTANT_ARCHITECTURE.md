# AI WhatsApp Shop Assistant --- Product Architecture

## 1. Project Overview

### Project name

AI WhatsApp Shop Assistant

### Primary goal

Build a practical shop assistant for a family retail + wholesale
business.

The system must reduce billing mistakes, reduce the burden on the user's
mother, preserve accurate product prices, record every confirmed sale,
and allow the user's father to quickly search and verify sales.

The system is intended for real family use, not only as a portfolio
demonstration.

### Core principle

**AI understands the conversation. The database is the source of truth.
Deterministic business logic performs pricing and calculations.**

The AI must never invent a product price, quantity, unit, or conversion
when the information is missing or ambiguous.

If something is uncertain, the system must ask for clarification.

------------------------------------------------------------------------

# 2. Real-World Problem

The family business has both retail and wholesale sales.

The shop handles products such as:

-   Tobacco products
-   Biscuits
-   Bingo/snacks
-   Incense/agarbatti
-   Matchboxes
-   Noodles
-   Other daily-use products

The user's mother may operate the shop alone.

Problems include:

-   She may not remember every product price.
-   She should not have to type every product.
-   Customers naturally speak orders instead of providing structured
    data.
-   Similar product names can cause mistakes.
-   Different products have different selling units.
-   Quantity/rate mistakes can reduce profit.
-   The father needs to verify what sales were made during the day.
-   Searching through many bills manually is inconvenient.

The assistant should therefore make the workflow:

**Speak -\> Understand -\> Verify -\> Calculate -\> Confirm -\> Save -\>
Search**

------------------------------------------------------------------------

# 3. Main Users

## 3.1 Mother --- Sales/Billing User

Primary activities:

-   Receive customer order.
-   Speak the order using WhatsApp voice/microphone.
-   Review the interpreted order.
-   Correct mistakes.
-   Confirm the bill.
-   Optionally send the invoice to the customer.

The interface should be extremely simple.

She should not need to:

-   Type product names.
-   Remember prices.
-   Perform calculations manually.
-   Navigate complicated dashboards.

------------------------------------------------------------------------

## 3.2 Father --- Sales Verification/Management User

Primary activities:

-   Ask how many sales happened today.
-   Search a customer.
-   View what a customer purchased.
-   Check a customer's bill amount.
-   Search sales by product.
-   View total daily sales.
-   Review individual bills.
-   Later, view stock and reports.

Example:

> "What did Satya buy today?"

Expected result:

``` text
Customer: Satya
Bill: INV-002

Filter          3 Packet
Scissor         1 Piece
Kings           2 Piece
Intimate        1 Piece
Marie Light ₹5  1 Dozen
Marie Light ₹10 1 Dozen
Bingo ₹5        1 Saram
Bingo ₹10       1 Saram

Total: ₹1,366
```

------------------------------------------------------------------------

# 4. Core Product Workflow

## 4.1 Mother creates a sale

``` text
Mother speaks into WhatsApp
        |
        v
Voice message
        |
        v
Speech-to-text
        |
        v
Language detection
        |
        v
AI extracts order information
        |
        v
Product resolver identifies exact products
        |
        v
Database retrieves authoritative rates
        |
        v
Billing engine calculates amounts
        |
        v
Draft bill
        |
        v
Mother confirms/corrects
        |
        v
Final sale saved
        |
        v
Optional customer invoice
```

------------------------------------------------------------------------

# 5. Example Natural-Language Order

Example:

> "Satya, three Filter, one Scissor, two Kings, one Intimate, Marie
> Light five rupees one, ten rupees one, Bingo five rupees one, ten
> rupees one."

The system should extract approximately:

``` json
{
  "customer_name": "Satya",
  "items": [
    {
      "product": "Filter",
      "quantity": 3,
      "unit": "packet"
    },
    {
      "product": "Scissor",
      "quantity": 1,
      "unit": "piece"
    },
    {
      "product": "Kings Triple Two",
      "quantity": 2,
      "unit": "piece"
    },
    {
      "product": "Intimate",
      "quantity": 1,
      "unit": "piece"
    },
    {
      "product": "Marie Light ₹5",
      "quantity": 1,
      "unit": "dozen"
    },
    {
      "product": "Marie Light ₹10",
      "quantity": 1,
      "unit": "dozen"
    },
    {
      "product": "Bingo ₹5",
      "quantity": 1,
      "unit": "saram"
    },
    {
      "product": "Bingo ₹10",
      "quantity": 1,
      "unit": "saram"
    }
  ]
}
```

The AI's job ends at structured understanding.

The backend then performs exact product matching, price lookup, unit
conversion, and calculation.

------------------------------------------------------------------------

# 6. Critical Accuracy Rule

This is a money-related application.

Never allow the LLM to decide a final price.

Bad architecture:

``` text
Voice
  -> LLM
  -> LLM guesses price
  -> Bill
```

Correct architecture:

``` text
Voice
  -> Speech-to-text
  -> LLM understands order
  -> Product ID
  -> MongoDB price
  -> Billing engine
  -> Bill
```

If the product or unit is ambiguous:

``` text
AI detects ambiguity
        |
        v
Ask user for clarification
        |
        v
Continue only after clarification
```

Example:

> "Bingo three saram"

If the system cannot determine whether the customer wants Bingo ₹5 or
Bingo ₹10:

> "Do you mean Bingo ₹5 or Bingo ₹10?"

It must not guess.

------------------------------------------------------------------------

# 7. Product Database Architecture

The product database should contain a canonical product record.

Recommended fields:

``` text
Product
├── product_id
├── canonical_name
├── brand
├── category
├── variant
├── tamil_name
├── aliases
├── retail_unit
├── wholesale_unit
├── base_unit
├── retail_rate
├── wholesale_rate
├── conversion_rules
├── stock_quantity
├── active
└── metadata
```

Example:

``` json
{
  "product_id": "KINGS",
  "canonical_name": "Kings Triple Two",
  "category": "Tobacco",
  "variant": "Triple Two",
  "aliases": [
    "Kings",
    "King",
    "Kings Triple Two"
  ],
  "retail_unit": "piece",
  "base_unit": "piece",
  "retail_rate": 222,
  "conversion_rules": {
    "bundle": {
      "pieces": 20
    }
  },
  "active": true
}
```

------------------------------------------------------------------------

# 8. Units

The application must support business-specific units.

Initial units:

-   piece
-   packet
-   dozen
-   saram
-   bundle

Do not assume that every product uses the same unit.

The database must explicitly define valid units for each product.

------------------------------------------------------------------------

# 9. Real Product Data Currently Known

These are real values supplied for the current project and must not be
replaced with invented values.

## Filter

-   ₹118 per packet.
-   A bundle was described as 50 pieces.
-   The relationship between packet price and bundle price is not yet
    fully defined.
-   Do NOT automatically calculate bundle price as 118 × 50.

## Kings Triple Two

-   ₹222 per piece.
-   1 bundle = 20 pieces.
-   1 bundle = ₹4,440.

## Scissor

-   ₹100 per piece.
-   1 bundle = 50 pieces.
-   1 bundle = ₹5,000.

## Intimate

-   ₹117 per piece.
-   1 bundle = 20 pieces.
-   1 bundle = ₹2,340.

## Flag

-   ₹76 per piece.
-   1 bundle = 50 pieces.
-   1 bundle = ₹3,800.

## Marie Light ₹10

-   1 dozen = ₹110.

## Marie Light ₹5

-   1 dozen = ₹55.

## Yippee Noodles

-   ₹15 per piece.
-   1 dozen = 12 pieces.
-   A previous statement mentioned ₹13 in a way that is ambiguous.
-   Do not invent a dozen selling price until clarified.

## Yippee Family Pack

-   ₹55 per piece.
-   1 dozen = 12 pieces.

## Beedi

-   ₹320 per bundle.
-   Bundle piece count has not been supplied.

## Bingo ₹5

-   ₹76 per saram.
-   1 saram = 16 pieces.

## Bingo ₹10

-   ₹110 per saram.
-   1 saram = 16 pieces.

Products without confirmed real rates must remain clearly marked as
dummy/development data until the family provides the actual rate.

------------------------------------------------------------------------

# 10. Pricing and Conversion Rules

Some products have a piece price and a fixed bundle size.

Example:

``` text
Kings
₹222 / piece
20 pieces / bundle

1 bundle = 222 × 20
         = ₹4,440
```

If the order is:

``` text
2 pieces + 3 bundles
```

then:

``` text
2 × ₹222 = ₹444

3 × 20 × ₹222 = ₹13,320

Total = ₹13,764
```

However, this conversion logic must only be applied when the database
explicitly says the base rate is per piece and the bundle contains a
defined number of pieces.

Do not apply the same formula to Filter because ₹118 is a packet rate.

------------------------------------------------------------------------

# 11. Billing Engine

The billing engine is deterministic Python code.

Example:

``` text
Product
Quantity
Unit
Rate
        |
        v
Amount = Quantity × Applicable Rate
        |
        v
All item amounts
        |
        v
Grand Total
```

The LLM should not perform these calculations.

The backend should calculate and verify totals.

The system should preserve:

-   quantity
-   unit
-   rate
-   amount
-   total
-   timestamp
-   customer
-   bill ID

------------------------------------------------------------------------

# 12. Draft Bill and Confirmation

The system should never immediately finalize an uncertain order.

Flow:

``` text
Order understood
      |
      v
Draft bill
      |
      v
User reviews
      |
      +---- Correct ----> Update order
      |
      +---- Confirm ----> Save sale
```

Example:

``` text
Draft Bill

Customer: Satya

Filter          3 Packet     ₹354
Scissor         1 Piece      ₹100
Kings           2 Piece      ₹444
Intimate        1 Piece      ₹117
Marie Light ₹5  1 Dozen       ₹55
Marie Light ₹10 1 Dozen      ₹110
Bingo ₹5        1 Saram       ₹76
Bingo ₹10       1 Saram      ₹110

Total: ₹1,366

Confirm bill?
```

------------------------------------------------------------------------

# 13. Corrections

The user should be able to naturally correct a draft.

Examples:

> "Change Bingo to 5."

> "Remove Kings."

> "Add two Marie Light."

> "Change Filter from three to five."

The system should update the structured order and regenerate the bill.

------------------------------------------------------------------------

# 14. Customer Invoice

After confirmation:

``` text
Bill confirmed
      |
      v
"Would you like to receive the bill on WhatsApp?"
      |
      +---- No ----> Finish
      |
      +---- Yes
              |
              v
        Ask WhatsApp number
              |
              v
        Validate number
              |
              v
        Confirm number
              |
              v
        Send invoice
```

The invoice should be generated from the confirmed database transaction,
not directly from the LLM response.

------------------------------------------------------------------------

# 15. Sales History

Every confirmed sale must be stored.

Recommended structure:

``` text
Sale
├── sale_id
├── invoice_number
├── customer_name
├── customer_phone
├── created_at
├── created_by
├── items
│   ├── product_id
│   ├── product_name_snapshot
│   ├── quantity
│   ├── unit
│   ├── rate
│   └── amount
├── subtotal
├── total
├── status
└── audit information
```

Important:

Store the product name and rate used at the time of sale as a snapshot.

If the product price changes tomorrow, yesterday's bill must still show
yesterday's price.

------------------------------------------------------------------------

# 16. Father's Sales Search

Father should be able to ask natural-language questions.

Examples:

### Customer

> "What did Satya buy today?"

### Customer total

> "How much did Satya buy today?"

### Number of sales

> "How many sales today?"

### Daily sales

> "What is today's total sales?"

### Product

> "Who bought Bingo today?"

### Historical search

> "What did Satya buy yesterday?"

The system should convert the request into a controlled database query.

For exact sales reporting, use normal database queries rather than
relying on RAG.

------------------------------------------------------------------------

# 17. Daily Sales Example

``` text
Today's Sales

Customers: 10
Bills: 10

1. Kumar    ₹850
2. Satya    ₹1,366
3. Ravi     ₹620
...
10. Arun    ₹540

Total Sales: ₹XX,XXX
```

The exact total must come from the database.

------------------------------------------------------------------------

# 18. Audit Trail

Because this system affects real business money, important changes
should be traceable.

Example:

``` text
Original:
Bill INV-102
Total: ₹1,366

Later change:
Bingo ₹5
1 Saram -> 2 Saram

Changed by:
Father

Time:
Recorded automatically
```

Do not silently overwrite important historical information.

------------------------------------------------------------------------

# 19. Language Support

Initial target languages:

-   English
-   Tamil
-   Tanglish
-   Mixed English/Tamil

The product should support natural speech such as:

> "Satya-ku three Filter kudunga."

or:

> "Satya, three Filter, one Scissor."

The system should eventually normalize this into structured
English/internal product IDs.

User preferences can be stored per WhatsApp user.

Example:

``` text
Mother -> English response
Father -> English/Tamil
```

Automatic language detection can also be added.

------------------------------------------------------------------------

# 20. WhatsApp Architecture

WhatsApp is the final primary interface.

Conceptual architecture:

``` text
Mother/Father
     |
     v
WhatsApp
     |
     v
WhatsApp Business API / Provider
     |
     v
Webhook
     |
     v
FastAPI Backend
     |
     +-------------------+
     |                   |
     v                   v
Speech-to-text        Text message
     |                   |
     +---------+---------+
               |
               v
        Language/Intent
               |
               v
        LLM extraction
               |
               v
        Product resolver
               |
               v
            MongoDB
               |
               v
        Billing engine
               |
               v
        Confirmation
               |
               v
          Sale storage
               |
               v
         WhatsApp response
```

WhatsApp integration should be added after the local workflow is
working.

------------------------------------------------------------------------

# 21. Backend Architecture

Recommended stack:

-   Python
-   FastAPI
-   MongoDB
-   PyMongo
-   LLM API
-   Speech-to-text API
-   WhatsApp Business API/provider

Suggested application structure:

``` text
shop-assistant/
│
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   │
│   ├── models/
│   │   ├── product.py
│   │   ├── sale.py
│   │   └── user.py
│   │
│   ├── services/
│   │   ├── product_service.py
│   │   ├── order_service.py
│   │   ├── billing_service.py
│   │   ├── sales_service.py
│   │   ├── speech_service.py
│   │   └── ai_service.py
│   │
│   ├── routes/
│   │   ├── products.py
│   │   ├── sales.py
│   │   ├── orders.py
│   │   └── whatsapp.py
│   │
│   └── utils/
│
├── data/
│   └── seed/
│
├── tests/
│
├── .env
├── .gitignore
├── requirements.txt
└── README.md
```

The exact structure may evolve during implementation.

------------------------------------------------------------------------

# 22. Dummy Data Strategy

We should start with a large realistic dummy product catalog.

The dummy data should contain:

-   realistic product names
-   variants
-   categories
-   English aliases
-   Tamil/Tanglish aliases
-   retail units
-   wholesale units
-   dummy prices
-   conversion rules
-   stock values

The purpose is to stress-test the product resolver and database.

Do not use meaningless names such as:

``` text
Product 1
Product 2
Product 3
```

Use realistic development data.

The dummy data must be clearly labelled as dummy.

Later, real shop data can replace the dummy catalog without changing the
core application logic.

------------------------------------------------------------------------

# 23. RAG Decision

Do not start this project with RAG.

The initial problem is primarily:

-   voice understanding
-   product matching
-   structured extraction
-   database lookup
-   deterministic billing
-   transaction storage
-   sales search

RAG may be considered later for:

-   product knowledge
-   business documentation
-   help/FAQ
-   natural-language policy retrieval

But exact prices and sales should come from the database.

------------------------------------------------------------------------

# 24. Security and Reliability Principles

Because this handles business information:

-   Never hard-code API secrets.
-   Use `.env`.
-   Do not commit secrets to Git.
-   Validate incoming data.
-   Validate phone numbers.
-   Validate quantities.
-   Validate product IDs.
-   Never trust LLM-generated prices.
-   Log important failures.
-   Keep confirmed transaction records.
-   Add tests around billing calculations.
-   Handle database connection errors.
-   Handle speech-to-text errors.
-   Handle ambiguous product matches.
-   Handle duplicate messages where possible.

------------------------------------------------------------------------

# 25. Success Criteria

The first useful version is successful when:

1.  Mother can provide an order naturally.
2.  The system extracts customer and products.
3.  Products map to exact database records.
4.  Rates come from MongoDB.
5.  Quantities and units are preserved.
6.  Bill calculations are deterministic.
7.  Mother can correct mistakes.
8.  Mother confirms the bill.
9.  Confirmed sale is saved.
10. Father can search the sale by customer.
11. Father can view what that customer purchased.
12. Father can view daily sales.
13. No price is guessed by the AI.

------------------------------------------------------------------------

# 26. Development Philosophy

Build the smallest useful version first.

Do not try to build:

-   advanced dashboards
-   complex RAG
-   recommendation engines
-   forecasting
-   advanced analytics

before the core billing workflow works.

Priority:

**Accuracy -\> Reliability -\> Usability -\> Speed -\> Advanced AI**

The application should solve the family's immediate problem first.

------------------------------------------------------------------------

# 27. Learning Philosophy for Naresh

This project is also a learning project.

For every implementation step, explain:

### What are we doing?

The technical task.

### Why are we doing it?

The real-world problem it solves.

### How does it work?

The technical mechanism.

### What changes in our product?

The user-visible/product impact.

### What should I learn?

The GenAI/software engineering concept behind it.

Do not give unexplained code.

The developer should be guided phase by phase and should understand the
architecture before blindly copying code.
