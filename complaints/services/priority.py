"""Small, explainable urgency score for the casework queues.

The score deliberately uses only operational signals already stored on a case.
It is a prioritisation aid for officers, not an automated decision.
"""

from datetime import timedelta

from django.utils import timezone

from complaints.models import CanonicalStatus, InstitutionMatchStatus


def case_priority(case, now=None):
    """Return a bounded score, label, and human-readable reasons for a case."""
    now = now or timezone.now()
    if case.status == CanonicalStatus.DISPOSED:
        return 0, "Resolved", []

    score, reasons = 0, []
    if case.status == CanonicalStatus.ESCALATED:
        score += 45
        reasons.append("Escalated")
    if case.sla_due_at and case.sla_due_at < now:
        score += 35
        reasons.append("SLA overdue")
    elif case.sla_due_at and case.sla_due_at <= now + timedelta(days=3):
        score += 20
        reasons.append("SLA due soon")
    if not case.institution_id:
        score += 15
        reasons.append("Institution unresolved")
    elif case.match_status == InstitutionMatchStatus.FUZZY_SUGGESTED:
        score += 10
        reasons.append("Match needs review")
    if case.last_action_at and case.last_action_at < now - timedelta(days=14):
        score += 10
        reasons.append("No recent action")

    score = min(score, 100)
    label = "Critical" if score >= 60 else "High" if score >= 35 else "Watch" if score else "On track"
    return score, label, reasons
