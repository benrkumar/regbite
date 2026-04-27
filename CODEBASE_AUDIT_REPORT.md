# RegBite Codebase Audit Report

Date: 2026-04-17
Reviewer: Codex
Repository: `benrkumar/regbite`

## Purpose

This review evaluates RegBite as both:

1. A software platform
2. A regulatory-intelligence product whose core promise is:
   - learn and track FSSAI, Legal Metrology, AYUSH, BIS, and DGFT regulations
   - ingest regulation documents into a knowledge base
   - scan product labels and detect mismatches against those regulations

The review was done as a senior software tester and coder: product intent, correctness, security, operational behavior, and likely failure modes were all considered.

## Review Scope

Static code review covered these areas:

- App bootstrap, config, DB, migrations
- Auth, session handling, CSRF, roles/admin access
- Product creation, label upload, OCR/extraction, compliance checks
- Reports, sharing, alerts, notifications
- Billing and subscription enforcement
- Regulation scraper and change-classification flow
- LLM Studio / RAG ingestion / KB retrieval / rule extraction flows
- Quick checker / form-first flows
- Background tasks and scheduler/worker behavior

No automated test suite or live environment execution was run during this pass.

## Product Understanding

RegBite is a monolithic FastAPI + Jinja server-rendered SaaS application. The intended product loop is:

1. Learn regulations:
   - scrape or upload regulation documents
   - classify changes
   - store rules, regulation updates, and KB chunks
   - support admin review via LLM Studio

2. Learn products:
   - upload or manually create product label records
   - extract structured label data from images/PDFs
   - persist product and scan outputs into a product knowledge base

3. Detect mismatch:
   - compare extracted label fields against rule definitions
   - produce PASS/FAIL/WARNING checks, severity-weighted scores, alerts, and reports

Architecturally, this is not “LLM-only”. The main compliance decision engine is rule-based (`nutracomply/app/services/compliance_engine.py`), while the LLM/KB layer is secondary and mainly supports:

- format-sensitive checks
- regulation search/chat
- rule extraction from uploaded documents
- product KB recall

That separation is a good design choice, because it keeps the core compliance path deterministic.

## High-Level Strengths

- The platform has a clear separation between rule evaluation, extraction, and KB/RAG support.
- The product surface is broad and genuinely productized: billing, reports, team roles, notifications, admin console, public pages, and CMS are all integrated.
- Label processing stores both structured extraction and binary file data, which is good for auditability and preview resilience.
- The compliance engine is severity-aware and category-aware, which is important for realistic regulatory scoring.
- There is meaningful thought around fallback behavior: OCR fallback, provider fallback, in-process scheduler fallback, and report-sharing expiration.

## High-Risk Findings

### 1. API key leakage via URL query string

Severity: Critical

File:
- `nutracomply/app/routes/settings.py`

Issue:
- Newly created API keys are returned through a redirect query parameter (`new_key=...`).
- This leaks secrets into browser history, server logs, analytics tooling, reverse proxies, and referrer trails.

Why this matters:
- This is a direct credential-exposure issue, not just a UX concern.

Recommendation:
- Render the raw key only in a one-time POST response or one-time server-rendered page.
- Never place the raw secret in the URL.

### 2. Paid-plan cancellation removes entitlements immediately

Severity: Critical

Files:
- `nutracomply/app/routes/billing.py`
- `nutracomply/app/services/quota_service.py`

Issue:
- Cancellation marks the subscription cancelled and also immediately sets `user.plan = FREE`.
- Quota enforcement uses `user.plan`, so the system revokes paid quotas immediately even though messaging says access continues until the end of the billing period.

Why this matters:
- This is a contract/billing correctness issue and will produce customer-facing complaints.

Recommendation:
- Keep the effective plan active until `current_period_end`.
- Base quota checks on `Subscription.status/current_period_end`, not only denormalized `user.plan`.

### 3. Webhook can mark payment as paid without provisioning the subscription

Severity: Critical

File:
- `nutracomply/app/routes/billing.py`

Issue:
- `/billing/verify-payment` provisions subscription state.
- `/billing/webhook` only marks the payment record as paid.
- If the browser flow is interrupted after capture, the user can pay but never receive Growth access.

Why this matters:
- This creates revenue-without-entitlement and breaks trust.

Recommendation:
- Make webhook processing idempotently provision subscription state.
- Treat the frontend callback as convenience, not the only source of truth.

### 4. Quota bypass through bulk import and bulk upload paths

Severity: Critical

File:
- `nutracomply/app/routes/products.py`

