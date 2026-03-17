# NutraComply — FSSAI Compliance Monitor

Automated compliance checking for nutraceutical product labels against FSSAI regulations.

## What It Does

- **Upload label images/PDFs** → OCR extracts all text
- **AI extraction** (Google Gemini) → structures label into JSON fields
- **35+ FSSAI rules** → checks every field against current regulations
- **Detailed report** → per-rule PASS/FAIL with specific remediation guidance
- **Daily FSSAI scraper** → monitors fssai.gov.in for regulation changes
- **Auto re-check** → when regulations change, all labels are re-checked overnight
- **Alert inbox** → email + in-app alerts for violations and regulation updates

## Quick Start

### Prerequisites
- Python 3.11+
- Google Gemini free API key: https://aistudio.google.com/app/apikey
- Redis (only needed for the Phase 2 daily scraper worker — not required for label uploads)

### Option A: Local (Quickest — SQLite, no Docker needed)

```bash
cd nutracomply
pip install -r requirements.txt

cp .env.example .env
# Edit .env: add your GEMINI_API_KEY
# DATABASE_URL is already set to sqlite:///./nutracomply.db

# Run from the project root (CORDING/)
python run_api.py
```

Visit http://localhost:8000 — register, add a product, upload a label.

```bash
# Optional: start the Celery worker for daily FSSAI scraping (requires Redis)
celery -A app.workers.celery_app worker --beat --loglevel=info
```

### Option B: Docker (Full stack with PostgreSQL + Redis)

```bash
cd nutracomply
cp .env.example .env
# Edit .env: add GEMINI_API_KEY, set DATABASE_URL to postgresql://...
docker-compose up --build
```

## Configuration (.env)

| Variable | Description |
|---|---|
| `DATABASE_URL` | `sqlite:///./nutracomply.db` (dev) or PostgreSQL URL (prod) |
| `REDIS_URL` | Redis connection string (only needed for Celery worker) |
| `SECRET_KEY` | Random 64-char string for JWT signing |
| `GEMINI_API_KEY` | Free from https://aistudio.google.com/app/apikey |
| `BREVO_SMTP_*` | Free SMTP from https://app.brevo.com (300 emails/day) |
| `ALERT_TO_EMAIL` | Email to receive compliance alerts |

## Key URLs

| URL | Description |
|---|---|
| `/` | Redirects to dashboard |
| `/register` | Create your account |
| `/dashboard` | Compliance overview for all products |
| `/products` | Product / SKU management |
| `/products/{id}/upload` | Upload a label for analysis |
| `/labels/{id}` | Full compliance report |
| `/alerts` | Alert inbox |
| `/regulations` | FSSAI regulation change feed |
| `/docs` | Auto-generated FastAPI API docs |

## FSSAI Rules Covered (35+ rules)

### Mandatory Fields
- Product type declaration (HEALTH SUPPLEMENT / NUTRACEUTICAL)
- "NOT FOR MEDICINAL USE" statement
- FSSAI 14-digit license number
- Net quantity, serving size, %RDA per ICMR
- Expiry date, manufacturing date, batch number
- Manufacturer name + address, country of origin
- Veg/Non-veg mark, allergen declarations
- Storage conditions, "Keep out of reach of children"

### Prohibited Claims
- Disease treatment/cure claims
- Disease prevention claims
- Misleading efficacy claims ("miracle", "guaranteed cure")
- Dietary supplement substitution claims

### Banned Ingredients (2022 FSSAI ban)
- Raspberry ketone, Saw palmetto, Guarana (Paullinia cupana)
- Angelica sinensis, Notoginseng, Chaga extract
- Chlorella growth factor, Tea tree oil (internal use)

### Format Requirements
- English language mandatory
- Minimum font size compliance
- Allergen declaration format

## Tech Stack (all free/open-source)

- **FastAPI** + Jinja2 templates
- **PostgreSQL** + SQLAlchemy
- **Redis** + Celery (daily scraping, background processing)
- **PaddleOCR** (image OCR, Hindi+English)
- **pdfplumber** (PDF text extraction)
- **Google Gemini 1.5 Flash** (free API, structured extraction + regulation classification)
- **Brevo SMTP** (free email alerts, 300/day)
- **BeautifulSoup4** + httpx (FSSAI website scraping)
