# Revamp

SIH prototype for institution complaint monitoring across AICTE Bureaus and Cells.

The first milestone is a synthetic-data demo that resolves institutions, surfaces possible cross-Bureau overlaps, and records a human review decision. It does not connect to production systems or use real complainant data.

## Project status

- Product scope and delivery sequence: [`docs/MVP_SCOPE.md`](docs/MVP_SCOPE.md); requirement mapping and acceptance path: [`docs/REQUIREMENTS_TRACEABILITY.md`](docs/REQUIREMENTS_TRACEABILITY.md)
- Complete phase register: [`docs/PHASEWISE_DELIVERY.md`](docs/PHASEWISE_DELIVERY.md); architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Implemented slices: synthetic data, identity matching and review, case register and API, overlap/conflict coordination, transfer workflow, SLA alerts, PDF/Excel/CSV reports, mock source adapters, and container/CI setup
- Phase 4A–4D officer actions and reports require Django login and the relevant permissions
- External gates still open: official SIH problem statement/template, mentor workflow sign-off, live source access, production hosting, named team assignments and actual rehearsals

## Local setup

Requires Python 3.10 or newer.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py makemigrations complaints
python manage.py migrate
python manage.py seed_demo
python manage.py seed_match_benchmark
python manage.py createsuperuser
python manage.py runserver
```

The app uses SQLite by default for a quick local start. Set the PostgreSQL variables in your shell before launching to use PostgreSQL. For the floating Disha assistant, copy `.env.example` to `.env` and set `SARVAM_API_KEY`; Django loads `.env` at startup and sends Sarvam chat requests server-side, so the key is never exposed to the browser. Do not commit credentials or real complaint data. If a key has been shared publicly, revoke it and create a replacement.

The dashboard is available at `/`, CSV import at `/import/`, Match Review at `/matches/`, the Overlap Center at `/overlap/`, reports at `/reports/`, sign-in at `/accounts/login/`, and Django admin at `/admin/`. Case and institution detail pages are linked from the register. `/health/` provides a small process health response. Workflow updates, coordination decisions/messages, match reviews, and reports require an authenticated account and the relevant permissions. State-changing forms use CSRF-protected POST requests.

### Phase 4A local access

1. Apply the schema migration with `python manage.py migrate` (this applies the new tables without deleting existing records).
2. Create a local administrator with `python manage.py createsuperuser`, then sign in at `/admin/`.
3. Create Django Groups named `bureau:RB`, `bureau:PGRC`, etc. and add each officer to their Bureau/Cell group. Grant these groups the `view_caselink`, `review_case_links`, `add_caselink`, and `add_coordinationmessage` permissions. The `overlap-managers` group can be used for coordinators who need cross-Bureau access; grant the same permissions. Accounts and group permissions are managed in Django admin.
4. Open `/overlap/` to compare suggestions, record decisions, post messages, and review borderline institution matches. In-app message notifications are delivered to active users in the mentioned Bureau/Cell group and to overlap managers.

The existing case register, dashboard, institution pages, and CSV import remain part of the prototype. The pre-existing CSV import is still intended only for a local synthetic-data demo and is not production-hardened.

The `seed_demo` command creates or refreshes a synthetic dataset of about 800 institutions and 4,000 cases, with planted overlap/conflict examples and separate benchmark labels. `seed_match_benchmark` adds a small isolated matching sample. `evaluate_benchmarks` writes threshold and link results to `artifacts/evaluation/`. `ingest_mock_source rb` and `ingest_mock_source pgrc` exercise repeat-safe source adapters. `refresh_sla_alerts` reconciles due-soon, overdue, stale, escalated and pending-transfer alerts; Celery Beat schedules this every 15 minutes in Docker Compose. The sample import file is [`static/sample_data/demo_cases.csv`](static/sample_data/demo_cases.csv).

### Container setup

Copy `.env.example` to `.env`, replace the Django secret and database password, and set `DJANGO_DEBUG=0` before using a non-local deployment. Docker Desktop is required.

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_demo
docker compose exec web python manage.py seed_match_benchmark
```

