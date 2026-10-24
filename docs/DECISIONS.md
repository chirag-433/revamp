# Project decisions and open questions

## Recorded decisions

| Date | Decision | Reason | Owner |
|---|---|---|---|
| 2026-10-24 | Use Django templates for the prototype UI, with SQLite for local setup and PostgreSQL as an optional database. | Keeps the demonstration setup simple while preserving a shared-database path. | Project team — confirm |
| 2026-10-24 | Use synthetic case and institution data only; do not write back to production systems. | The repository has no official integration approval or data-sharing agreement. | Project team — confirm |
| 2026-10-24 | Keep overlap suggestions separate from source cases and require an authorized human decision. | Avoids merging records based only on a similarity score. | Project team — confirm |
| 2026-10-24 | Treat thresholds, Bureau names, SLA durations, event dates, and target metrics in planning documents as assumptions. | The plan explicitly says these values require validation. | Product lead — confirm |

## Open questions for mentor or official source

1. Which exact problem-statement fields, statuses, roles, and outputs are mandatory?
2. Which Bureaus/Cells and regions should the demonstration include?
3. What SLA durations, calendars, pauses, and escalation recipients are authoritative?
4. What is the approved source of institution IDs and institution master data?
5. What is the official 2026 submission template and the restriction on prepared code at the finale?
6. Are AICTE source integration, personal data, cloud hosting, email, or external notifications in scope?

## Decision log entry template

| Date | Question | Decision | Evidence/source | Owner |
|---|---|---|---|---|
| YYYY-MM-DD | Fill in | Fill in | Link or meeting note | Name |
