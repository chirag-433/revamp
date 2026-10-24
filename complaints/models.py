from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class CanonicalStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    UNDER_PROCESS = "under_process", "Under process"
    DISPOSED = "disposed", "Disposed"
    TRANSFERRED = "transferred", "Transferred"
    ESCALATED = "escalated", "Escalated"


class InstitutionMatchStatus(models.TextChoices):
    EXACT_ID = "exact_id", "Exact Permanent ID"
    FUZZY_SUGGESTED = "fuzzy_suggested", "Suggested for review"
    CONFIRMED = "confirmed", "Confirmed by reviewer"
    UNMATCHED = "unmatched", "Unmatched"


class BureauCell(models.Model):
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Bureau or Cell"
        verbose_name_plural = "Bureaus and Cells"

    def __str__(self):
        return f"{self.code} - {self.name}"


class Institution(models.Model):
    aicte_permanent_id = models.CharField(
        max_length=64, unique=True, null=True, blank=True, db_index=True
    )
    name = models.CharField(max_length=240)
    normalized_name = models.CharField(max_length=240, blank=True, db_index=True)
    address = models.TextField(blank=True)
    district = models.CharField(max_length=120, blank=True, db_index=True)
    state = models.CharField(max_length=120, blank=True, db_index=True)
    region = models.CharField(max_length=120, blank=True, db_index=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(
                fields=["state", "district"], name="complaints__state_district_idx"
            )
        ]

    def __str__(self):
        identifier = self.aicte_permanent_id or "no Permanent ID"
        return f"{self.name} ({identifier})"

    def save(self, *args, **kwargs):
        from .services.normalization import normalize_institution_name

        self.normalized_name = normalize_institution_name(self.name)
        super().save(*args, **kwargs)


class InstitutionAlias(models.Model):
    institution = models.ForeignKey(
        Institution, on_delete=models.CASCADE, related_name="aliases"
    )
    alias = models.CharField(max_length=240)
    normalized_alias = models.CharField(max_length=240, db_index=True)
    source = models.CharField(max_length=80, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["institution", "normalized_alias"],
                name="unique_institution_normalized_alias",
            )
        ]
        ordering = ["normalized_alias"]

    def __str__(self):
        return f"{self.alias} -> {self.institution.name}"

    def save(self, *args, **kwargs):
        from .services.normalization import normalize_institution_name

        self.normalized_alias = normalize_institution_name(self.alias)
        super().save(*args, **kwargs)


class StatusMap(models.Model):
    source_system = models.CharField(max_length=80)
    source_status = models.CharField(max_length=120)
    canonical_status = models.CharField(
        max_length=24, choices=CanonicalStatus.choices
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source_system", "source_status"],
                name="unique_source_status_mapping",
            )
        ]
        ordering = ["source_system", "source_status"]

    def __str__(self):
        return f"{self.source_system}: {self.source_status} -> {self.canonical_status}"


class ComplaintCase(models.Model):
    source_system = models.CharField(max_length=80)
    source_case_id = models.CharField(max_length=120)
    case_number = models.CharField(max_length=120, blank=True, db_index=True)
    institution = models.ForeignKey(
        Institution,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cases",
    )
    raw_institution_name = models.CharField(max_length=240, blank=True)
    match_confidence = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True
    )
    match_status = models.CharField(
        max_length=24,
        choices=InstitutionMatchStatus.choices,
        default=InstitutionMatchStatus.UNMATCHED,
        db_index=True,
    )
    category = models.CharField(max_length=120, blank=True, db_index=True)
    description = models.TextField(blank=True)
    source_status = models.CharField(max_length=120, blank=True)
    status = models.CharField(
        max_length=24,
        choices=CanonicalStatus.choices,
        default=CanonicalStatus.PENDING,
        db_index=True,
    )
    bureau = models.ForeignKey(
        BureauCell, on_delete=models.PROTECT, related_name="cases"
    )
    assigned_officer = models.CharField(max_length=160, blank=True)
    received_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_action_at = models.DateTimeField(null=True, blank=True)
    next_action = models.CharField(max_length=240, blank=True)
    expected_disposal_at = models.DateTimeField(null=True, blank=True)
    sla_due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source_system", "source_case_id"],
                name="unique_case_per_source_system",
            )
        ]
        indexes = [
            models.Index(
                fields=["bureau", "status"], name="complaints__bureau__stat_idx"
            ),
            models.Index(
                fields=["institution", "status"], name="complaints__institut_stat_idx"
            ),
        ]
        permissions = [
            ("manage_case_workflow", "Can record case workflow actions"),
        ]
        ordering = ["-received_at", "-id"]

    @property
    def is_open(self):
        return self.status != CanonicalStatus.DISPOSED

    def __str__(self):
        return self.case_number or f"{self.source_system}:{self.source_case_id}"


class CaseAction(models.Model):
    case = models.ForeignKey(
        ComplaintCase, on_delete=models.CASCADE, related_name="actions"
    )
    action_type = models.CharField(max_length=80)
    from_bureau = models.ForeignKey(
        BureauCell,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="actions_from",
    )
    to_bureau = models.ForeignKey(
        BureauCell,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="actions_to",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="complaint_actions",
    )
    actor_label = models.CharField(max_length=160, blank=True)
    acted_at = models.DateTimeField(db_index=True)
    remarks = models.TextField(blank=True)
    document_reference = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["acted_at", "id"]

    def __str__(self):
        return f"{self.action_type} - {self.case}"


