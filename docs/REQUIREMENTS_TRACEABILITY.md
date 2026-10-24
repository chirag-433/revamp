# Requirements and delivery traceability

**Baseline:** SIH institution complaint monitoring prototype

**Review state:** Product scope and phase acceptance checks are recorded. Official problem-statement sign-off is pending because the complete official statement is not in the repository; the supplied planning text contains a `PASTED` placeholder.

This document maps the available planning requirements to the prototype and gives a repeatable acceptance path. Treat the implementation as a synthetic-data demonstration until the official statement is checked for required fields, roles, workflow states, service timelines, and reporting outputs.

## Requirement traceability

| ID | Available requirement | Prototype implementation | Acceptance evidence | State |
|---|---|---|---|---|
| R1 | Show cases across multiple Bureaus/Cells | Bureau/Cell, institution, and case records; dashboard and case register | Seed synthetic data and filter the register by Bureau and status | Implemented |
| R2 | Import source cases while retaining provenance | CSV import stores source system, source case ID, source status, and source fields | Import `static/sample_data/demo_cases.csv`; re-import and confirm the same source key updates the existing row | Implemented |
| R3 | Map source statuses to a shared vocabulary | `StatusMap` maps source statuses to canonical case states | Import rows with configured and unknown source statuses; confirm configured rows save and unknown mappings report errors | Implemented |
| R4 | Resolve institutions using a stable ID where possible | Exact AICTE Permanent ID resolution, normalized-name matching, and explainable fuzzy candidates | Run `run_matching`; inspect exact, suggested, and unmatched cases in Match Review | Implemented |
| R5 | Escalate uncertain institution matches to a person | Match review queue records confirmation/rejection and reviewer audit events | Sign in as a permitted reviewer, decide a suggested match, then inspect case history/audit data | Implemented |
| R6 | Surface possible cross-Bureau overlaps without merging source cases | Overlap suggestions compare open cases for a resolved institution across distinct Bureaus/Cells | Open Overlap Center; inspect the explanation and compare both source cases | Implemented |
| R7 | Let authorized officers coordinate and record decisions | Permission-gated confirm/reject/related decisions, notes, messages, notifications, and audit events | Use an account with the documented group permissions; post a coordination message and record a decision | Implemented |
| R8 | Track case progress and the next action | Permission-gated status, next action, deadline, and note updates with timestamped case actions | Update a case and confirm actor, time, and action appear in its history | Implemented |
| R9 | Highlight cases approaching or past an expected deadline | Due-soon and overdue alerts, dashboard totals, and refresh command | Set synthetic deadlines and run `refresh_sla_alerts`; inspect the dashboard alert queue | Implemented; three-day warning window is a prototype assumption |
| R10 | Report workload and demonstrate matching quality against known labels | Workload report, register CSV export, and precision/recall from separate synthetic labels | Run `seed_match_benchmark`, then inspect Reports; confirm the benchmark is labelled synthetic | Implemented; benchmark is not production accuracy |
| R11 | Make the demonstration repeatable and safe for synthetic data | Seed/reset commands, setup instructions, responsive controls, focus states, reduced motion, and walkthrough | Follow `docs/DEMO_SCRIPT.md`; reset only `DEMO` and `BENCHMARK` source records, then reseed | Implemented |
| R12 | Match the exact SIH problem statement | Cannot verify without the complete official problem statement | Compare its required fields, user roles, workflow states, SLA rules, outputs, and constraints with this matrix | Pending official source |

## Data and workflow assumptions to validate

| Assumption in the prototype | Current behavior | Validate against official statement |
|---|---|---|
| Case identity is source-scoped | `(source_system, source_case_id)` is unique | Confirm source identifiers and duplicate/update rules |
| Canonical states are Pending, Under process, Disposed, Transferred, and Escalated | Source states map through `StatusMap` | Confirm the official status list and permitted transitions |
| An unresolved Permanent ID can use name and location signals | Fuzzy institution candidates require review below the automatic threshold | Confirm approved institution identifiers and human-review policy |
| An overlap is a coordination suggestion | Source cases remain separate; a user records a link decision | Confirm overlap definition, decision types, and who may decide |
| A deadline within three days is due soon | SLA alerts use a configurable service constant currently set to three days | Confirm actual deadlines, calendars, pause rules, and escalation policy |
| Reports use synthetic benchmark labels | Precision and recall are calculated only for the labelled benchmark | Confirm required operational reports and data-governance rules |
| Prototype data is synthetic and integrations are out of scope | No production AICTE write-back or complainant data is used | Confirm integration, security, privacy, and deployment obligations |

## Phase completion register

| Phase | Exit check | Evidence in this repository | Completion |
|---|---|---|---|
| 0 — Scope baseline | Scope, requirements-to-feature mapping, assumptions, and open validation recorded | `docs/MVP_SCOPE.md` and this matrix | Baseline complete; official problem-statement sign-off pending |
| 1 — Foundation | Clean setup, schema, and repeatable synthetic seed path | Django project, migrations, `seed_demo`, README setup | Implemented |
| 2 — Import and tracking | Validated duplicate-safe CSV import, status mapping, case/institution views, and history | Import service, case and institution views, sample CSV, models | Implemented |
| 3 — Matching and overlap review | Explainable institution resolution, human review, cross-Bureau suggestions, recorded decision | Matching/overlap services, review queues and coordination screens | Implemented |
| 4 — Dashboard and proof | Workflow audit, SLA alerts, coordination, workload/CSV reports, labelled benchmark metrics | Case workflow, `SlaAlert`, overlap center, reports, benchmark seed command | Implemented |
| 5 — Presentation hardening | Safe reset, repeatable demo, responsive/accessibility behavior and documented walkthrough | `reset_demo`, templates/CSS, README, `docs/DEMO_SCRIPT.md` | Implemented |

## Acceptance run

From the project root, use the commands in `README.md` to install dependencies, migrate, seed demo and benchmark data, create an authorized account, and start the server. Then follow `docs/DEMO_SCRIPT.md`.

The core acceptance path is: import a synthetic case; verify duplicate-safe update and source fields; run institution matching; review an uncertain candidate; inspect a cross-Bureau suggestion; record a permission-gated workflow update and coordination decision; inspect the resulting history, alert, and report; export the register; reset synthetic records and repeat.

## Sign-off needed

Phase 0 is complete as a documented baseline, but the project must not claim official requirement sign-off until the full AICTE/SIH problem statement is added and R12 plus the assumption table are checked against it. Update the scope and matrix with any required changes before treating the prototype as submission-ready.
