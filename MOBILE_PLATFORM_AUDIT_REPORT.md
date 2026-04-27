# RegBite Mobile Platform Audit

Date: 2026-04-28  
Primary auditor stance: senior mobile software tester + product/engineering auditor  
Scope: responsive web product only, not native iOS/Android

## Executive Summary

RegBite is **mobile-capable but not yet mobile-ready for mission-critical compliance work**.

The product already has the right structural ingredients for mobile use: a dedicated public shell, an authenticated app shell with hamburger and bottom navigation, an admin shell, clear empty states, and a strong shared-report experience. A mobile user can sign in, navigate the workspace, view compliance reports, inspect alerts, and read public guidance pages without the app collapsing.

However, the audit found three gaps that materially lower trust on phone-sized screens:

1. **Governance controls are exposed to the wrong roles.** Read-only users can still reach sensitive billing and API-key screens on mobile.
2. **Two important admin surfaces are broken.** `/admin/users` and `/admin/api-usage` return `500` in the audited local environment.
3. **Core workflows are still desktop-first.** Product review, extraction editing, tables, admin operations, and several management screens are technically responsive but not designed for fast, accurate use on a phone.

The bottom line is straightforward: **mobile is acceptable today for monitoring, reading, and lightweight review, but not yet safe or efficient for governance, power-user operations, or deep remediation work**.

## Executive Verdict

If RegBite is positioned as a field-accessible compliance platform, the current mobile experience is only partially aligned with that promise. The strongest mobile experience is in **viewing** trust artifacts such as shared reports, alerts, and public guidance. The weakest experience is in **managing** the system: billing, API keys, admin workflows, extraction editing, and data-heavy lists.

From a leadership perspective, the priority is not cosmetic polish. The first mobile work should focus on:

- access-control integrity,
- broken admin pages,
- onboarding containment,
- notification behavior,
- and redesigning the core product review surfaces from tables into task-driven cards and sections.

## Mobile Maturity Scorecard

| Domain | Score (5) | Assessment | Commentary |
|---|---:|---|---|
| Public marketing and trust pages | 3.8 | Solid | Readable, credible, and mostly stable on mobile, though long and content-dense. |
| Authentication and onboarding | 2.6 | Mixed | Login works; onboarding exists; route gating is inconsistent after sign-in. |
| Authenticated app shell | 3.5 | Solid base | Hamburger and mobile navigation are present and functional. |
| Core product workflows | 2.5 | Weak | Product detail and extraction handling remain desktop-first and spreadsheet-like. |
| Compliance report readability | 3.9 | Strong | Report and shared-report views are among the best mobile surfaces. |
| Alerts and notifications | 2.8 | Mixed | Alerts are readable; notifications auto-mark read, which hurts mobile triage. |
| Team, billing, and governance | 1.9 | High risk | Sensitive pages are exposed to non-admin roles; table-heavy design remains. |
| Admin operations | 1.8 | High risk | Mobile shell exists, but two key pages crash and many screens are too dense. |
| Access-control integrity | 1.5 | Critical | Observed permissions do not consistently match intended role policy. |
| Overall mobile readiness | 2.7 | Not yet ready for heavy operational use | Good foundation, but trust and usability gaps remain. |

## What Works Well Today

- The app shell correctly renders a mobile navigation pattern rather than forcing the desktop sidebar into a narrow viewport.
- Public trust surfaces are coherent: the landing page, help content, blog content, and shared-report pages are readable and professional on mobile.
- The shared-report experience is especially strong: active links are readable, expired links are explicit, and the page frames the output as view-only rather than legal advice.
- Empty states are present across the core user experience and generally do the right thing.
- Read-only mutation prevention exists in some important places. For example, viewers cannot use label upload flows even though some surrounding access-control behavior is still inconsistent.
- The label report view is materially more mobile-friendly than the product detail editor. Severity counts, findings, evidence blocks, and preview framing remain understandable on a phone.

## Methodology

### Audit Environment

