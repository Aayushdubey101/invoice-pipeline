# Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│  Client                                                     │
│  apps/web  (Next.js 15, port 3000)                         │
│  ┌──────────────┐  ┌─────────────┐  ┌────────────────────┐ │
│  │ Upload page  │  │Review queue │  │ Review detail      │ │
│  │ DropZone     │  │TanStack Q   │  │ PDF + FieldEditor  │ │
│  └──────┬───────┘  └──────┬──────┘  └────────┬───────────┘ │
└─────────┼─────────────────┼─────────────────┼──────────────┘
          │  HTTP/JSON       │                 │
┌─────────▼─────────────────▼─────────────────▼──────────────┐
│  API                                                        │
│  apps/api  (FastAPI, port 8000)                             │
│  ┌────────────┐  ┌──────────────┐  ┌───────┐  ┌─────────┐ │
│  │ /documents │  │ /review      │  │/invoi-│  │/vendors │ │
│  │ upload     │  │ queue/approve│  │ces    │  │         │ │
│  └────────────┘  └──────────────┘  └───────┘  └─────────┘ │
│                                                             │
│  Pipeline Orchestrator (pipeline.py)                        │
│  ingest → classify → text_extract → ocr_fallback →         │
│  field_extract → confidence_score → canonicalize →          │
│  persist → notify                                           │
└──────────────────┬──────────────────────────────────────────┘
                   │
        ┌──────────┴──────────┐
        │                     │
┌───────▼──────┐   ┌──────────▼────────────┐
│  PostgreSQL  │   │  ChromaDB             │
│  (port 5432) │   │  (port 8001)          │
│              │   │                       │
│  documents   │   │  vendor embeddings    │
│  invoices    │   │  (all-MiniLM-L6-v2)  │
│  inv_fields  │   └───────────────────────┘
│  line_items  │
│  vendors     │
│  audit_log   │
└──────────────┘
```

## Pipeline Stage Detail

```
File bytes (PDF/image/email)
        │
        ▼
┌─────────────────┐
│    ingest       │  SHA256 → document_id
│                 │  Idempotency: if hash exists → return cached
│                 │  MIME allowlist: pdf, png, jpg, tiff, eml, msg, html, txt
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    classify     │  text_pdf: pdfplumber avg chars/page ≥ 50
│                 │  scanned_pdf: avg chars/page < 50
│                 │  image: mime type image/*
│                 │  email: mime type message/rfc822 or .msg
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
text_extract  (email: unstructured + attachment recursion)
    │
    ▼
ocr_fallback  (only if text < threshold)
    │         PaddleOCR → Tesseract fallback
    │
    ▼
field_extract  LLM single call via instructor
    │          Schema: Invoice(invoice_number, vendor_name, ..., line_items[])
    │          Each field: FieldValue(value, confidence 0–1, evidence snippet)
    │
    ▼
confidence_score
    │          base = LLM self-reported
    │          +0.1 if date parseable
    │          +0.1 if currency recognized (ISO 4217)
    │          +0.2 if subtotal + tax ≈ total
    │          +0.1 if vendor matched
    │          cap 1.0; flag needs_review=true if any field < 0.75
    │
    ▼
canonicalize
    │          dates: dateparser → YYYY-MM-DD
    │          currency: babel.numbers → ISO 4217 + Decimal
    │          vendor: rapidfuzz ≥90 → Chroma cosine ≥0.85 → new vendor
    │          tax IDs: python-stdnum validation
    │
    ▼
persist        documents + invoices + invoice_fields + line_items + audit_log
    │
    ▼
notify         webhook POST (non-fatal on failure)
               review queue flag
```

## Database Schema

```sql
documents     id(sha256), filename, mime_type, file_size_bytes, doc_type,
              status, errors jsonb, created_at, updated_at

vendors       id(uuid), canonical_name, aliases jsonb, address, tax_id,
              status, embedding_id, created_at, updated_at

invoices      id(uuid), document_id→documents, vendor_id→vendors,
              invoice_number, invoice_date, due_date, total_amount(numeric),
              currency, payment_terms, purchase_order,
              needs_review bool, review_reasons jsonb, raw_extraction jsonb,
              created_at, updated_at

invoice_fields id(uuid), invoice_id→invoices, field_name,
               raw_value, canonical_value, confidence(float),
               evidence, needs_review bool, reviewed bool, reviewed_value,
               created_at, updated_at

line_items    id(uuid), invoice_id→invoices, position int,
              description, quantity(numeric), unit_price(numeric),
              total(numeric), currency, confidence(float),
              created_at

audit_log     id(uuid), document_id→documents, actor, stage, action,
              before_hash, after_hash, metadata jsonb, created_at
              (INSERT ONLY — never update or delete)
```

## LLM Provider Abstraction

```
LLMProvider (Protocol)
│   async def extract(text, schema, system_prompt, temperature) → (BaseModel, ExtractionMeta)
│
├── LMStudioProvider    instructor + AsyncOpenAI → LM Studio endpoint
├── OpenAIProvider      instructor + AsyncOpenAI → api.openai.com
├── AnthropicProvider   instructor + AsyncAnthropic
└── GeminiProvider      instructor + google-genai

Factory auto-detect order:
  1. LLM_PROVIDER env var explicit
  2. LM Studio: GET {LM_STUDIO_BASE_URL}/models, 2s timeout
  3. ANTHROPIC_API_KEY set?
  4. OPENAI_API_KEY set?
  5. GEMINI_API_KEY set?
  6. raise NoLLMProviderConfigured
```

## Frontend Data Flow

```
UploadDropzone
  → POST /documents/upload → {document_id, status, errors}
  → navigate to /review on success

ReviewQueue  (TanStack Query)
  → GET /review/queue → {items: [...], total}
  → search/filter client-side
  → <Link href="/review/{id}"> per item

Review Detail  (/review/[id])
  → GET /invoices/{id} → invoice + fields + line_items
  → dynamic import PdfViewer (SSR disabled, react-pdf v10)
  → FieldEditor inline edits → PATCH /review/{id}/field/{field_id}
  → POST /review/{id}/approve | reject
  → invalidate ["review-queue"] on success

VendorsPage
  → GET /vendors/ → list
  → PATCH /vendors/{id} → canonical_name + aliases
```

## Key Design Decisions

### Pipeline: Never Raise

Stages attach errors to `document.errors[]` instead of raising. A failed OCR stage doesn't abort field extraction — it proceeds with empty text. This means partial extraction is always possible, and the failure reason is always inspectable.

### Decimal for Money

All monetary values use `decimal.Decimal` — never `float`. Postgres `NUMERIC` columns preserve precision. The `canonical_value` stored in `invoice_fields` is a string representation of the Decimal to avoid any precision loss.

### SHA256 Document ID

The document's SHA256 hash is its primary key. Re-uploading the same file is fully idempotent without any additional locking or DB lookup by filename. The deduplication check is a single indexed primary key lookup.

### Audit Log: Insert-Only

The `audit_log` table has no UPDATE or DELETE paths in the codebase. This is enforced by convention (the repository never calls those operations on this table) and documented here. Compliance requirements treat audit entries as immutable facts.

### Vendor Canonicalization: Two-Stage

rapidfuzz (CPU, microseconds) runs first. Only on a miss does the pipeline invoke sentence-transformers + ChromaDB (milliseconds but heavier). This keeps the common case fast for known vendors.

### Frontend: TanStack Query + Cache Invalidation

All server state lives in TanStack Query. After approve/reject/edit, the query cache for `["review-queue"]` and `["invoice", id]` is invalidated, triggering a background refetch. No manual state sync.
