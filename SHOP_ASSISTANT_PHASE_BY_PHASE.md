# AI WhatsApp Shop Assistant --- Phase-by-Phase Implementation Plan

## How to use this file

This is the implementation roadmap for building the AI WhatsApp Shop
Assistant.

The project should be built in small working phases.

For every phase, the developer/AI assistant must explain:

1.  What are we doing?
2.  Why are we doing it?
3.  How does it work?
4.  What changes in the product?
5.  What should Naresh learn from this?
6.  How do we test it?
7.  What is the expected result before moving to the next phase?

Do not skip directly to advanced AI features.

The priority is:

**Working product -\> Accuracy -\> Family testing -\> Real data -\>
Advanced features**

------------------------------------------------------------------------

# PHASE 0 --- Project Setup and Understanding

## Goal

Create the project and understand its architecture before implementing
business logic.

## What are we doing?

Create the backend project using Python and FastAPI.

Prepare:

``` text
shop-assistant/
├── app/
├── data/
├── tests/
├── .env
├── .gitignore
├── requirements.txt
└── README.md
```

## Why?

Every production application needs a clean structure.

This prevents all code from becoming one large file.

## What will Naresh learn?

-   Python project structure
-   Virtual environments
-   Dependencies
-   Environment variables
-   Backend/application architecture

## Expected result

The application starts successfully.

Example:

``` text
Server running
GET /
```

returns a simple health message.

------------------------------------------------------------------------

# PHASE 1 --- MongoDB Connection

## Goal

Connect the application to MongoDB.

## What are we doing?

Create the database connection layer.

Initial collections:

``` text
products
sales
users
```

Later:

``` text
audit_logs
customers
settings
```

## Why?

The shop needs persistent data.

If the application restarts, the products and sales must not disappear.

## How?

FastAPI -\> Python database layer -\> MongoDB.

## What changes in the product?

The shop now has a permanent digital data store.

## What will Naresh learn?

-   Database
-   Collection
-   Document
-   CRUD
-   Connection string
-   MongoDB
-   NoSQL concepts

## Test

Start the application and confirm MongoDB connectivity.

Do not proceed until the connection is reliable.

------------------------------------------------------------------------

# PHASE 2 --- Product Master Database

## Goal

Create the product catalog.

## What are we doing?

Define the product schema.

Important fields:

``` text
product_id
canonical_name
brand
category
variant
aliases
Tamil/Tanglish aliases
retail unit
wholesale unit
base unit
retail rate
wholesale rate
conversion rules
stock
active
```

## Why?

The AI must not invent prices.

The database becomes the authoritative source for prices.

## Example

``` text
Kings Triple Two
₹222 / piece
20 pieces / bundle
```

The database knows:

``` text
piece -> ₹222
bundle -> 20 pieces
```

## What changes in the product?

We can now ask the backend:

> "What is the price of Kings?"

and retrieve the real stored price.

## What will Naresh learn?

-   Data modeling
-   Schema design
-   Primary identifiers
-   Aliases
-   Product variants
-   Business rules

------------------------------------------------------------------------

# PHASE 3 --- Large Dummy Product Dataset

## Goal

Populate the database with a large realistic dummy catalog.

## What are we doing?

Create hundreds of development products across realistic shop
categories.

Examples:

-   tobacco
-   biscuits
-   snacks
-   noodles
-   incense
-   matchboxes
-   daily-use products

Include realistic aliases.

Example:

``` text
Kings
King
Kings Triple Two
```

could map to one canonical product ID.

## Why?

A tiny dataset will make the AI appear accurate even when the product
resolver is weak.

A larger dataset forces us to test realistic ambiguity.

## Important

Clearly mark dummy prices as development data.

Do not mix dummy rates with real family rates without an explicit flag.

## What changes?

We can stress-test product search before using real shop data.

------------------------------------------------------------------------

# PHASE 4 --- Product Search API

## Goal

Create a backend API that can find products.

## Example

``` text
GET /products/search?q=kings
```

Possible response:

``` json
{
  "product_id": "KINGS",
  "name": "Kings Triple Two",
  "rate": 222,
  "unit": "piece"
}
```

## Why?

The AI should eventually produce a product name or product identifier,
and the backend needs a reliable way to resolve it.

## What will Naresh learn?