- Dedicated local server: `http://127.0.0.1:8002`
- Dedicated local database: `nutracomply/mobile_audit.db`
- Demo behavior disabled:
  - `ENABLE_DEMO_DATA=false`
  - `SHOW_DEMO_LOGIN_HINTS=false`
- Public base URL configured to the isolated audit server

### Test Personas

- `super_admin`
- `account_admin`
- `editor`
- `viewer`
- `consultant`
- onboarding-incomplete user
- empty-workspace user

### Seeded States

- empty workspace
- populated workspace
- archived product
- failing product/report
- active and expired shared reports
- alert-heavy account
- invite pending/acceptance flow
- billed subscription history
- API keys
- blog and regulation content

### Evidence Sources

- Live in-app browser walkthroughs on the mobile shell path
- Direct route verification by role
- Static review of routes, templates, CSS breakpoints, and access-control code
- Server-log review for failing screens

### Important Limitations

- The in-app browser clearly validated the mobile shell path, but exact device-width measurement was limited. Fine-grained `<=768px` and `<=480px` behavior was cross-checked with CSS/template inspection rather than inferred.
- Real external payment, email, OCR-provider, and scraper-provider flows were not executed live in this audit environment.
- This report evaluates the current mobile web product; it does not assess native app patterns.

## Severity-Ranked Findings

## Critical Findings

### C1. Billing Governance Is Exposed To Read-Only Roles

- Screen/workflow: `/billing`
- Role + viewport: `viewer`, `consultant`, and `editor` on the live mobile app shell
- Observed issue: read-only users can open the billing page on mobile and see payment history, subscription details, and a visible `Cancel Subscription` action.
- Business impact: this is a governance failure. On mobile, where users rely on visible cues more than deep context, it creates a strong false impression of authority and exposes sensitive commercial information to the wrong roles.
- Likely technical cause: the GET route renders the page without enforcing the billing permission check. Intended role policy exists in `nutracomply/app/services/access_control.py:49-58`, but the page route in `nutracomply/app/routes/billing.py:100-123` does not apply `_require_billing_user`.
- Recommended fix: enforce the same permission gate on the GET route and all billing actions, hide billing navigation for non-authorized roles, and replace access failures with a clear `403` or a read-only explanation screen rather than a silent redirect.

### C2. API-Key Management Is Exposed To Read-Only Roles

- Screen/workflow: `/settings/api-keys`
- Role + viewport: `viewer`, `consultant`, and `editor` on the live mobile app shell
- Observed issue: read-only users can reach the API-key management page and see existing keys, a key-creation form, and revoke controls.
- Business impact: this is both an information-disclosure problem and a governance problem. Even if some mutation endpoints are protected elsewhere, the mobile UI exposes secrets-related management surfaces to roles that should never see them.
- Likely technical cause: intended policy exists, but the GET page is not permission-gated. The route in `nutracomply/app/routes/settings.py:235-240` renders the page without checking `can_manage_api_keys`, even though the permission helper is already available.
- Recommended fix: apply the same permission gate to page render and actions, remove the navigation item for non-authorized roles, and show a scoped account-admin-only explainer where appropriate.

## High Findings

### H1. Admin User Management Crashes On Mobile And Desktop

- Screen/workflow: `/admin/users`
- Role + viewport: `super_admin`, live mobile shell and direct route check
- Observed issue: the screen returns `500` instead of rendering the user-management experience.
- Business impact: this blocks one of the core admin responsibilities and undermines confidence in the admin console as an operational tool.
- Likely technical cause: the template sorts on `user.company_name` without handling `None`. The failure originates from `nutracomply/app/templates/admin/users.html:154`.
- Recommended fix: make the sort null-safe in the route or template, add a regression test with null company names, and avoid view-time sorting where missing data can crash rendering.

### H2. Admin API Usage Page Is Not Portable Across Environments