Issue:
- Single-product creation checks quotas.
- Spreadsheet import, pasted CSV import, and bulk file upload do not enforce per-item plan limits consistently.

Why this matters:
- Free users can exceed both product and scan limits by using alternate flows.

Recommendation:
- Apply quota checks inside each bulk loop and stop/partially accept with clear reporting.
- Treat all write paths as equivalent from a billing-entitlement perspective.

### 5. Admin privilege revocation is inconsistent

Severity: Critical

File:
- `nutracomply/app/routes/admin.py`

Issue:
- Authorization relies on `user.is_admin`.
- Role changes update `role`, but demotions do not consistently clear `is_admin`.
- A user can therefore keep admin access after a nominal role downgrade.

Why this matters:
- This is a privilege-management defect with security implications.

Recommendation:
- Define one source of truth for authorization.
- Either derive admin access from role only, or always synchronize `role` and `is_admin` on every mutation.

## Major Product/Logic Findings

### 6. Regulation scraper is intentionally narrow and likely to miss important source documents

Severity: High

File:
- `nutracomply/app/services/scraper.py`

Observations:
- The scraper is restricted to a very small number of fixed URLs.
- It rejects many PDFs unless the URL/text passes keyword filters.
- PDF extraction only reads the first 5 pages.
- Result caps (`[:100]`, `[:25]`, `[:20]`) silently truncate discovery.

Why this matters for the product:
- The app’s “learning regulations” promise depends on coverage and freshness.
- Missing a source document means the knowledge base can be stale while still appearing healthy.

Recommendation:
- Expand source inventory and make it data-driven.
- Persist crawl metrics: pages checked, docs discovered, docs rejected, reject reason.
- Add alerting for source failures and unusually low discovery counts.
- Store full-document metadata and review rejected PDFs in admin UI.

### 7. Regulation feed exposes a source filter that is not actually applied

Severity: High

File:
- `nutracomply/app/routes/regulations.py`

Issue:
- `source` is accepted as a parameter and passed to the template as `filter_source`, but it is never used in the query.

Why this matters:
- Users/admins may believe they are filtering by regulator when they are not.
- That undermines trust in the regulation-review surface.

Recommendation:
- Either implement the filter or remove it from the UI/API.

### 8. Quick Checker creates persistent products instead of ephemeral analysis sessions

Severity: High

File:
- `nutracomply/app/routes/checker.py`

Issue:
- Manual quick checks and uploaded quick checks create full `Product` and `LabelVersion` records.
- They also feed the product KB.

Why this matters:
- “Quick check” behavior now mutates the customer’s product inventory and KB.
- That pollutes analytics, product counts, scan quotas, and product knowledge quality.
- Test or exploratory runs can become indistinguishable from real catalog data.

Recommendation:
- Separate ephemeral checks from canonical products.
- Introduce a temporary scan/session model or an `is_temporary`/`source=checker` lifecycle with cleanup rules.

### 9. Quick Checker does not mirror the main upload-validation path

Severity: High

Files:
- `nutracomply/app/routes/checker.py`
- `nutracomply/app/routes/labels.py`
- `nutracomply/app/routes/products.py`

Issue:
- Main label upload validates file signatures.
- Quick checker upload validates extension and size only.
- This means different entry points accept different inputs for the same product promise.

Why this matters:
- Testers and users will get inconsistent outcomes depending on which workflow they use.

Recommendation:
- Centralize upload validation and reuse it everywhere.

### 10. The report-share email integration is broken

Severity: High

Files:
- `nutracomply/app/routes/reports.py`
- `nutracomply/app/services/notification.py`

Issue:
- The caller passes `(user, product, share_url)`.
- The function expects `(user, product_name, share_url, expires_at)`.
- The exception is swallowed.

Why this matters:
- A user-visible “shared successfully” flow silently fails its notification side effect.

Recommendation:
- Fix the signature mismatch and add structured logging on failure.

## Medium-Risk Findings

### 11. Password policy is inconsistent across user flows

Severity: Medium

Files:
- `nutracomply/app/routes/auth.py`
- `nutracomply/app/routes/settings.py`
- `nutracomply/app/routes/team.py`

Issue:
- Registration uses a stronger 10-character mixed-case + digit rule.
- Password change and invite acceptance only require 8 characters.

Why this matters:
- Security guarantees vary depending on how the account was created or updated.

Recommendation:
- Centralize password policy and reuse the same validator across all flows.

### 12. Admin “label extractor” metrics appear to query a non-existent field

Severity: Medium

