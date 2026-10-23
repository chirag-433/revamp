# Revamp

SIH prototype for institution complaint monitoring across AICTE Bureaus and Cells.

The first milestone is a synthetic-data demo that resolves institutions, surfaces possible cross-Bureau overlaps, and records a human review decision. It does not connect to production systems or use real complainant data.

## Project status

- Product scope and delivery sequence: [`docs/MVP_SCOPE.md`](docs/MVP_SCOPE.md)
- Current slice: Django project foundation and canonical data model
- Open validation: the exact official problem statement is not yet in the project materials

## Local setup

Requires Python 3.10 or newer.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py makemigrations complaints
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

The app uses SQLite by default for a quick local start. `.env.example` is a reference file; Django does not load it automatically. Set the PostgreSQL variables in your shell before launching to use PostgreSQL. Do not commit credentials or real complaint data.

The Django admin is available at `/admin/`. API endpoints, CSV ingestion, synthetic seed data, and the dashboard are planned for later slices.

## Scope guardrails

- Demo data must be synthetic and include separate ground truth for matching metrics.
- An overlap is a coordination suggestion, never an automatic case merge.
- Exact Permanent ID matches are deterministic; uncertain name matches require review.
- Do not publish measured accuracy claims until they are calculated from the labelled dataset.