- Screen/workflow: `/admin/api-usage`
- Role + viewport: `super_admin`, direct route validation in the local mobile audit environment
- Observed issue: the page returns `500`.
- Business impact: local QA, demo environments, and portability testing are impaired. That weakens release confidence for an already dense operational surface.
- Likely technical cause: the query in `nutracomply/app/routes/admin.py:848-860` uses PostgreSQL-style `INTERVAL '5 hours 30 minutes'`, which breaks under SQLite in the audit environment.
- Recommended fix: move timezone bucketing into SQLAlchemy/database-agnostic logic, or perform the conversion in Python after querying UTC timestamps. Add an explicit compatibility test for local SQLite runs.

### H3. Onboarding Is Enforced Only On `/dashboard`

- Screen/workflow: onboarding containment
- Role + viewport: onboarding-incomplete account-admin user on the mobile shell
- Observed issue: an onboarding-incomplete user is redirected from `/dashboard` to `/onboarding`, but can still open other authenticated routes such as `/products`, `/checker`, `/alerts`, `/billing`, `/team`, and `/settings`.
- Business impact: mobile first-run experience becomes inconsistent and users can bypass setup, landing directly in screens that assume a configured workspace.
- Likely technical cause: onboarding gating is implemented narrowly in `nutracomply/app/main.py:947-967` rather than centrally across authenticated app routes.
- Recommended fix: centralize onboarding enforcement in middleware or a shared dependency for all protected app routes, with an allowlist only for onboarding, logout, and a minimal account-recovery set.

### H4. Notifications Auto-Mark As Read On Open

- Screen/workflow: `/notifications`
- Role + viewport: `account_admin` on live mobile shell
- Observed issue: opening the notifications page marks unread notifications as read immediately. The page itself indicates that all notifications are marked as read on visit.
- Business impact: on mobile, accidental opens are common. Auto-read behavior destroys the user's triage state and makes unread counts unreliable as a working memory aid.
- Likely technical cause: the route in `nutracomply/app/routes/notifications.py:18-30` updates unread notifications during page load rather than on explicit user action.
- Recommended fix: switch to explicit `Mark all read` or per-item read controls, and preserve unread state until the user intentionally acknowledges it.

### H5. Unauthorized Checker Access Redirects To Login Instead Of Showing A Permission State

- Screen/workflow: `/checker`
- Role + viewport: `viewer` and `consultant` on live mobile shell
- Observed issue: authenticated users without checker permission are redirected to the login page.
- Business impact: this creates a false sign-out or session-loss impression on mobile, which is especially confusing when users depend on browser back behavior and limited screen context.
- Likely technical cause: the helper in `nutracomply/app/routes/checker.py:53-57` returns `None` for unauthorized users, and the route in `nutracomply/app/routes/checker.py:84-89` treats that as a login redirect condition.
- Recommended fix: return a proper permission error or a role-aware explanation page that tells the user why checker access is unavailable.

### H6. Product Detail And Extraction Editing Are Still Desktop-First

- Screen/workflow: `/products/{id}` and associated extraction editing
- Role + viewport: `account_admin` and `editor` on live mobile shell
- Observed issue: the product detail page presents a dense editing surface with spreadsheet-like fields, long forms, nested tables, and wide content clusters. It is technically responsive but not ergonomically mobile.
- Business impact: this is one of the highest-value workflows in the product. If mobile users cannot comfortably validate extracted fields, compare evidence, and fix issues, the product cannot fully support field or on-the-go review.
- Likely technical cause: the template is still structured as a dense desktop editing form. Key concentration is in `nutracomply/app/templates/product_detail.html:88-247`.
- Recommended fix: redesign the page into stacked sections or accordions: product facts, claims, ingredients, nutrition, packaging claims, evidence preview, and remediation actions. Keep one sticky primary action only.

### H7. The Mobile Dashboard Is Informative But Not Triage-Oriented