-   REST API
-   GET request
-   Query parameters
-   JSON
-   Request/response cycle
-   FastAPI routing

------------------------------------------------------------------------

# PHASE 5 --- Deterministic Billing Engine

## Goal

Build billing without AI first.

## What are we doing?

Create Python functions for:

``` text
calculate_item_amount()
calculate_bundle_amount()
calculate_total()
validate_unit()
```

## Example

``` text
Kings
2 pieces
₹222 each

2 × 222 = ₹444
```

## Bundle example

``` text
Kings
1 bundle
20 pieces
₹222 each

1 × 20 × 222
= ₹4,440
```

## Why?

Billing must be exact.

This is a critical business component and must not depend on LLM
reasoning.

## What will Naresh learn?

-   Business logic
-   Functions
-   Validation
-   Deterministic systems
-   Unit conversion
-   Financial calculation

## Test aggressively

Test:

-   1 piece
-   2 pieces
-   1 bundle
-   2 bundles
-   mixed pieces + bundles
-   invalid quantities
-   unknown units

------------------------------------------------------------------------

# PHASE 6 --- Structured Order Model

## Goal

Represent an order as structured data.

Example:

``` json
{
  "customer_name": "Satya",
  "items": [
    {
      "product_id": "FILTER",
      "quantity": 3,
      "unit": "packet"
    },
    {
      "product_id": "KINGS",
      "quantity": 2,
      "unit": "piece"
    }
  ]
}
```

## Why?

Natural language is unstructured.

The backend needs structured information.

## What will Naresh learn?

This is a major GenAI concept:

**Unstructured language -\> structured data**

This is one of the most useful patterns in LLM application development.

------------------------------------------------------------------------

# PHASE 7 --- LLM Order Extraction

## Goal

Use an LLM to understand natural language.

## Input

> "Satya three Filter one Scissor two Kings"

## Expected structured output

``` json
{
  "customer_name": "Satya",
  "items": [
    {
      "product_text": "Filter",
      "quantity": 3,
      "unit": "packet"
    },
    {
      "product_text": "Scissor",
      "quantity": 1,
      "unit": "piece"
    },
    {
      "product_text": "Kings",
      "quantity": 2,
      "unit": "piece"
    }
  ]
}
```

## Important

The LLM should extract what the user said.

It should NOT invent:

``` text
rate
stock
total
```

Those come from the backend.

## What will Naresh learn?

-   LLM APIs
-   Prompt engineering
-   Structured output
-   JSON extraction
-   Function/tool calling concepts
-   Hallucination control

------------------------------------------------------------------------

# PHASE 8 --- Product Resolver

## Goal

Convert the AI's product text into an exact product ID.

Example:

``` text
AI output:
"Kings"

        ↓

Product resolver

        ↓

KINGS
```

## Why?

The database must know exactly which product the customer means.

## Matching order

Start simple:

1.  Exact canonical name
2.  Exact alias
3.  Case-insensitive matching
4.  Variant matching
5.  Fuzzy matching
6.  Semantic matching later if required

Do not jump directly to embeddings.

## Ambiguity

If multiple products match:

``` text
Bingo ₹5
Bingo ₹10
```

ask:

> "Which Bingo do you mean: ₹5 or ₹10?"

## What will Naresh learn?

-   Entity resolution
-   Search
-   Aliases
-   Ambiguity handling
-   Why AI alone is not enough

------------------------------------------------------------------------

# PHASE 9 --- AI Order -\> Database -\> Bill

## Goal

Connect the AI extraction to the deterministic billing engine.

Full pipeline:

``` text
Natural language
      ↓
LLM extraction
      ↓
Structured order
      ↓
Product resolver
      ↓
MongoDB
      ↓
Price + conversion
      ↓
Billing engine
      ↓
Draft bill
```

## Why?

This is the first major working version of the core product.

## Example

Input:

> "Satya three Filter, one Scissor"

Output:

``` text
Satya

Filter
3 packet × ₹118 = ₹354

Scissor
1 piece × ₹100 = ₹100

Total = ₹454
```

------------------------------------------------------------------------

# PHASE 10 --- Draft Bill and Corrections

## Goal

Allow the mother to review and correct the bill before saving.

## Example

System:

``` text
Satya

Filter 3 Packet ₹354
Scissor 1 Piece ₹100

Total ₹454

Confirm?
```

Mother:

