from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from complaints.models import (
    AuditLog,
    CanonicalStatus,
    ComplaintCase,
    SlaAlert,
)


WARNING_WINDOW_DAYS = 3


def refresh_sla_alerts(case_ids=None, *, now=None):
    """Reconcile active in-app SLA alerts against the current case deadlines."""
    now = now or timezone.now()
    threshold = now + timedelta(days=WARNING_WINDOW_DAYS)
    cases = ComplaintCase.objects.exclude(status=CanonicalStatus.DISPOSED)
    if case_ids is not None:
        cases = cases.filter(pk__in=case_ids)

    counts = {SlaAlert.AlertType.DUE_SOON: 0, SlaAlert.AlertType.OVERDUE: 0}
    with transaction.atomic():
        for case in cases.only("pk", "sla_due_at", "status"):
            desired = None
            if case.sla_due_at and case.sla_due_at < now:
                desired = SlaAlert.AlertType.OVERDUE
            elif case.sla_due_at and case.sla_due_at <= threshold:
                desired = SlaAlert.AlertType.DUE_SOON

            active = list(SlaAlert.objects.select_for_update().filter(
                case=case, resolved_at__isnull=True
            ))
            for alert in active:
                if alert.alert_type != desired:
                    alert.resolved_at = now
                    alert.save(update_fields=["resolved_at"])
                    AuditLog.objects.create(
                        action="sla_alert_resolved", entity_type="SlaAlert",
                        entity_id=str(alert.pk),
                        details={"case_id": case.pk, "alert_type": alert.alert_type},
                    )
                else:
                    counts[alert.alert_type] += 1

            if desired and not any(alert.alert_type == desired for alert in active):
                alert = SlaAlert.objects.create(case=case, alert_type=desired)
                counts[desired] += 1
                AuditLog.objects.create(
                    action="sla_alert_opened", entity_type="SlaAlert",
                    entity_id=str(alert.pk),
                    details={"case_id": case.pk, "alert_type": desired,
                             "sla_due_at": case.sla_due_at.isoformat()},
                )

        # Disposed cases are resolved too, including when a single case was requested.
        disposed = ComplaintCase.objects.filter(status=CanonicalStatus.DISPOSED)
        if case_ids is not None:
            disposed = disposed.filter(pk__in=case_ids)
        for alert in SlaAlert.objects.select_for_update().filter(
            case__in=disposed, resolved_at__isnull=True
        ):
            alert.resolved_at = now
            alert.save(update_fields=["resolved_at"])
            AuditLog.objects.create(
                action="sla_alert_resolved", entity_type="SlaAlert",
                entity_id=str(alert.pk),
                details={"case_id": alert.case_id, "alert_type": alert.alert_type,
                         "reason": "case_disposed"},
            )
    return counts
