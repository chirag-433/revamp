# SIH phase delivery register

This register follows the supplied nine-phase implementation plan. It separates repository deliverables from activities that need the official SIH materials, a mentor, a team, or an external hosting account. Planning targets and placeholders in the source plan are treated as assumptions until confirmed.

## Phase 0 — Alignment and readiness

- **Repository-ready:** scope baseline, requirement matrix, assumption list, and a repeatable demo path are documented in `MVP_SCOPE.md`, `REQUIREMENTS_TRACEABILITY.md`, and `DEMO_SCRIPT.md`.
- **Roles:** role descriptions and responsibilities are in `TEAM_READINESS.md`; names and backups remain for the team to assign.
- **Pending external validation:** official 2026 SIH rules/template/timeline, mentor answers for Bureau names and field/status/SLA rules, mentor scope sign-off, and tool/account checklist completion.
- **Gate:** do not label scope officially signed off until the statement and mentor answers are checked into the project.

## Phase 1 — Foundations, schema, and synthetic data

- Django project, schema migrations, SQLite local setup, and optional PostgreSQL configuration are implemented.
- `seed_demo` creates synthetic institutions, cases, actions, and planted cross-Bureau links; the default dataset target is about 800 institutions and 4,000 cases.
- Ground-truth labels are stored separately from matcher inputs.
- Docker Compose provisions PostgreSQL, Redis, Django, Celery worker and scheduler; GitHub Actions checks Django, migrations and tests.

## Phase 2 — Matching engine

- Permanent ID, normalized-name, alias, and explainable fuzzy candidate matching are available; uncertain matches go to human review.
- Similarity uses a local explainable fuzzy matcher and alias data; no embedding model download is required for the demo.
- Evaluation commands report threshold-specific matching results and labelled overlap/conflict results. Planning thresholds remain targets, not claims.
- The current sample sizes and measured results are recorded in `BENCHMARK_RESULTS.md` and the generated CSV/threshold chart under `artifacts/evaluation/`.
- **Gate:** record measured results and known gaps from the generated dataset before presenting target attainment.

## Phase 3 — Core application

- Django authentication, permission checks, case and institution pages, dashboard, source-preserving CSV import, case history, and filters are available.
- Role and region scope is applied server-side where configured.
- **Pending:** official role matrix and every official problem-statement field must be confirmed; a demo role switcher is not an authentication substitute.

## Phase 4 — Overlap Center, workflow, alerts, and reports

- The Overlap Center supports comparison, decisions, links, messages, and notifications. Case actions are recorded in an append-only timeline.
- SLA alerts, rule-based action-conflict suggestions, workload views, benchmark metrics, and CSV, Excel and PDF exports are included.
- The transfer acceptance flow records the request, restricts the response to the receiving Bureau, changes ownership only on acceptance, and raises an alert for aged pending transfers.
- **Pending or simplified:** external email delivery, live WebSocket updates, approved service-calendar values, and official report content need operational decisions.

## Phase 5 — Integration, hardening, and deployment

- CSV validation and repeat-safe import preserve source identifiers; mock RB and PGRC adapters are provided as local fixtures.
- CSRF, permission checks, input validation, environment secrets, and a production settings profile are included.
- **Pending external setup:** public HTTPS deployment, production database, backup credentials, live source access, and external review/usability sessions. No deployment or rehearsal result is claimed until observed.

## Phase 6 — Deck, demo, and rehearsal

- An editable eight-slide deck, architecture/matching visuals, Q&A sheet, four-minute demo, and one-minute cut are provided as project artifacts.
- **Pending:** official SIH template, named speakers and driver, three timed rehearsals, mentor review, final screenshots, and submission exports. Replace assumptions with measured results before submission.

## Phase 7 — 36-hour finale

- A time-boxed execution checklist, cut order, offline fallback, and presentation-day checklist are documented in `FINALE_RUNBOOK.md`.
- **Not executable in advance:** event-day attendance, judging, build-from-scratch restrictions, finale feedback, and live demonstration outcomes.

## Phase 8 — Post-finale roadmap

- Discovery, pilot, expansion, hardening, and learning stages with decision gates are documented in `PRODUCTION_ROADMAP.md` and the deck.
- **Pending:** data-owner agreements, pilot users, hosting/security approvals, and outcome measurements.

## Current acceptance order

1. Apply migrations and seed the default synthetic dataset.
2. Run the matching and conflict evaluation commands; save the generated report with its dataset version.
3. Exercise import, institution review, overlap review, case action, alerts, and CSV export using role-scoped accounts.
4. Follow the demo script locally; record each rehearsal result rather than marking the future event checklist complete.
5. Verify official problem-statement requirements and SIH restrictions before submission or deployment.