- Screen/workflow: `/dashboard`
- Role + viewport: `account_admin` on live mobile shell
- Observed issue: the dashboard stacks KPI cards, products, renewals, alerts, recent activity, and quick actions into a long scroll. It reads like a compressed desktop homepage rather than a mobile command center.
- Business impact: users on mobile need prioritization, not density. A screen meant to orient the user should surface urgent work first.
- Likely technical cause: mobile styling compresses the same overall module set rather than re-sequencing the page for phone use.
- Recommended fix: rebuild the mobile dashboard around `Do next`, `Critical issues`, `Recent scans`, and `Pending renewals`, with secondary analytics moved below the fold or behind a secondary tab.

## Medium Findings

### M1. Core List Screens Remain Table-First Rather Than Phone-First

- Screen/workflow: `/products`, `/products/archived`, `/reports`, `/renewals`, `/billing`, `/settings/api-keys`, `/admin/products`, `/admin/rules`, `/admin/blog`, `/admin/blog/categories`
- Role + viewport: multiple roles on live mobile shell and template inspection
- Observed issue: many core screens still rely on tables that hide a few columns on smaller widths but keep desktop interaction patterns.
- Business impact: horizontal compression, action clustering, and low scanability increase error risk and reduce throughput on mobile.
- Likely technical cause: responsive CSS trims columns at smaller breakpoints, but the underlying information architecture remains tabular. Example concentration appears in `nutracomply/app/templates/products.html:49-62` and `nutracomply/app/templates/products.html:171-239`.
- Recommended fix: move primary mobile views to stacked cards with one-line status summaries, visible primary action, and expandable detail drawers.

### M2. Team Management Is Partially Mobile-Adapted But Still Operationally Heavy

- Screen/workflow: `/team` and invite acceptance
- Role + viewport: `account_admin` and invited user
- Observed issue: the page includes some mobile fallback treatment, but role management, invite status, and action controls still read as a compressed admin table. Invite acceptance is simpler and cleaner than the management page itself.
- Business impact: account admins can technically manage the team on a phone, but it is slower and easier to misread than necessary.
- Likely technical cause: mixed paradigms in `nutracomply/app/templates/team.html`, including a mobile card fallback around `:135-140` but continued table/action density further down.
- Recommended fix: split the page into two phone-sized sections: `Members` and `Invites`, with role edits hidden behind clear secondary actions.

### M3. Empty Workspaces Still Show Global Regulation Content Without Strong Provenance Framing

- Screen/workflow: empty-state dashboard and related feeds
- Role + viewport: empty-workspace account-admin on live mobile shell
- Observed issue: even when the workspace has no products or reports, mobile users still encounter regulation-alert content. The page does not strongly distinguish global platform intelligence from workspace-specific work.
- Business impact: for new users, this can blur what is actionable now versus what is general industry context.
- Likely technical cause: shared/global content modules are rendered alongside workspace modules without strong provenance labels.
- Recommended fix: clearly label global regulation cards as `Industry update` and separate them visually from workspace tasks such as `Your products`, `Your alerts`, and `Your renewals`.

### M4. Admin LLM And Label-Extractor Screens Are Responsive But Not Mobile-Native

- Screen/workflow: `/admin/llm`, `/admin/llm/regulations/train`, `/admin/llm/regulations/chat`, `/admin/label-extractor`
- Role + viewport: `super_admin`, live mobile shell and static template review
- Observed issue: these screens render, but they depend on long forms, text-heavy output, and dense operational detail. On a phone they are inspectable, but not efficient.
- Business impact: mobile admins can monitor these tools, but substantial work still wants a laptop-class layout.
- Likely technical cause: desktop admin tools were compressed for narrow widths rather than reauthored for mobile task slices.
- Recommended fix: define a mobile-admin scope explicitly. On phone, allow status viewing, job retries, and short notes; keep full training, curation, and extractor debugging in a desktop-optimized flow.

### M5. The Landing Page Is Trustworthy But Overloaded For Small Screens

- Screen/workflow: `/`
- Role + viewport: public mobile shell
- Observed issue: the page presents a strong value proposition and good trust framing, but mobile users must scroll through a lot of explanatory content before reaching secondary destinations.
- Business impact: new visitors may understand the product, but the journey is slower than it should be, especially for users coming from shared links or direct recommendations.
- Likely technical cause: the mobile page preserves the full storytelling arc from desktop rather than compressing it into fewer decisive sections.
- Recommended fix: shorten the mobile top half, add a more obvious `Sign in to scan` or `See sample report` path, and defer secondary proof points lower.

