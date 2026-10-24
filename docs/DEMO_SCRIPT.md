# SIH case monitoring prototype — 4 minute demo

Use only synthetic data in this prototype.

## Prepare (first run)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py seed_match_benchmark
python manage.py createsuperuser
python manage.py runserver
```

Sign in at `/accounts/login/`. In Django admin, give the demo user the `manage_case_workflow` permission to record case updates. Grant `view_complaintcase` to view Reports. For Bureau-scoped access, put an officer in a group named `bureau:<CODE>`; coordinator access uses `overlap-managers`.

## Walkthrough

1. Open the overview and point out open workload, approaching deadlines, escalations, and the synthetic-data label.
2. Open the case register. Filter by Bureau, status, or SLA state; open a case with an institution and inspect its source fields and history.
3. As an authorized officer, record a status, next step, deadline, and short note. Return to the case history to show the actor and timestamp.
4. Open the Overlap Center to compare cross-Bureau cases and show that a human decision is recorded without merging source cases.
5. Open Reports to show the live workload counts and measured precision/recall for the separately labelled benchmark. Explain that the figures describe this synthetic benchmark only.
6. Export the register as CSV if requested.

## Reset and repeat

The reset is explicit and deletes only cases whose source system is `DEMO` or `BENCHMARK`; canonical institution records are retained. Then reseed and refresh SLA alerts:

```powershell
python manage.py reset_demo --confirm
python manage.py seed_demo
python manage.py seed_match_benchmark
python manage.py refresh_sla_alerts
```

The reset also removes links and labels attached to those synthetic cases through their normal cascade behavior. It does not delete imported case records from other source systems.

## Prototype limits

- No live AICTE source integration, production SSO, external email/SMS, or real complainant data.
- The SLA warning window is three days and the dashboard refreshes the in-app queue when opened. A scheduled deployment should run `refresh_sla_alerts` periodically.
- Matching precision/recall is calculated only when the benchmark labels exist; it is not a claim of production accuracy.
- Validate workflow fields and timelines against the official SIH problem statement before deployment.
