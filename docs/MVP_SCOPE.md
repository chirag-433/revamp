# SIH MVP Scope: Institution Complaint Monitoring Dashboard

**Status:** Draft for the first prototype iteration  
**Evidence base:** The three supplied planning/research documents  
**Open validation:** Confirm the exact AICTE problem statement and its required fields/statuses before treating this scope as final.

## 1. Prototype goal

Show that authorized AICTE users can see institution-related cases from multiple Bureaus/Cells in one place, identify open cases that may need cross-Bureau coordination, review the evidence, and record a decision without merging or changing the source cases.

The prototype uses synthetic data. It does not connect to or write into production AICTE systems.

## 2. The demo journey

1. Import a synthetic RB or PGRC case through a CSV file or prepared mock source.
2. Resolve the institution using its AICTE Permanent ID when present. If it is missing, suggest a match using normalized institution name and location.
3. Find other open cases for the resolved institution in a different Bureau/Cell.
4. Show **“Potential Overlapping Cases – Coordination Required”** with the matched cases and reasons.
5. Let an officer confirm the overlap, mark the cases as related, or reject the suggestion. Record the decision in the case history.
6. Return to the dashboard and show the updated alert and case totals.

## 3. MVP scope

### Must include

- Synthetic institutions, cases, Bureaus/Cells, statuses, and case-action history.
- CSV ingestion for the demo, with source-system and source-case identifiers so re-importing a row does not create a duplicate.
- A canonical status mapping for the source statuses used in the demo.
- Institution resolution using exact Permanent ID first, then name plus district/state matching.
- A review state for uncertain institution matches; no automatic case merge.
- Cross-Bureau alerts when the same resolved institution has open cases in more than one Bureau/Cell.
- An explanation on each alert: institution match method/confidence, case status, Bureaus involved, and any useful category or issue-similarity evidence.
- A small dashboard, case list with essential filters, institution profile, case detail/timeline, and overlap review screen.
- Confirm/reject/related decisions recorded with actor and timestamp.
- Synthetic-data ground truth and a metrics view or report that calculates precision and recall from the generated dataset. Do not pre-fill an accuracy claim before measuring it.

### Defer until the core journey works

- Semantic embeddings and multilingual NLP.
- Conflict-action rules beyond the basic overlap alert.
- Email, SMS, WhatsApp, and mobile notifications.
- Production SSO, real AICTE integrations, cross-system write-back, and Kubernetes deployment.
- Predictive disposal-time analytics and complainant identity matching.
- A large report catalogue; add exports only after the core demo is stable.

## 4. Matching and alert behavior

### Institution resolution

1. If a valid Permanent ID matches the institution master, use that deterministic match.
2. Otherwise normalize the institution name and compare it with candidate names, using district and state as additional evidence.
3. Present uncertain candidates for human review. Keep the original text and the match explanation for auditability.

Thresholds must be configurable and tuned against labelled synthetic data. The example weights and thresholds in the source plan are hypotheses, not validated accuracy results.

### Cross-Bureau overlap

Create a coordination suggestion when two cases resolve to the same institution, are open, and belong to different Bureaus/Cells. Issue-text similarity may help order or describe suggestions, but must not suppress a cross-Bureau alert by itself. Keep the cases separate unless an authorized user records a link decision.

## 5. Demo data and privacy

- Generate synthetic names, institution records, case descriptions, statuses, dates, and action histories.
- Include deliberate noise: missing IDs, common abbreviations, spelling variations, and a small set of labelled true and false matches.
- Keep ground truth separate from the matching input so metrics measure the matcher rather than reveal the answer.
- Do not use real complainant data or secrets in the demo repository.
- If complainant fields are later needed, minimize and mask them by default and make access auditable.

## 6. Initial technical direction

The project folder is currently empty, so there is no existing stack to preserve. Recommended prototype direction:

- **Backend:** Django + Django REST Framework for models, authentication, permissions, and admin.
- **Database:** PostgreSQL for a realistic shared demo; keep development startup simple and document any local fallback.
- **Matching:** deterministic ID lookup and a small, explainable fuzzy matching layer. Add embeddings only if time and measured value justify them.
- **Frontend:** choose Django templates for the fastest end-to-end slice, or React if the team already has a working React setup. Do not build both UI approaches.
- **Jobs:** run matching during import for the small demo dataset. Add a scheduler/worker only when the workflow needs it.

This is a recommendation, not a locked decision; the next implementation step should confirm the team's preferred frontend and local database setup.

## 7. Delivery sequence and exit criteria

### Part 0 — Validate scope

- Obtain the exact problem statement and extract its required fields, users, outputs, and constraints.
- Confirm the demo journey and choose one frontend approach.
- **Exit:** requirement-to-feature checklist and a frozen first-demo scope.

### Part 1 — Foundation

- Create the application skeleton, core data model, migrations, seed data, and a repeatable local startup path.
- **Exit:** a clean local start loads synthetic institutions and cases without manual database editing.

### Part 2 — Import and tracking

- Add CSV validation/import, status mapping, case list/detail, and institution profile.
- **Exit:** an imported case is visible with its source fields and history; re-importing it does not duplicate it.

### Part 3 — Matching and overlap review

- Add deterministic/fuzzy institution resolution, explanation, overlap alerts, and officer decisions.
- **Exit:** the demo journey completes from noisy input through a recorded decision.

### Part 4 — Dashboard and proof

- Add essential KPIs, filters, SLA ageing if required by the exact PS, and measured precision/recall on labelled synthetic data.
- **Exit:** metrics can be reproduced from the demo dataset and the main demo flow remains reliable.

### Part 5 — Presentation hardening

- Improve empty/loading/error states, accessibility, local fallback, documentation, and the short demo script.
- **Exit:** the prototype can be reset and demonstrated end-to-end without relying on live source-system access.

## 8. Decisions still needed

1. The full official problem statement is not present in the supplied pasted text; it has a `PASTED` placeholder. Validate against the official PS before finalizing fields and requirement coverage.
2. Confirm whether the team prefers Django templates or an existing/known React frontend.
3. Confirm whether PostgreSQL is available for local development; otherwise choose a documented prototype fallback.
4. Treat SIH dates, rules, and winner statistics in the research PDFs as research notes until checked against current official sources.