### M6. Public Long-Form Surfaces Could Use Better In-Page Navigation

- Screen/workflow: `/help`, `/blog`, blog post pages, `/terms`, `/privacy`, `/changelog`
- Role + viewport: public mobile shell and static review
- Observed issue: the content is readable, but long pages lack stronger chapter-jump patterns, sticky mini-TOCs, or more decisive return actions.
- Business impact: mobile users can consume the content, but not skim or recover as efficiently as they could.
- Likely technical cause: content pages are optimized for narrative reading rather than mobile reference behavior.
- Recommended fix: add sticky section jump links, compact section summaries, and a clearer end-of-page CTA back to the app or help hub.

## Low Findings

### L1. 404 Recovery Works But Could Recover Faster

- Screen/workflow: invalid public route
- Role + viewport: public mobile shell
- Observed issue: the 404 state is functional, but the recovery path can be more opinionated.
- Business impact: low severity, but mobile users benefit from quick escape hatches.
- Likely technical cause: standard fallback page without a strong task-based CTA.
- Recommended fix: add primary actions for `Go to home`, `Sign in`, and `Open help`.

### L2. Some Role Expectations Are Still Implied Rather Than Explicit

- Screen/workflow: mixed app surfaces
- Role + viewport: all roles
- Observed issue: in several places the UI relies on redirects or missing actions rather than clearly saying what a role can and cannot do.
- Business impact: low immediate severity, but it increases confusion and support burden.
- Likely technical cause: permissions are enforced route-by-route rather than supported by a consistent UI pattern.
- Recommended fix: add role-aware helper text and empty states such as `Your role can review but not edit`.

## Role Matrix Summary

| Role | Mobile result | Main observation |
|---|---|---|
| `super_admin` | Mixed | Admin shell reachable, but `/admin/users` and `/admin/api-usage` fail. Direct account-owned product/report routes do not behave like normal workspace access, which is acceptable for a platform admin but should be explicit. |
| `account_admin` | Mixed-positive | Main workspace is usable on mobile. Dashboard, products, reports, alerts, billing, team, checker, and settings all render, but several key screens are dense. |
| `editor` | Risky | Can reach productive workflows, but also sees governance pages that should be reserved for account admins. |
| `viewer` | Risky | Correctly blocked from upload/edit flows in some places, but can still reach billing and API-key screens and is misrouted to login for checker denial. |
| `consultant` | Risky | Same pattern as viewer: strong read-only intent, inconsistent route protection, confusing checker redirect. |
| onboarding-incomplete user | Weak | Redirected to onboarding from `/dashboard` but can bypass setup through other routes. |
| empty-workspace user | Positive with caveat | Empty-state rendering is good, but global regulation content can blur the product narrative for a brand-new account. |

## Screen Coverage Appendix

### Public Surfaces

| Surface | Validation mode | Result | Key mobile observation |
|---|---|---|---|
| `/` | Live | Reachable | Good trust framing, but long and content-heavy. |
| `/pricing` | Route + template review | Reachable | Not visually broken; likely acceptable, but not materially optimized for short mobile comparison. |
| `/features` | Route + template review | Reachable | Informationally strong; should be compressed for faster skim. |
| `/about` | Route + template review | Reachable | Stable. |
| `/contact` | Route + template review | Reachable | Stable. |
| `/help` | Live | Reachable | Readable; long-form navigation can improve. |
| `/terms` | Route + template review | Reachable | Long-form legal content; acceptable baseline. |
| `/privacy` | Route + template review | Reachable | Long-form legal content; acceptable baseline. |
| `/changelog` | Route + template review | Reachable | Readable but long. |
| `/login` | Live | Reachable | Clear and usable on mobile. |
| `/register` | Route + template review | Reachable | No major mobile blocker seen. |
| `/blog` | Live | Reachable | Card/list pattern is acceptable. |
| `/blog/{slug}` | Live | Reachable | Good reading experience; lacks stronger in-page nav. |
| shared report active | Live | Reachable | Strong mobile artifact. |
| shared report expired | Live | Reachable | Clear state and recovery message. |
| invalid route / 404 | Live | Reachable | Recovery could be more direct. |

