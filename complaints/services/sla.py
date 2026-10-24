from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from complaints.models import (
    AuditLog,
    CanonicalStatus,
    CaseTransfer,
    ComplaintCase,
    SlaAlert,
)


WARNING_WINDOW_DAYS = 3
STALE_CASE_DAYS = 15
TRANSFER_ACCEPTANCE_DAYS = 3


def refresh_sla_alerts(case_ids=None, *, now=None):
    """Reconcile active in-app SLA alerts against the current case deadlines."""
    now = now or timezone.now()
    threshold = now + timedelta(days=WARNING_WINDOW_DAYS)
    cases = ComplaintCase.objects.exclude(status=CanonicalStatus.DISPOSED)
    if case_ids is not None:
        cases = cases.filter(pk__in=case_ids)

    counts = {value: 0 for value, _ in SlaAlert.AlertType.choices}
    with transaction.atomic():
        case_rows = list(cases.only("pk", "sla_due_at", "status", "last_action_at", "received_at"))
        case_pks = [case.pk for case in case_rows]
        pending_transfer_case_ids = set(CaseTransfer.objects.filter(
            case_id__in=case_pks,
            state=CaseTransfer.State.PENDING,
            requested_at__lte=now - timedelta(days=TRANSFER_ACCEPTANCE_DAYS),
        ).values_list("case_id", flat=True))
        active_alerts = list(SlaAlert.objects.select_for_update().filter(
            case_id__in=case_pks, resolved_at__isnull=True
        ))
        alerts_by_case = {}
        for alert in active_alerts:
            alerts_by_case.setdefault(alert.case_id, []).append(alert)

        resolved_alerts = []
        opened_alerts = []
        for case in case_rows:
            desired = set()
            if case.sla_due_at and case.sla_due_at < now:
                desired.add(SlaAlert.AlertType.OVERDUE)
            elif case.sla_due_at and case.sla_due_at <= threshold:
                desired.add(SlaAlert.AlertType.DUE_SOON)
            last_activity = case.last_action_at or case.received_at
            if last_activity and last_activity <= now - timedelta(days=STALE_CASE_DAYS):
                desired.add(SlaAlert.AlertType.STALE)
            if case.status == CanonicalStatus.ESCALATED:
                desired.add(SlaAlert.AlertType.ESCALATED)
            if case.pk in pending_transfer_case_ids:
                desired.add(SlaAlert.AlertType.TRANSFER_AWAITING)

            active = alerts_by_case.get(case.pk, [])
            for alert in active:
                if alert.alert_type not in desired:
                    alert.resolved_at = now
                    resolved_alerts.append(alert)
                    AuditLog.objects.create(
                        action="sla_alert_resolved", entity_type="SlaAlert",
                        entity_id=str(alert.pk),
                        details={"case_id": case.pk, "alert_type": alert.alert_type},
                    )
                else:
                    counts[alert.alert_type] += 1

            active_types = {alert.alert_type for alert in active}
            for alert_type in desired - active_types:
                opened_alerts.append(SlaAlert(case=case, alert_type=alert_type))

        if resolved_alerts:
            SlaAlert.objects.bulk_update(resolved_alerts, ["resolved_at"], batch_size=500)
        if opened_alerts:
            SlaAlert.objects.bulk_create(opened_alerts, batch_size=500)
            for alert in opened_alerts:
                counts[alert.alert_type] += 1
                AuditLog.objects.create(
                    action="sla_alert_opened", entity_type="SlaAlert",
                    entity_id=str(alert.pk),
                    details={"case_id": alert.case_id, "alert_type": alert.alert_type,
                             "sla_due_at": alert.case.sla_due_at.isoformat() if alert.case.sla_due_at else None},
                )

        # Disposed cases are resolved too, including when a single case was requested.
        disposed = ComplaintCase.objects.filter(status=CanonicalStatus.DISPOSED)
        if case_ids is not None:
            disposed = disposed.filter(pk__in=case_ids)
        disposed_alerts = list(SlaAlert.objects.select_for_update().filter(
            case__in=disposed, resolved_at__isnull=True
        ))
        if disposed_alerts:
            for alert in disposed_alerts:
                alert.resolved_at = now
            SlaAlert.objects.bulk_update(disposed_alerts, ["resolved_at"], batch_size=500)
        for alert in disposed_alerts:
            AuditLog.objects.create(
                action="sla_alert_resolved", entity_type="SlaAlert",
                entity_id=str(alert.pk),
                details={"case_id": alert.case_id, "alert_type": alert.alert_type,
                         "reason": "case_disposed"},
            )
    return counts