> "Change Filter to five."

System:

``` text
Filter 5 Packet ₹590
Scissor 1 Piece ₹100

Total ₹690
```

## Why?

Speech recognition and AI extraction can make mistakes.

The user must have a correction loop.

## What will Naresh learn?

-   Conversational state
-   Session management
-   Multi-turn interactions
-   Validation
-   Human-in-the-loop AI

------------------------------------------------------------------------

# PHASE 11 --- Save Confirmed Sale

## Goal

Save only confirmed bills as sales.

## What are we doing?

Create the `sales` collection.

Store:

``` text
sale_id
invoice_number
customer_name
customer_phone
date
time
created_by
items
rate snapshot
amount snapshot
total
status
```

## Why?

Father needs to search previous transactions.

The business also needs historical records.

## Important

Save the price used at the time of sale.

If:

``` text
Today:
Kings = ₹222
```

and tomorrow:

``` text
Kings = ₹230
```

yesterday's bill must remain ₹222.

------------------------------------------------------------------------

# PHASE 12 --- Father's Sales Search

## Goal

Allow father to search sales naturally.

Start with normal API/database queries.

Examples:

``` text
GET /sales/today
GET /sales/customer/Satya
GET /sales/product/Bingo
```

## Expected use

Father:

> "What did Satya buy today?"

System:

``` text
Satya

Filter          3 Packet
Scissor         1 Piece
Kings           2 Piece
Intimate        1 Piece
Marie Light ₹5  1 Dozen
...

Total: ₹1,366
```

## What will Naresh learn?

-   Database queries
-   Filtering
-   Sorting
-   Date queries
-   Aggregation

------------------------------------------------------------------------

# PHASE 13 --- Daily Sales Reports

## Goal

Allow father to see daily business activity.

Examples:

> "How many sales today?"

> "Today's total sales?"

> "Show today's customers."

> "Who bought Bingo today?"

## Example

``` text
Today's Sales

Bills: 10
Customers: 10

Total: ₹XX,XXX
```

## Important

All numbers must come from the database.

The LLM should not calculate the total from memory.

------------------------------------------------------------------------

# PHASE 14 --- Natural-Language Sales Queries

## Goal

Allow father to ask questions naturally.

Example:

> "What did Satya buy today?"

The AI can identify:

``` text
intent = customer_sales
customer = Satya
date = today
```

Then backend performs:

``` text
MongoDB query
```

The AI can format the result for the user.

## Architecture

``` text
Father question
      ↓
LLM intent/query extraction
      ↓
Validated structured query
      ↓
MongoDB
      ↓
Exact result
      ↓
Response formatting
```

## Important

Do not allow the LLM to freely generate dangerous database operations.

Use controlled query types.

------------------------------------------------------------------------

# PHASE 15 --- Voice Input

## Goal

Allow mother to speak instead of typing.

## Pipeline

``` text
Voice message
      ↓
Speech-to-text
      ↓
Text
      ↓
Existing order pipeline
```

## Why?

This directly solves the mother's usability problem.

## What will Naresh learn?

-   Speech-to-text
-   Audio processing
-   Voice AI
-   API integration
-   Error handling

------------------------------------------------------------------------

# PHASE 16 --- Tamil, English, Tanglish and Mixed Language

## Goal

Support natural family communication.

Examples:

> "Satya-ku three Filter kudunga."

> "Three filter, one scissor."

> Tamil speech with English product names.

## Strategy

The speech-to-text output is passed to the language understanding layer.

Normalize the language into canonical product IDs.

Do not create duplicate product records for each language.

Example:

``` text
Tamil/Tanglish aliases
       |
       v
Same canonical product ID
```

## What will Naresh learn?

-   Multilingual NLP
-   Language detection
-   Normalization
-   Alias design

------------------------------------------------------------------------

# PHASE 17 --- WhatsApp Integration

## Goal

Move from local testing to the actual family interface.

## Architecture

``` text
WhatsApp
    ↓
WhatsApp Business API/provider
    ↓
Webhook
    ↓
FastAPI
    ↓
Existing application services
```

## Important

Do not rewrite the business logic for WhatsApp.

WhatsApp should be another interface over the same backend.

This is a major software architecture principle:

**Separate interface from business logic.**

------------------------------------------------------------------------

# PHASE 18 --- Customer Invoice on WhatsApp