### Authenticated User Surfaces

| Surface | Validation mode | Result | Key mobile observation |
|---|---|---|---|
| `/onboarding` | Live | Reachable | Flow exists, but enforcement is not comprehensive. |
| `/dashboard` | Live | Reachable | Informative but too dense for triage. |
| `/products` | Live | Reachable | Still table-first. |
| `/products/bulk-upload` | Live | Reachable | Usable, though copy and control density are high. |
| `/products/archived` | Live | Reachable | Table-first mobile treatment. |
| `/products/{id}` | Live | Reachable | Core mobile weakness due to extraction-edit complexity. |
| `/products/{id}/upload` | Live | Reachable | Upload control is usable; role denial works better here than elsewhere. |
| `/labels/{id}` | Live | Reachable | Stronger mobile trust view than product detail. |
| `/reports` | Live | Reachable | Works, but still list/table heavy. |
| `/reports/{id}` | Live | Reachable | Report detail is one of the better mobile app pages. |
| `/checker` | Live | Reachable for authorized roles | Unauthorized roles get a misleading login redirect. |
| `/alerts` | Live | Reachable | Readable; alert handling is workable on mobile. |
| `/notifications` | Live | Reachable | Auto-read behavior undermines triage value. |
| `/regulations` | Live | Reachable | Content readable; provenance separation can improve. |
| `/reg-alerts` | Live | Reachable | Good for awareness; stronger workspace/global distinction recommended. |
| `/renewals` | Live | Reachable | Table/list density remains desktop-first. |
| `/settings` | Route + template review | Reachable | General settings acceptable. |
| `/settings/api-keys` | Live | Reachable | Critical role leakage. |
| `/team` | Live | Reachable for admin roles | Partially adapted, still operationally dense. |
| `/team/accept/{token}` | Live | Reachable | Cleaner than the main team-management screen. |
| `/billing` | Live | Reachable | Critical role leakage plus dense mobile layout. |

### Admin Surfaces

| Surface | Validation mode | Result | Key mobile observation |
|---|---|---|---|
| `/admin/dashboard` | Live | Reachable | Renders, but dense and analytic-heavy. |
| `/admin/users` | Live | `500` | Broken due to null-unsafe sorting. |
| `/admin/products` | Live | Reachable | Large table, low phone efficiency. |
| `/admin/rules` | Live | Reachable | Dense review screen, still desktop-oriented. |
| `/admin/alerts` | Live/route check | Reachable | Functional, but dense. |
| `/admin/published-alerts` | Route check | Reachable | Not fully visually stressed, but reachable. |
| `/admin/activity` | Route check | Reachable | Likely table-heavy by design; needs mobile simplification. |
| `/admin/api-usage` | Route check | `500` | Breaks in local SQLite audit environment. |
| `/admin/finance` | Route check | Reachable | Likely desktop-first. |
| `/admin/system` | Route check | Reachable | Operational surface, not yet phone-native. |
| `/admin/llm` | Live | Reachable | Readable summary page, but dense. |
| `/admin/llm/regulations/train` | Live | Reachable | Too form-heavy for sustained phone use. |
| `/admin/llm/regulations/chat` | Live | Reachable | Technically works, but long conversational/admin outputs are cumbersome on mobile. |
| `/admin/label-extractor` | Live | Reachable | Phone-usable for quick checks, not for deep debugging. |
| `/admin/blog` | Live | Reachable | Table/list density remains high. |
| `/admin/blog/categories` | Live | Reachable | Similar density issue. |

## Root-Cause Themes

### 1. Responsive Shells Exist, But Information Architecture Is Still Desktop-Led

