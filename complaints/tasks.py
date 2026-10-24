from celery import shared_task

from complaints.services.sla import refresh_sla_alerts


@shared_task
def refresh_case_sla_alerts():
    """Refresh due, overdue, stale, escalated, and transfer alerts on schedule."""
    counts = refresh_sla_alerts()
    return {key: value for key, value in counts.items()}