The web app is then available at `http://localhost:8000`. PostgreSQL data persists in a named volume. Docker defaults are for local development and must be replaced for deployment.

## CSV import contract

Required columns: `source_system`, `source_case_id`, `bureau_code`, `institution_name`, and `source_status`.

Optional columns: `case_number`, `institution_permanent_id`, `category`, `description`, `assigned_officer`, `received_at`, `last_action_at`, `next_action`, `expected_disposal_at`, `sla_due_at`, and `action_remarks`.

Dates must be ISO 8601. A source status must have a matching `StatusMap` entry and the Bureau/Cell code must exist and be active. Rows with validation errors are skipped and reported; valid rows are saved. Re-imports update the same `(source_system, source_case_id)` record, and the database enforces that key as unique. A provided Permanent ID links only when it exactly matches an active institution record; unknown or missing IDs remain unresolved for the later matching phase.

CSV imports require an authenticated account with the Django `add_complaintcase` permission. The importer remains intended for a local synthetic-data prototype and is not a production source integration.

## Delivery status

- **Phase 0 — requirements:** prototype scope, traceability matrix, assumptions, and acceptance path are recorded in [`docs/MVP_SCOPE.md`](docs/MVP_SCOPE.md) and [`docs/REQUIREMENTS_TRACEABILITY.md`](docs/REQUIREMENTS_TRACEABILITY.md). The complete official problem statement is still needed for final requirement sign-off.
- **Phase 1 — foundation:** Django app, schema migrations, SQLite/PostgreSQL configuration, repeatable synthetic seed command, Docker Compose with PostgreSQL/Redis/Celery, and CI checks are in place.
- **Phase 2 — import and tracking:** CSV validation/import, canonical status mapping, duplicate-safe updates, case list/detail, and institution profiles are in place. The matcher reports threshold sweeps against synthetic ground truth.
- **Phase 3 — matching and review:** 3-tier fuzzy institution resolution, a manual match review queue, cross-Bureau overlap detection, and the Phase 3 overlap list remain available.
- **Phase 4A — Coordination:** cross-Bureau suggestions, comparison, audited decisions, manual related links, coordination threads and in-app notifications, and borderline institution-match review.
- **Phase 4B — Workflow:** permission-gated case status, next-action, deadline, and note updates appear in the timestamped action history and append-only audit log.
- **Phase 4C — SLA alerts:** due-soon, overdue, stale, escalated and pending-transfer alerts refresh in-app and on a 15-minute Celery schedule.
- **Phase 4D — Reports:** workload counts, register CSV/Excel/PDF exports, and precision/recall measured against separately stored synthetic match and link labels.
- **Phase 5 — Demo hardening:** role-scoped web/API access, login throttling, environment secrets, CSRF, production static files, repeat-safe source adapters, Docker setup, CI, reset command, setup notes and walkthrough.
- **Phase 6 — Demo materials:** an editable eight-slide draft deck, four-minute and one-minute demo scripts, benchmark note, and mentor Q&A sheet are in `output/presentations/` and `docs/`. Replace the layout with the official SIH template when received.
- **Phases 7–8 — Future readiness:** finale runbook and post-finale roadmap are in `docs/FINALE_RUNBOOK.md` and `docs/PRODUCTION_ROADMAP.md`; event/pilot outcomes remain future work.
- Benchmark results are synthetic and small. They are reported with their sample sizes and are not evidence of operational accuracy.

## Scope guardrails

- Demo data must be synthetic. Matching metrics are limited to the labelled synthetic benchmark and must not be presented as production accuracy.
- An overlap is a coordination suggestion, never an automatic case merge.
- Exact Permanent ID matches are deterministic; uncertain name matches require review.
- Do not publish measured accuracy claims until they are calculated from the labelled dataset.