class SlaAlert(models.Model):
    class AlertType(models.TextChoices):
        DUE_SOON = "due_soon", "Due soon"
        OVERDUE = "overdue", "Overdue"

    case = models.ForeignKey(
        ComplaintCase, on_delete=models.CASCADE, related_name="sla_alerts"
    )
    alert_type = models.CharField(max_length=16, choices=AlertType.choices)
    opened_at = models.DateTimeField(default=timezone.now, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["resolved_at", "opened_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["case", "alert_type"],
                condition=Q(resolved_at__isnull=True),
                name="unique_active_sla_alert_per_type",
            )
        ]

    def __str__(self):
        return f"{self.get_alert_type_display()} — {self.case}"


class SyntheticMatchLabel(models.Model):
    """Ground-truth label kept separate from matcher inputs for benchmark runs."""

    case = models.OneToOneField(
        ComplaintCase, on_delete=models.CASCADE, related_name="match_label"
    )
    expected_institution = models.ForeignKey(
        Institution, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="synthetic_match_labels",
    )
    dataset = models.CharField(max_length=80, default="demo-match-v1", db_index=True)

    class Meta:
        ordering = ["dataset", "case_id"]

    def __str__(self):
        return f"{self.dataset}: {self.case}"


class CaseLink(models.Model):
    class LinkType(models.TextChoices):
        OVERLAP = "overlap", "Potential overlap"
        RELATED = "related", "Related"
        DUPLICATE = "duplicate", "Duplicate"
        CONFLICT = "conflict", "Conflicting actions"

    class ReviewState(models.TextChoices):
        SUGGESTED = "suggested", "Suggested"
        CONFIRMED = "confirmed", "Confirmed"
        REJECTED = "rejected", "Rejected"

    case_a = models.ForeignKey(
        ComplaintCase, on_delete=models.CASCADE, related_name="links_as_a"
    )
    case_b = models.ForeignKey(
        ComplaintCase, on_delete=models.CASCADE, related_name="links_as_b"
    )
    link_type = models.CharField(max_length=16, choices=LinkType.choices)
    review_state = models.CharField(
        max_length=16, choices=ReviewState.choices, default=ReviewState.SUGGESTED
    )
    score = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    explanation = models.JSONField(default=dict, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="case_link_decisions",
    )
    decision_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["case_a", "case_b", "link_type"],
                name="unique_case_link_type",
            ),
            models.CheckConstraint(
                condition=~Q(case_a=F("case_b")),
                name="case_link_must_connect_distinct_cases",
            ),
        ]
        indexes = [
            models.Index(
                fields=["review_state", "link_type"], name="complaints__review__link_idx"
            )
        ]
        permissions = [("review_case_links", "Can review and coordinate linked cases")]
        ordering = ["-created_at"]

    def clean(self):
        super().clean()
        if self.case_a_id and self.case_b_id and self.case_a_id == self.case_b_id:
            raise ValidationError("A case cannot be linked to itself.")

    def save(self, *args, **kwargs):
        if self.case_a_id and self.case_b_id and self.case_a_id > self.case_b_id:
            self.case_a_id, self.case_b_id = self.case_b_id, self.case_a_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.case_a} / {self.case_b} ({self.get_link_type_display()})"


class AppendOnlyAuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Audit log entries are append-only.")

    def delete(self):
        raise ValidationError("Audit log entries are append-only.")


class AppendOnlyAuditManager(models.Manager.from_queryset(AppendOnlyAuditQuerySet)):
    pass


class AuditLog(models.Model):
    objects = AppendOnlyAuditManager()

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="complaint_audit_events",
    )
    action = models.CharField(max_length=80)
    entity_type = models.CharField(max_length=80)
    entity_id = models.CharField(max_length=120)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]

    def save(self, *args, **kwargs):
        if self.pk and AuditLog.objects.filter(pk=self.pk).exists():
            raise ValidationError("Audit log entries are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit log entries are append-only.")

    def __str__(self):
        return f"{self.action} {self.entity_type}:{self.entity_id}"



class CoordinationMessage(models.Model):
    """A message in the coordination thread for one linked pair of cases."""

    link = models.ForeignKey(CaseLink, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="coordination_messages"
    )
    mentioned_bureau = models.ForeignKey(
        BureauCell, on_delete=models.PROTECT, related_name="coordination_messages"
    )
    body = models.TextField(max_length=4000)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"Message for {self.link_id} to {self.mentioned_bureau.code}"


class CoordinationNotification(models.Model):
    """An in-app notification sent to an officer group for a bureau."""

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="coordination_notifications"
    )
    message = models.ForeignKey(
        CoordinationMessage, on_delete=models.CASCADE, related_name="notifications"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [models.UniqueConstraint(
            fields=["recipient", "message"], name="unique_coordination_message_notification"
        )]

    def __str__(self):
        return f"Coordination notification for {self.recipient_id}"