Files:
- `nutracomply/app/routes/admin_llm.py`
- `nutracomply/app/models.py`

Issue:
- The admin label-extractor page queries `LabelVersion.confidence`.
- The model defines `LabelVersion.extraction_confidence`.

Why this matters:
- The UI likely falls back to empty stats silently, which weakens observability of extraction quality.

Recommendation:
- Fix the field name and add a smoke test for admin analytics pages.

### 13. Alert badge counts are global, not user-scoped, across many pages

Severity: Medium

Examples:
- `nutracomply/app/routes/products.py`
- `nutracomply/app/routes/settings.py`
- `nutracomply/app/routes/reports.py`
- many others

Issue:
- `unread_alerts` frequently counts all unread alerts in the database instead of alerts relevant to the current user.

Why this matters:
- Users may see inflated or misleading alert badges based on other accounts’ alerts.

Recommendation:
- Scope alert queries by product ownership, report ownership, team, or intended audience.

### 14. Notification URLs are hard-coded to one Railway deployment hostname

Severity: Medium

File:
- `nutracomply/app/services/notification.py`

Issue:
- Emails point at a specific production URL everywhere.

Why this matters:
- This breaks staging/preview environments and complicates domain changes.

Recommendation:
- Use a configurable public base URL in settings.

### 15. KB retrieval is pragmatic but not strong enough for a regulation-heavy product at scale

Severity: Medium

File:
- `nutracomply/app/services/llm_service.py`

Observations:
- Retrieval is SQL `LIKE`-based with stopwords and score heuristics.
- This is workable for small corpora, but precision and recall will degrade as the regulations KB grows.
- The product’s “learn regulations” promise becomes increasingly retrieval-quality-sensitive.

Why this matters:
- RAG answers can look authoritative while missing the best source chunk.

Recommendation:
- Add retrieval-quality instrumentation.
- Consider semantic retrieval or hybrid search for the regulations KB.
- Add document/version metadata filters so newer amendments outrank superseded text.

## Architectural Assessment

### What is working well

- Deterministic rule engine remains central
- Label data is persisted for audit/replay
- Compliance results, product KB, and regulation KB are separate concepts
- There is a path toward admin-reviewed rule extraction from new regulation docs

### What is fragile

- Too many alternate flows implement near-duplicate behavior inconsistently
- Critical business logic is spread across routes rather than centralized services
- Multiple “soft fallback” patterns swallow exceptions, which hides product defects
- Scheduler and worker models are hybrid, which increases operational ambiguity

## Tester-Oriented Product Evaluation

From a software tester’s perspective, the most important question is:

“If a customer trusts RegBite to learn the latest regulation and then flag label mismatches correctly, what would make that trust fail?”

The main answers are:

1. Source coverage gaps in the scraper and KB ingestion
2. Inconsistent validation across scan entry points
3. Silent failure modes in notifications, metrics, and fallback logic
4. Alternate workflows polluting core product data
5. Billing and authorization inconsistencies that damage platform trust even if compliance logic is correct

So the product foundation is promising, but not yet fully trustworthy as a compliance-grade system without stronger controls around:

- source completeness
- data lineage
- entry-point consistency
- observability
- entitlement/security correctness

## Recommended Next Actions

### Immediate

1. Fix API key URL leakage
2. Fix billing entitlement logic and webhook provisioning
3. Fix admin-role synchronization
4. Apply quota checks to all bulk flows
5. Fix the report-share notification bug

### Short term

1. Unify upload validation and scan orchestration across all entry points
2. Make quick-check sessions ephemeral or explicitly separate from canonical products
3. Scope alert counts properly
4. Fix admin extractor metrics
5. Externalize the notification base URL

### Product-quality improvements

1. Add source-audit telemetry for regulation crawling
2. Track document versioning/supersession more explicitly in the KB
3. Add retrieval-quality evaluation for regulations chat
4. Add regression tests around rules, entitlements, and privileged admin actions
5. Add end-to-end “new regulation -> KB -> rule extraction -> scan mismatch” test scenarios

## Final Assessment

RegBite is a serious, real product with a strong base architecture for compliance analysis. The best part of the design is that it does not rely entirely on LLMs for compliance decisions; the rule engine remains the core authority. That is the right direction.

The biggest weaknesses are not cosmetic. They are trust issues:

- trust that the latest regulations were actually learned
- trust that all scan entry points behave the same
- trust that admin access and billing state are correct
- trust that notifications and analytics reflect reality

In short:

- Compliance engine direction: good
- Productization level: strong
- Trustworthiness for production compliance workflows: not yet high enough without targeted fixes