## Goal

Send the confirmed bill to the customer.

Flow:

``` text
Bill confirmed
      ↓
Ask:
"Send bill on WhatsApp?"
      ↓
Yes
      ↓
Ask phone number
      ↓
Validate number
      ↓
Confirm number
      ↓
Generate invoice
      ↓
Send
```

## Important

The invoice should come from the confirmed database transaction.

------------------------------------------------------------------------

# PHASE 19 --- Family Testing With Dummy Data

## Goal

Test the system with your mother and father.

Do not immediately replace the entire dummy database with real data.

Test:

-   Natural speaking style
-   Product pronunciation
-   Tamil/Tanglish
-   Repeated products
-   Corrections
-   Ambiguous product names
-   Units
-   Quantities
-   Customer names

Record failures.

Example:

``` text
Mother said:
"Marie five"

System understood:
Marie Light ₹10

Correct:
Marie Light ₹5
```

Add this real-world phrase as an alias/rule.

This is valuable product development data.

------------------------------------------------------------------------

# PHASE 20 --- Replace Dummy Rates With Real Shop Data

## Goal

Import actual products and rates.

## Strategy

Do not change the application logic.

Replace the product master data.

This demonstrates good separation between:

``` text
Application code
        +
Business data
```

The code should continue working.

------------------------------------------------------------------------

# PHASE 21 --- Stock Management

## Goal

Reduce stock manually tracking work.

When a sale is confirmed:

``` text
Stock
  ↓
Decrease sold quantity
```

Example:

``` text
Bingo ₹5
Stock = 100 Saram

Sold = 3 Saram

New stock = 97 Saram
```

This phase should come only after billing is reliable.

------------------------------------------------------------------------

# PHASE 22 --- Wholesale vs Retail

## Goal

Support the family business's two sales modes.

Possible:

``` text
Retail
Wholesale
```

The same product can have:

``` text
retail_rate
wholesale_rate
```

The system must know which pricing mode applies.

Do not guess.

If the business rules are unclear, ask.

------------------------------------------------------------------------

# PHASE 23 --- Audit Logs and Corrections

## Goal

Track important changes.

Example:

``` text
Bill INV-102

Original:
₹1,366

Changed:
Bingo ₹5
1 -> 2

Changed by:
Father

Timestamp:
Automatically recorded
```

This makes the system safer for real business use.

------------------------------------------------------------------------

# PHASE 24 --- Error Handling and Reliability

## Goal

Make the application robust.

Handle:

-   MongoDB unavailable
-   LLM API unavailable
-   Speech-to-text failure
-   Empty voice message
-   Unknown product
-   Multiple product matches
-   Invalid quantity
-   Invalid unit
-   Duplicate WhatsApp message
-   Network timeout
-   Missing customer name
-   Missing price
-   Missing conversion rule

Never silently continue with incorrect financial information.

------------------------------------------------------------------------

# PHASE 25 --- Testing

## Goal

Create automated tests.

Especially test:

### Billing

``` text
2 × ₹222 = ₹444
```

### Bundle

``` text
1 Kings bundle
= 20 × ₹222
= ₹4,440
```

### Mixed order

``` text
2 pieces + 1 bundle
```

### Invalid product

Should return an error.

### Ambiguous product

Should ask for clarification.

### Historical price

Old sale should retain old rate.

### Daily report

Database totals must match individual sales.

------------------------------------------------------------------------

# PHASE 26 --- Security

## Goal

Protect the system.

Implement:

-   Environment variables
-   Secret management
-   Authentication
-   User roles
-   Input validation
-   API security
-   Database access controls
-   Logging
-   Safe error messages

Mother and father should have appropriate access.

------------------------------------------------------------------------

# PHASE 27 --- Production Deployment

## Goal

Make the system accessible outside the local computer.

Potential architecture:

``` text
WhatsApp
   ↓
Public HTTPS endpoint
   ↓
Cloud-hosted FastAPI
   ↓
MongoDB
   ↓
AI services
```

Deployment technology can be selected later based on cost and
simplicity.

Do not deploy before the local workflow is stable.

------------------------------------------------------------------------

# PHASE 28 --- Real Family Pilot

## Goal

Use the system for a limited period in the actual shop.

Start with:

-   a subset of products
-   controlled billing
-   manual verification