RegBite has responsive wrappers, not consistently mobile-native task design. Many pages shrink, stack, or hide columns, but they still preserve the mental model of a desktop back office.

### 2. Permission Logic And UI Visibility Are Not Reliably Aligned

The most serious mobile trust issue is not visual. It is the mismatch between intended role policy and actual page reachability or visible controls.

### 3. Operational Screens Were Compressed, Not Reauthored

Admin analytics, rules, API usage, billing, and team management all show signs of being ported to narrow widths rather than redesigned for mobile decision-making.

### 4. RegBite’s Best Mobile Experience Is Evidence Viewing, Not Data Correction

Shared reports and label reports communicate trust well on a phone. Extraction editing, account management, and admin curation do not.

## Quick Wins

- Close the role leaks on `/billing` and `/settings/api-keys`.
- Replace checker login redirects with a permission state.
- Stop auto-marking notifications as read.
- Fix `/admin/users` null-safe sorting.
- Fix `/admin/api-usage` for non-PostgreSQL environments.
- Add stronger role-aware labels such as `Read-only access` on viewer and consultant screens.
- Add recovery-forward CTAs on the mobile 404 page.

## Medium-Lift Improvements

- Replace mobile tables for products, reports, renewals, team, and billing with stacked cards.
- Rebuild the dashboard into an urgent-work-first mobile layout.
- Rework product detail into sectioned accordions with one sticky primary action.
- Separate workspace content from global regulation intelligence more clearly.
- Split team management into smaller phone-first sections.
- Add mobile jump navigation for long public content pages.

## Strategic Redesign Opportunities

- Create a dedicated **mobile compliance review mode** focused on evidence, mismatch severity, remediation checklist, and sign-off rather than full record editing.
- Create a **mobile admin triage mode** that limits phone tasks to approvals, exceptions, retries, and alerts while reserving full data curation for desktop.
- Introduce a **trust ledger pattern** across reports and product detail: source citation, confidence explanation, regulator mapping, and unresolved issues should be visible in a single collapsible mobile narrative.

## Prioritized Remediation Roadmap

### Wave 1: Trust And Access Integrity

- Enforce role gates on billing and API-key pages and actions.
- Replace incorrect login redirects with `403` or role-aware explanation states.
- Stop auto-read notification behavior.
- Expand route-level mobile smoke tests for all roles.

### Wave 2: Admin Stability

- Fix `/admin/users` null handling.
- Remove PostgreSQL-only assumptions from `/admin/api-usage`.
- Add regression coverage for local audit environments and seeded admin data.

### Wave 3: Mobile Workflow Redesign

- Redesign products, reports, renewals, and team pages into cards and sections.
- Rebuild product detail and extraction editing for phone-first review.
- Re-sequence dashboard content around urgency and next action.

### Wave 4: Mobile Product Clarity

- Separate workspace tasks from global regulation intelligence more clearly.
- Improve long-form navigation for help/blog/legal pages.
- Add stronger role and provenance labeling throughout the app.

### Wave 5: Mobile Role-Specific Operating Modes

- Define mobile-appropriate scope for account admins, reviewers, and super admins.
- Keep evidence review and approvals on mobile.
- Push full curation, analytics, and bulk management toward desktop-first experiences.

## Live Validation Gaps

These areas were assessed by code and UI-state inspection rather than full live execution:

- live payment transaction flow
- live email delivery
- external scraper behavior
- OCR/AI-provider reliability under production traffic
- push-style or out-of-band notification delivery

## Final Assessment

RegBite already has enough mobile structure to be useful, but not enough mobile product design discipline to be trusted as a complete on-phone operating environment.

The good news is that this is not a ground-up rebuild problem. The strongest elements are already present: responsive shells, clear report framing, credible public pages, and enough route coverage to support a true mobile pathway. The next step is to close the control leaks and redesign the highest-value working surfaces around how people actually use a phone: short sessions, one-handed scanning, urgent review, and low-tolerance-for-confusion interactions.
