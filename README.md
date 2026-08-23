# Invoice Intelligence Pipeline

<p align="center">
  <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&size=20&pause=1000&color=2E86FF&center=true&vCenter=true&width=600&lines=Extract+structured+data+from+any+invoice;PDF+%7C+Scan+%7C+Image+%7C+Email;LLM+extraction+%2B+confidence+scoring;Human-in-the-loop+review+UI" alt="typing-svg" />
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-FastAPI-009688?logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/Next.js-15-black?logo=next.js" />
  <img src="https://img.shields.io/badge/PostgreSQL-async-4169E1?logo=postgresql&logoColor=white" />
  <img src="https://img.shields.io/badge/Qdrant-vector%20db-DC244C" />
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white" />
  <img src="https://img.shields.io/badge/LLM-OpenAI%20%7C%20Anthropic%20%7C%20Gemini%20%7C%20Groq%20%7C%20Ollama-purple" />
  <img src="https://img.shields.io/badge/License-MIT-green" />
</p>

Upload any invoice — text PDF, scanned PDF, image, or email — and get back clean, structured, confidence-scored data. Low-confidence fields drop into a side-by-side review UI for a human to check.

## 🔴 Live Demo

**[invoice-intelligence.duckdns.org](https://invoice-intelligence.duckdns.org/)**

> Hosted on a personal server for demo purposes — may go down or be unavailable at any time, no uptime guarantee.

## Features

- 🤖 **Multi-provider LLM extraction** — OpenAI, Anthropic, Gemini, Groq, or local models via Ollama/LM Studio, with auto-detection and fallback
- 📄 **Any input format** — text PDFs, scanned PDFs/images (OCR), emails
- ✅ **Per-field confidence scoring** — flags low-confidence fields for review
- 🔎 **Vendor matching** — fuzzy match + vector embeddings (Qdrant) to auto-canonicalize vendor names
- 👀 **Human-in-the-loop review UI** — PDF side-by-side with editable, highlighted fields
- 🔁 **Idempotent uploads** — SHA256 dedup, re-uploads return the cached result
- 🔐 **Guest mode + Clerk auth** — try it instantly, or sign in for persistent workspaces
- 📊 **Audit trail** — every state change logged, immutably

## Quick Start

```bash
git clone https://github.com/Aayushdubey101/invoice-pipeline
cd invoice-pipeline
cp .env.example .env          # pick your LLM provider
docker compose up -d          # starts postgres, qdrant, api, web
./scripts/seed.sh             # loads sample invoices + vendors
open http://localhost:3000
```

## How It Works

```
upload → classify → extract text/OCR → LLM field extraction
       → confidence scoring → canonicalize → review queue
```

| Stage | What it does |
|---|---|
| Extract | pdfplumber for text PDFs, PaddleOCR/Tesseract for scans & images |
| LLM extract | Structured field extraction via `instructor`, across 5 provider options |
| Confidence | LLM confidence + math/date/vendor checks → flags for review |
| Canonicalize | Dates → ISO, currency → Decimal, vendor → matched via Qdrant |
| Review | Human approves/edits flagged fields in the web UI |

## Tech Stack

**Backend:** Python, FastAPI, SQLAlchemy (async), PostgreSQL, Qdrant, `instructor`
**Frontend:** Next.js, TypeScript, Tailwind, shadcn/ui
**Infra:** Docker Compose, deployed on AWS EC2

## Deployment

Runs anywhere Docker does. Includes production overrides (`docker-compose.prod.yml`) and a Render deploy path — see `SETUP.md` for details. This instance is deployed on AWS EC2.

## Author

**Aayush Dubey** — [GitHub](https://github.com/Aayushdubey101)

## License

MIT — see [LICENSE](LICENSE).
