# Mentor and judge Q&A notes

## What problem does this solve?

It gives authorized officers a shared register and institution view, so they can spot possible cross-Bureau overlaps or conflicting actions and coordinate a human decision.

## Does it connect to AICTE systems?

No. RB and PGRC adapters currently read synthetic JSON and CSV fixtures through the common import contract. Live access requires approval and source-owner field mapping.

## How accurate is the matching?

The current report evaluates a small generated benchmark: 24 institution labels and 450 case-pair labels. At threshold 0.90, institution matching measured 100% precision and recall at 50% coverage. These results are not a production accuracy claim.

## Does the application merge cases automatically?

No. It creates suggestions for review. An officer records the decision, and the source cases remain separate.

## What happens when one Bureau transfers a case?

The receiving Bureau accepts or rejects a pending request. Acceptance moves ownership; rejection restores the prior status and owner. Both decisions enter the case action history and audit log.

## How does the prototype run?

The local option uses Django and SQLite. Docker Compose starts Django, PostgreSQL, Redis, a Celery worker and a scheduled Celery Beat service.

## What needs approval before a pilot?

The exact SIH problem statement and template, role and Bureau map, official statuses and SLA rules, source-owner access, privacy and retention rules, hosting/security review, and named team roles.
