# Revamp

SIH prototype for institution complaint monitoring across AICTE Bureaus and Cells.

The first milestone is a synthetic-data demo that resolves institutions, surfaces possible cross-Bureau overlaps, and records a human review decision. It does not connect to production systems or use real complainant data.

## Project status

- Product scope and delivery sequence: [`docs/MVP_SCOPE.md`](docs/MVP_SCOPE.md)
- Current slice: foundation and Phase 2 case import/tracking
- Open validation: the exact official problem statement is not yet in the project materials

## Local setup

Requires Python 3.10 or newer.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py makemigrations complaints
python manage.py migrate
python manage.py seed_demo
python manage.py createsuperuser
python manage.py runserver
```

The app uses SQLite by default for a quick local start. `.env.example` is a reference file; Django does not load it automatically. Set the PostgreSQL variables in your shell before launching to use PostgreSQL. Do not commit credentials or real complaint data.

The floating Casework Guide help desk uses Gemini through a server-side request. Set `GEMINI_API_KEY` in the shell before launching; the key is intentionally never exposed to the browser. Do not paste API keys into source files or commit them. If a key has been shared publicly, revoke it and create a replacement.

The case register is available at `/`, CSV import at `/import/`, and the Django admin at `/admin/`. Case and institution detail pages are linked from the register. `/health/` provides a small process health response.

The `seed_demo` command creates or refreshes a small set of clearly synthetic institutions, Bureaus/Cells, status mappings, cases, and initial history. It is safe to run more than once; it does not delete existing data. The sample import file is [`static/sample_data/demo_cases.csv`](static/sample_data/demo_cases.csv).

## CSV import contract

Required columns: `source_system`, `source_case_id`, `bureau_code`, `institution_name`, and `source_status`.

Optional columns: `case_number`, `institution_permanent_id`, `category`, `description`, `assigned_officer`, `received_at`, `last_action_at`, `next_action`, `expected_disposal_at`, `sla_due_at`, and `action_remarks`.

Dates must be ISO 8601. A source status must have a matching `StatusMap` entry and the Bureau/Cell code must exist and be active. Rows with validation errors are skipped and reported; valid rows are saved. Re-imports update the same `(source_system, source_case_id)` record, and the database enforces that key as unique. A provided Permanent ID links only when it exactly matches an active institution record; unknown or missing IDs remain unresolved for the later matching phase.

This first import screen is intended for a local synthetic-data prototype. It is not yet protected by production authentication or authorization and must not be exposed publicly.

## Delivery status

- **Phase 0 — requirements:** draft scope is recorded in [`docs/MVP_SCOPE.md`](docs/MVP_SCOPE.md); the complete official problem statement is still needed to validate exact field names and workflow requirements.
- **Phase 1 — foundation:** Django app, initial schema migration, local SQLite/PostgreSQL configuration, repeatable synthetic seed command, and local startup steps are in place.
- **Phase 2 — import and tracking:** CSV validation/import, canonical status mapping, duplicate-safe updates, case list/detail, and institution profiles are in place.
- **Next:** Phase 3 matching suggestions and cross-Bureau overlap review. No fuzzy matching, alerts, or officer case-link decisions are implemented yet.

## Scope guardrails

- Demo data must be synthetic. Labelled ground truth and matching metrics are planned for Phase 4.
- An overlap is a coordination suggestion, never an automatic case merge.
- Exact Permanent ID matches are deterministic; uncertain name matches require review.
- Do not publish measured accuracy claims until they are calculated from the labelled dataset.
