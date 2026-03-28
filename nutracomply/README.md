# RegBite — AI-Powered FSSAI Compliance Platform

RegBite is an AI-powered SaaS platform for checking Indian nutraceutical and health supplement labels against **64 compliance rules** spanning FSSAI, Legal Metrology, and AYUSH regulations.

**Live:** https://steadfast-courage-production-0f66.up.railway.app/

---

## Table of Contents

- [How It Works](#how-it-works)
- [User Flows](#user-flows)
  - [Registration & Onboarding](#1-registration--onboarding)
  - [Product Management](#2-product-management)
  - [Label Upload & Compliance](#3-label-upload--compliance-analysis)
  - [Dashboard](#4-dashboard)
  - [Reports](#5-reports)
  - [Alerts & Notifications](#6-alerts--notifications)
  - [Regulation Feed](#7-regulation-feed)
  - [Team Management](#8-team-management)
  - [Billing & Subscriptions](#9-billing--subscriptions)
  - [License Renewal Tracker](#10-license-renewal-tracker)
  - [Blog](#11-blog)
  - [Settings](#12-settings)
  - [Admin Panel](#13-admin-panel)
  - [Public Pages](#14-public-pages)
- [Compliance Engine](#compliance-engine)
- [AI Architecture](#ai-architecture)
- [Tech Stack](#tech-stack)
- [Configuration](#configuration)
- [Quick Start](#quick-start)
- [Route Reference](#route-reference)
- [Security](#security)

---

## How It Works

```
Upload Label Image/PDF
        |
        v
  +------------------+
  |   Gemini Vision   |  <-- Extracts 39 structured fields
  |   (2.5 Pro)       |      from label image
  +------------------+
        |
        v
  +------------------+
  |  64-Rule Engine   |  <-- FSSAI + Legal Metrology + AYUSH
  |  (Category-aware) |      Severity-weighted scoring
  +------------------+
        |
        v
  +------------------+
  | Compliance Report |  <-- Per-rule PASS/FAIL/WARNING
  | Score + Critical  |      Remediation guidance
  | Alerts + PDF      |      Shareable links
  +------------------+
```

---

## User Flows

### 1. Registration & Onboarding

```
/register  -->  /onboarding (3 steps)  -->  /dashboard
```

**Registration** (`/register`)
- Provide name, email, and password
- Password requires: 10+ characters, uppercase + lowercase + digit
- On registration: 5 demo products are auto-seeded for exploration
- If your email matches the `ADMIN_EMAIL` env var, you are granted admin access

**Onboarding** (`/onboarding`)
- **Step 1:** Company name + GSTIN (India tax ID)
- **Step 2:** Create your first real product (optional)
- **Step 3:** Confirmation — marks onboarding complete
- Skip option available at each step

**Login** (`/login`)
- Email + password authentication
- JWT stored in `access_token` httpOnly cookie (2-hour expiry)
- Rate-limited: 5 attempts per 5 minutes per email+IP combination
- Inactive accounts are blocked from login

**Logout** (`/logout`)
- Clears auth cookie, redirects to login

---

### 2. Product Management

```
/products  -->  /products/add  -->  /products/{id}
                                        |
                                        v
                                /products/{id}/upload
```

**Product List** (`/products`)
- View all active products with compliance status badges
- Quick-add product form (name, SKU, category, description)
- Optional: attach a label image at creation time

**Product Categories:**
- Health Supplement
- Nutraceutical
- Functional Food
- Food for Special Dietary Use
- Novel Food
- Ayurvedic / ASU (triggers AYUSH-specific rules)

**Product Detail** (`/products/{id}`)
- Product info, all label versions (history), latest compliance score
- Upload new label, view past analysis results
- Delete product (soft-delete)

**Bulk Upload** (`/products/bulk-upload`)
- Upload CSV or Excel (.xlsx/.xls) with columns: name, sku, category, description
- Auto-validates categories, skips duplicates by name
- Shows result: added/skipped/errors count

---

### 3. Label Upload & Compliance Analysis

```
Upload Image/PDF  -->  Background Processing  -->  Report Ready
```

**Upload** (`POST /products/{id}/upload`)
- Supported formats: JPEG, PNG, TIFF, WebP, PDF
- File validation: extension check + magic byte MIME verification + 50MB size limit
- Rate-limited: 30 uploads per hour
- Quota-checked against subscription plan limits

**Background Processing (async):**

1. **OCR** — Extracts raw text from image/PDF (PaddleOCR + Tesseract with Hindi support)

2. **AI Extraction** — Gemini Vision API structures the label into 39 fields:
   - Critical (7): product_name, product_type_declaration, fssai_license_number, net_quantity, expiry_date, manufacturer_details, ingredient_list
   - Important (9): serving_size, mfg_date, batch_number, storage_conditions, veg/non-veg mark, MRP, nutritional_table, warnings, allergen_declarations
   - Additional (23): health_claims, RDA percentages, advisory statements, country_of_origin, customer_care, formulation_reference, etc.

3. **Token-Saving Cache** — If a previous extraction has confidence >= 0.85, the cached result is reused (zero API tokens). Only the rules engine re-runs.

4. **Compliance Check** — 64 rules evaluated, filtered by product category

5. **Alert Generation** — CRITICAL/HIGH violations trigger in-app alerts + email notifications

6. **LLM KB Feed** — Product data is fed into the RAG knowledge base for admin querying

**Re-analysis** (`POST /labels/{id}/reanalyze`)
- Without `?force_extract=1`: reuses cached extraction, re-runs rules only
- With `?force_extract=1`: forces fresh Gemini API call + full re-analysis

---

### 4. Dashboard

**Route:** `/dashboard`

The main overview screen after login. Shows:

| Widget | Description |
|--------|-------------|
| **Product Summary** | Total products, compliant (score >= 80%), flagged (< 80%), pending (no label) |
| **Category Breakdown** | Products grouped by regulatory category |
| **Unread Alerts** | Count of unread compliance alerts |
| **Expiring Licenses** | Licenses expiring within 90 days (sorted by urgency) |
| **Regulation Alerts** | 3 most recent published regulation updates |
| **Notifications** | Unread notification count |

---

### 5. Reports

```
/labels/{id}  -->  /reports/generate/{label_id}  -->  /reports/{id}
                                                          |
                                                      /reports/{id}/download (PDF)
                                                      /reports/{id}/share (link)
```

**Report List** (`/reports`)
- All compliance reports for your account, newest first

**Report Detail** (`/reports/{id}`)
- Full compliance analysis: weighted score, critical score, violation summary
- Per-rule results grouped by: Failed, Warnings, Passed
- Each failed rule shows: severity badge, rule code, description, actual value found, remediation guidance

**PDF Download** (`/reports/{id}/download`)
- Generates branded PDF report (uses your custom brand name + color from Settings)
- Falls back to HTML download if PDF engine unavailable

**Share Link** (`POST /reports/{id}/share`)
- Creates a 30-day shareable link at `/r/{token}`
- No authentication required to view shared reports

**Quick Checker** (`/checker`)
- Manual compliance check without uploading an image
- Fill in label fields (product name, category, ingredients, claims, dates, etc.)
- Runs same 64-rule engine, generates report instantly
- Available from the landing page hero section
- Rate-limited: 20 checks per hour

---

### 6. Alerts & Notifications

**Compliance Alerts** (`/alerts`)
- Triggered automatically when label analysis finds CRITICAL or HIGH severity violations
- Each alert contains: violation list with rule codes, severities, and remediation steps
- Status workflow: UNREAD → ACKNOWLEDGED → IN_PROGRESS → RESOLVED
- Bulk "Mark All Read" action
- Email sent to registered notification addresses

**In-App Notifications** (`/notifications`)
- System notifications for: payments, team invites, report generation, etc.
- Types: info, success, warning, alert
- Auto-marked as read when page loads
- Optional deep links to relevant pages

**Regulation Alerts** (`/reg-alerts`)
- Admin-published updates about FSSAI regulation changes
- Filterable by severity: Informational, Important, Urgent
- Shows affected product categories

---

### 7. Regulation Feed

**Route:** `/regulations`

Two tabs:

| Tab | Content |
|-----|---------|
| **Feed** | Regulation changes detected by the FSSAI scraper, grouped by month |
| **Rules** | Searchable database of all 64 compliance rules with filters (category, severity, source) |

---

### 8. Team Management

```
/team  -->  Send Invite (email + role)  -->  Recipient gets /team/accept/{token}
```

**Team Dashboard** (`/team`)
- Requires Account Admin or Super Admin role
- View team members with roles, invite new members
- Change member roles, remove members
- View and revoke pending invites

**Invite Flow:**
- Select role: Editor, Viewer, or Consultant
- System generates unique invite token (7-day expiry)
- Share the invite URL with your team member

**Accept Invite** (`/team/accept/{token}`)
- Recipient creates account (name + password)
- Automatically linked to inviter's team
- Assigned the invited role
- Logged in immediately after acceptance

**Roles:**
| Role | Permissions |
|------|-------------|
| **Super Admin** | Full platform access + admin panel |
| **Account Admin** | Manage team, products, billing, settings |
| **Editor** | Add/edit products and labels |
| **Viewer** | Read-only access to reports and dashboards |
| **Consultant** | External advisor access |

---

### 9. Billing & Subscriptions

**Route:** `/billing`

Integrated with **Razorpay** (India's payment gateway).

**Plans:**

| Feature | Free | Growth (₹2,999/mo) | Enterprise |
|---------|------|---------------------|------------|
| Products | 5 | 50 | Unlimited |
| Scans/month | 10 | 200 | Unlimited |
| Reports | Basic | Branded PDF | Custom |
| Team | 1 user | 5 users | Unlimited |

**Payment Flow:**
1. Select plan → Razorpay checkout modal opens
2. Complete payment → Razorpay sends callback
3. Backend verifies signature (HMAC-SHA256)
4. Subscription activated, user.plan updated
5. Redirect to billing page with success message

**Webhook:** `POST /billing/webhook` — handles async payment events from Razorpay

**Cancel:** Downgrades to Free plan, access continues until billing period ends

---

### 10. License Renewal Tracker

**Route:** `/renewals`

Track expiry dates for regulatory licenses:

- **License Types:** FSSAI, AYUSH, IEC, BIS, State License, Other
- **Status Colors:** Active (green), Expiring within 60 days (amber), Expiring within 30 days (red), Expired (red)
- **Actions:** Add new license, update expiry (renew), delete
- **Dashboard Integration:** Expiring licenses (90-day window) shown on dashboard

---

### 11. Blog

**Public Blog** (`/blog`)
- Listing page with category filter pills, tag filtering, pagination (12/page)
- Featured posts grid (up to 3 pinned articles)
- SEO-optimized with meta tags and canonical URLs

**Blog Post** (`/blog/{slug}`)
- Full article with category badge, author, published date
- View counter (auto-incremented)
- Related articles section (same category)
- Share via copy-link button

**Admin Blog CMS** (`/admin/blog`)
- Dashboard with stats (total posts, published, drafts, total views)
- WYSIWYG editor (Quill.js) with rich text formatting
- Post management: Create, Edit, Publish, Archive, Delete
- Category management: Create/delete categories with auto-slugs
- SEO fields: meta title, meta description, featured image URL
- Status workflow: Draft → Published → Archived

---

### 12. Settings

**Route:** `/settings`

| Section | What It Does |
|---------|--------------|
| **Profile** | Update display name |
| **Password** | Change password (validates current, enforces complexity) |
| **Notifications** | Add up to 5 email addresses for compliance alert delivery |
| **Branding** | Custom brand name + color for PDF reports |
| **API Keys** | Create/revoke API keys (max 5 active, format: `rb_live_...`) |

---

### 13. Admin Panel

Accessible at `/admin/*` routes. Requires `is_admin=True`.

| Section | Route | Purpose |
|---------|-------|---------|
| **Dashboard** | `/admin/dashboard` | Platform-wide stats, growth metrics, recent signups |
| **Users** | `/admin/users` | User management — toggle active/admin, view details + activity |
| **Rules** | `/admin/rules` | Edit compliance rules — severity, description, remediation text |
| **Reg KB** | `/admin/regulations-kb` | Sync rules from seed file, seed/reseed LLM knowledge base |
| **Alerts** | `/admin/alerts` | View all system alerts with severity/type/status filters |
| **Published Alerts** | `/admin/published-alerts` | Compose regulation alert bulletins for users |
| **Blog** | `/admin/blog` | Full CMS (see Blog section above) |
| **LLM Studio** | `/admin/llm` | Manage RAG knowledge bases (regulations + products), upload docs, test chat |
| **Activity Log** | `/admin/activity` | Platform activity log (paginated, filterable by time) |
| **System** | `/admin/system` | DB stats, env info, trigger FSSAI scrape or full re-check |

**LLM Studio** (`/admin/llm`) provides:
- Two knowledge bases: Regulations and Products
- Auto-seed from database or upload custom documents (PDF/text)
- Document chunking for RAG retrieval
- Chat test interface to query the KB
- Stats: document count, chunk count, last updated

---

### 14. Public Pages

No authentication required.

| Route | Page |
|-------|------|
| `/` | Landing page with hero analyzer, feature showcase, social proof |
| `/features` | Detailed features: AI Scanner, 64-Rule Engine, regulation coverage |
| `/about` | Mission, values (Accuracy, Simplicity, India-First), team |
| `/contact` | Contact form (name, email, company, inquiry type, message) |
| `/pricing` | Plan comparison (Free / Growth / Enterprise) |
| `/blog` | Public blog listing |
| `/help` | Searchable FAQ accordion (Getting Started, Compliance, Billing, Technical) |
| `/terms` | Terms of Service (14 sections) |
| `/privacy` | Privacy Policy (data collection, third-party services, retention) |
| `/changelog` | Product version history (v1.0 → v3.2) |
| `/health` | Health check endpoint for Railway deployment monitoring |

---

## Compliance Engine

### 64 Rules Across 3 Frameworks

| Framework | Count | Scope |
|-----------|-------|-------|
| **FSSAI-NUTRA** | 43 | FSS Health Supplements, Nutraceuticals Regulations 2022 |
| **LM-PKG** | 9 | Legal Metrology (Packaged Commodities) Rules |
| **AYUSH-ASU** | 12 | Ayurvedic, Siddha, Unani product regulations |

### Rule Categories

| Category | Examples |
|----------|----------|
| **MANDATORY_FIELD** | Product type declaration, FSSAI license, net quantity, expiry date |
| **PROHIBITED_CLAIM** | Disease cure/treatment claims, misleading efficacy claims |
| **INGREDIENT_RESTRICTION** | Banned substances (Raspberry ketone, Saw palmetto, Guarana, etc.) |
| **FORMAT_REQUIREMENT** | English language, minimum font size, bilingual labeling |
| **QUANTITY_REQUIREMENT** | Serving size, %RDA per ICMR guidelines |
| **ALLERGEN_REQUIREMENT** | Allergen declaration format and completeness |
| **CLAIM_SUBSTANTIATION** | Health claim verification, advisory statements |

### Category-Aware Filtering

- **All products** get FSSAI + Legal Metrology rules (52 rules)
- **Ayurvedic/ASU products** additionally get 12 AYUSH-specific rules
- This prevents false positives from AYUSH rules on non-Ayurvedic products

### Scoring

**Weighted Compliance Score:**
- CRITICAL rule weight: 4x
- HIGH rule weight: 3x
- MEDIUM rule weight: 2x
- LOW rule weight: 1x
- Warnings receive 50% credit
- Score = (weighted_earned / weighted_total) x 100

**Critical Score:** Separate metric tracking only CRITICAL rule pass/fail rate. Shown prominently on reports when critical failures exist.

---

## AI Architecture

### Two AI Brains

**1. Extraction Brain (Gemini Vision)**
- Model: `gemini-2.5-pro-preview-06-05` (vision) / `gemini-2.0-flash` (text fallback)
- Extracts 39 structured fields from label images
- Confidence scoring: vision base 0.90, text base 0.82
- Validation layer: checks field completeness, format correctness
- Fallback: regex-based extraction if API fails

**2. Compliance & RAG Brain**
- Powered by Gemini with retrieval-augmented generation
- Two knowledge bases: Regulations (rules + amendments) and Products (extraction results)
- Used for: FORMAT-type rule checks (visual/bilingual verification), admin queries
- Document chunking with title boosting and stopword filtering

### Token-Saving Strategy
- Extraction results cached with confidence scores
- If existing extraction confidence >= 0.85: reuse cached data, only re-run rules engine
- This saves Gemini API tokens on re-analysis and batch re-checks

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Framework** | FastAPI + Jinja2 (SSR) |
| **Database** | PostgreSQL (Railway) / SQLite (local dev) |
| **ORM** | SQLAlchemy 2.0 |
| **Auth** | JWT (python-jose) + bcrypt |
| **AI** | Google Gemini 2.5 Pro (Vision) + Gemini 2.0 Flash (Text) |
| **OCR** | PaddleOCR + Tesseract (Hindi + English) |
| **PDF** | pdfplumber, PyMuPDF, WeasyPrint |
| **Task Queue** | Celery + Redis |
| **Email** | Brevo SMTP (300 free/day) |
| **Payments** | Razorpay (India) |
| **Scraping** | httpx + BeautifulSoup4 (FSSAI monitoring) |
| **Sanitization** | nh3 (Rust-based HTML sanitizer) |
| **Deploy** | Railway (auto-deploy on push to main) |
| **Design** | Monochrome Japanese minimal — Noto Sans JP, #111111 ink, #F8F8F8 bg |

---

## Configuration

### Environment Variables (.env)

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | `sqlite:///./regbite.db` (dev) or PostgreSQL URL (prod) |
| `SECRET_KEY` | Yes | Random 64+ char string for JWT signing |
| `GEMINI_API_KEY` | Yes | Google AI Studio API key |
| `REDIS_URL` | No | Redis URL (for Celery background tasks) |
| `ADMIN_EMAIL` | No | Email auto-promoted to super admin |
| `BREVO_SMTP_USER` | No | Brevo SMTP username |
| `BREVO_SMTP_PASSWORD` | No | Brevo SMTP password |
| `ALERT_FROM_EMAIL` | No | Sender address for alert emails |
| `ALERT_TO_EMAIL` | No | Default recipient for system alerts |
| `RAZORPAY_KEY_ID` | No | Razorpay API key |
| `RAZORPAY_KEY_SECRET` | No | Razorpay API secret |
| `RAZORPAY_WEBHOOK_SECRET` | No | Razorpay webhook signing secret |
| `DB_POOL_SIZE` | No | Connection pool size (default: 5) |
| `DB_MAX_OVERFLOW` | No | Pool overflow (default: 10) |
| `DB_STATEMENT_TIMEOUT` | No | Query timeout in ms (default: 30000) |

---

## Quick Start

### Option A: Local Development (SQLite)

```bash
cd nutracomply
pip install -r requirements.txt

# Create .env file
echo "DATABASE_URL=sqlite:///./regbite.db" > .env
echo "SECRET_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(64))')" >> .env
echo "GEMINI_API_KEY=your-key-here" >> .env

# Start server
uvicorn app.main:app --reload --port 8000
```

Visit http://localhost:8000 — register an account, add a product, upload a label.

### Option B: Docker (PostgreSQL + Redis)

```bash
cd nutracomply
cp .env.example .env
# Edit .env: add GEMINI_API_KEY, configure DATABASE_URL

docker-compose up --build
```

### Option C: Railway (Production)

Push to `main` branch — Railway auto-deploys via Dockerfile.

```bash
git push origin main
```

Health check: `/health` verifies DB connectivity.

---

## Route Reference

### Public (No Auth)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/` | Landing page (redirects to `/dashboard` if logged in) |
| GET | `/features` | Features page |
| GET | `/about` | About page |
| GET | `/contact` | Contact form |
| POST | `/contact/submit` | Submit contact form |
| GET | `/pricing` | Pricing page |
| GET | `/blog` | Blog listing |
| GET | `/blog/{slug}` | Blog post |
| GET | `/help` | FAQ / Help |
| GET | `/terms` | Terms of Service |
| GET | `/privacy` | Privacy Policy |
| GET | `/changelog` | Changelog |
| GET | `/health` | Health check (JSON) |
| GET | `/r/{token}` | Shared report (public link) |
| GET | `/reg-alerts` | Regulation alerts feed |

### Auth

| Method | Route | Description |
|--------|-------|-------------|
| GET/POST | `/login` | Login |
| GET/POST | `/register` | Registration |
| GET | `/logout` | Logout |
| GET/POST | `/onboarding` | Onboarding wizard |
| GET/POST | `/team/accept/{token}` | Accept team invite |

### App (Requires Auth)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/dashboard` | Main dashboard |
| GET | `/products` | Product list |
| POST | `/products/add` | Add product |
| GET | `/products/{id}` | Product detail |
| POST | `/products/{id}/delete` | Delete product |
| GET/POST | `/products/{id}/upload` | Upload label |
| GET/POST | `/products/bulk-upload` | Bulk CSV upload |
| GET | `/labels/{id}` | Label compliance report |
| POST | `/labels/{id}/reanalyze` | Re-run analysis |
| GET | `/reports` | Report list |
| GET | `/reports/{id}` | Report detail |
| GET | `/reports/{id}/download` | PDF download |
| POST | `/reports/{id}/share` | Create share link |
| GET | `/reports/generate/{label_id}` | Generate report |
| GET/POST | `/checker` | Quick compliance checker |
| GET | `/alerts` | Compliance alerts |
| POST | `/alerts/{id}/status` | Update alert status |
| POST | `/alerts/mark-all-read` | Mark all read |
| GET | `/notifications` | Notifications |
| GET | `/regulations` | Regulation feed + rules DB |
| GET | `/renewals` | License tracker |
| POST | `/renewals/add` | Add license |
| POST | `/renewals/{id}/renew` | Renew license |
| POST | `/renewals/{id}/delete` | Delete license |
| GET | `/settings` | All settings |
| POST | `/settings/profile` | Update profile |
| POST | `/settings/password` | Change password |
| POST | `/settings/notifications` | Update notification emails |
| POST | `/settings/branding` | Update report branding |
| GET | `/settings/api-keys` | API key management |
| POST | `/settings/api-keys/create` | Create API key |
| POST | `/settings/api-keys/{id}/revoke` | Revoke API key |
| GET | `/team` | Team management |
| POST | `/team/invite` | Send invite |
| POST | `/team/members/{id}/role` | Change role |
| POST | `/team/members/{id}/remove` | Remove member |
| POST | `/team/invites/{id}/revoke` | Revoke invite |
| GET | `/billing` | Billing page |
| POST | `/billing/create-order` | Create Razorpay order |
| POST | `/billing/verify-payment` | Verify payment |
| POST | `/billing/cancel` | Cancel subscription |
| POST | `/billing/webhook` | Razorpay webhook |

### Admin (Requires is_admin=True)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/admin/dashboard` | Admin overview |
| GET | `/admin/users` | User management |
| GET | `/admin/users/{id}` | User detail |
| POST | `/admin/users/{id}/toggle-*` | Toggle user flags |
| GET | `/admin/rules` | Compliance rules editor |
| POST | `/admin/rules/{id}/edit` | Edit rule |
| POST | `/admin/rules/{id}/toggle-active` | Toggle rule |
| GET | `/admin/regulations-kb` | Knowledge base management |
| POST | `/admin/regulations-kb/sync-rules` | Sync rules from seed file |
| POST | `/admin/regulations-kb/seed-llm` | Seed LLM knowledge base |
| POST | `/admin/regulations-kb/reseed-llm` | Clear + reseed LLM KB |
| GET | `/admin/alerts` | All alerts (filtered) |
| GET | `/admin/published-alerts` | Regulation alert composer |
| POST | `/admin/published-alerts/create` | Create alert bulletin |
| GET | `/admin/blog` | Blog CMS dashboard |
| GET | `/admin/blog/new` | New blog post editor |
| GET | `/admin/blog/{id}/edit` | Edit blog post |
| GET | `/admin/blog/categories` | Blog categories |
| GET | `/admin/llm` | LLM Studio dashboard |
| GET | `/admin/llm/{kb_type}/train` | KB document management |
| GET | `/admin/llm/{kb_type}/chat` | Chat test interface |
| GET | `/admin/activity` | Activity log |
| GET | `/admin/system` | System info + controls |
| POST | `/admin/trigger-scrape` | Trigger FSSAI scrape |
| POST | `/admin/trigger-recheck` | Re-check all labels |

---

## Security

| Measure | Implementation |
|---------|---------------|
| **CSRF Protection** | Double-submit cookie pattern, auto-injected via JS on all forms |
| **XSS Prevention** | Blog content sanitized with nh3 (Rust-based), Jinja2 auto-escaping |
| **File Upload** | Extension whitelist + magic byte MIME validation + 50MB size limit |
| **Password Policy** | Minimum 10 chars, requires uppercase + lowercase + digit |
| **Brute Force** | 5 login attempts per 5 minutes per email+IP (fail-closed rate limiter) |
| **JWT** | httpOnly cookie, 2-hour expiry, HS256 signing |
| **Webhook Validation** | Razorpay HMAC-SHA256 signature verification |
| **SQL Injection** | SQLAlchemy ORM parameterized queries |
| **Statement Timeout** | 30-second PostgreSQL query timeout |
| **Structured Logging** | JSON-formatted request logging with method, path, status, duration |

---

## Database Schema (Key Models)

```
User
  ├── Product[]
  │     ├── LabelVersion[]
  │     │     ├── ComplianceCheck[]  ──> ComplianceRule
  │     │     └── Alert[]
  │     └── ComplianceReport[]
  ├── Subscription
  ├── PaymentRecord[]
  ├── LicenseRenewal[]
  ├── Notification[]
  ├── APIKey[]
  └── ActivityLog[]

BlogCategory
  └── BlogPost[]

KBDocument
  └── KBChunk[]

LLMConversation
TeamInvite
RegulationChange
PublishedAlert
```

---

## Demo Accounts

| Account | Email | Password | Role |
|---------|-------|----------|------|
| Customer | `ben` | `admin@123` | Regular user with 5 demo products |
| Admin | `admin` | `admin@123` | Super admin with full platform access |

---

*Built with FastAPI, Gemini AI, and 64 FSSAI compliance rules for India's nutraceutical industry.*