Do not immediately depend on the system for every sale.

Compare:

``` text
System bill
vs
Actual/manual bill
```

Track mistakes.

------------------------------------------------------------------------

# PHASE 29 --- Improve From Real Usage

## Goal

Use actual family feedback to improve the system.

Measure:

-   Product recognition accuracy
-   Quantity recognition
-   Unit recognition
-   Billing accuracy
-   Number of corrections
-   Unknown products
-   Ambiguous products
-   Voice recognition failures
-   Time saved

The real-world testing becomes the feedback loop.

------------------------------------------------------------------------

# PHASE 30 --- Advanced Features

Only after the core system is stable consider:

-   Sales analytics
-   Product popularity
-   Low-stock alerts
-   Daily/weekly/monthly reports
-   Customer purchase history
-   Credit tracking
-   Profit analysis
-   Voice responses
-   Advanced multilingual support
-   Semantic product search
-   RAG for business documentation
-   Dashboard
-   Backup/restore
-   Advanced audit system

These are secondary.

The core product must remain:

**Accurate billing + easy voice input + reliable sales records + fast
sales search.**

------------------------------------------------------------------------

# Recommended Fastest MVP

If the goal is to help your mother quickly, do not wait for all 30
phases.

The first useful MVP should be:

``` text
Phase 0
Project setup

Phase 1
MongoDB

Phase 2
Product database

Phase 3
Dummy products

Phase 4
Product search

Phase 5
Billing engine

Phase 6
Structured order

Phase 7
LLM extraction

Phase 8
Product resolver

Phase 9
AI -> bill

Phase 10
Confirmation/corrections

Phase 11
Save sale

Phase 12
Father search

Phase 13
Daily sales
```

At this point, the core system is already useful.

Then:

``` text
Voice
   ↓
Tamil/Tanglish
   ↓
WhatsApp
   ↓
Customer invoice
   ↓
Real data
```

------------------------------------------------------------------------

# Definition of Done for the MVP

The MVP is considered successful when a user can do this:

``` text
Mother:

"Satya, three Filter, one Scissor, two Kings."

        ↓

System understands the order.

        ↓

System retrieves exact rates.

        ↓

System calculates:

Filter     3 × ₹118 = ₹354
Scissor    1 × ₹100 = ₹100
Kings      2 × ₹222 = ₹444

Total = ₹898

        ↓

Mother confirms.

        ↓

Sale saved.

        ↓

Father:

"What did Satya buy today?"

        ↓

System retrieves the exact saved sale.

        ↓

Father sees:

Filter     3 Packet
Scissor    1 Piece
Kings      2 Piece

Total = ₹898
```

This is the first major finish line.

------------------------------------------------------------------------

# Important Development Rule

Do not build the project as a collection of disconnected AI demos.

Build it as one continuous product:

``` text
PRODUCT DATA
     ↓
ORDER
     ↓
UNDERSTANDING
     ↓
PRODUCT MATCHING
     ↓
PRICE LOOKUP
     ↓
BILLING
     ↓
CONFIRMATION
     ↓
SALE
     ↓
SEARCH
     ↓
REPORTING
     ↓
WHATSAPP
```

Every new phase must connect to the previous phase.

------------------------------------------------------------------------

# Learning Rule for Every Coding Session

Before writing code, explain:

## 1. What are we building?

Give the exact technical task.

## 2. Why?

Connect it to the shop's real problem.

## 3. How?

Explain the architecture and data flow.

## 4. Code

Write the smallest clean implementation.

## 5. Run

Show how to run it.

## 6. Test

Give a real example.

## 7. Verify

Explain what success looks like.

## 8. Learn

Explain the underlying concept in beginner-friendly interview language.

## 9. Continue

Only move to the next phase after the current phase works.

------------------------------------------------------------------------

# Final Product Vision

The final system should feel like a simple shop assistant rather than a
complicated software application.

Mother should be able to:

**Speak -\> Review -\> Confirm**

Father should be able to:

**Ask -\> Search -\> Verify**

The system should handle the complicated work in the background:

**Speech -\> AI understanding -\> Product matching -\> Database -\>
Exact pricing -\> Billing -\> Transaction history -\> Search**

The purpose of the project is not to use AI everywhere.

The purpose is to use AI **where AI is useful**, and deterministic
software **where accuracy is critical**.
