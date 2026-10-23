import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="BureauCell",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=32, unique=True)),
                ("name", models.CharField(max_length=120)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"verbose_name": "Bureau or Cell", "verbose_name_plural": "Bureaus and Cells", "ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Institution",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("aicte_permanent_id", models.CharField(blank=True, db_index=True, max_length=64, null=True, unique=True)),
                ("name", models.CharField(max_length=240)),
                ("normalized_name", models.CharField(blank=True, db_index=True, max_length=240)),
                ("address", models.TextField(blank=True)),
                ("district", models.CharField(blank=True, db_index=True, max_length=120)),
                ("state", models.CharField(blank=True, db_index=True, max_length=120)),
                ("region", models.CharField(blank=True, db_index=True, max_length=120)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="InstitutionAlias",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("alias", models.CharField(max_length=240)),
                ("normalized_alias", models.CharField(db_index=True, max_length=240)),
                ("source", models.CharField(blank=True, max_length=80)),
                ("institution", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="aliases", to="complaints.institution")),
            ],
            options={"ordering": ["normalized_alias"]},
        ),
        migrations.CreateModel(
            name="StatusMap",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_system", models.CharField(max_length=80)),
                ("source_status", models.CharField(max_length=120)),
                ("canonical_status", models.CharField(choices=[("pending", "Pending"), ("under_process", "Under process"), ("disposed", "Disposed"), ("transferred", "Transferred"), ("escalated", "Escalated")], max_length=24)),
            ],
            options={"ordering": ["source_system", "source_status"]},
        ),
        migrations.CreateModel(
            name="ComplaintCase",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_system", models.CharField(max_length=80)),
                ("source_case_id", models.CharField(max_length=120)),
                ("case_number", models.CharField(blank=True, db_index=True, max_length=120)),
                ("raw_institution_name", models.CharField(blank=True, max_length=240)),
                ("match_confidence", models.DecimalField(blank=True, decimal_places=4, max_digits=5, null=True)),
                ("match_status", models.CharField(choices=[("exact_id", "Exact Permanent ID"), ("fuzzy_suggested", "Suggested for review"), ("confirmed", "Confirmed by reviewer"), ("unmatched", "Unmatched")], db_index=True, default="unmatched", max_length=24)),
                ("category", models.CharField(blank=True, db_index=True, max_length=120)),
                ("description", models.TextField(blank=True)),
                ("source_status", models.CharField(blank=True, max_length=120)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("under_process", "Under process"), ("disposed", "Disposed"), ("transferred", "Transferred"), ("escalated", "Escalated")], db_index=True, default="pending", max_length=24)),
                ("assigned_officer", models.CharField(blank=True, max_length=160)),
                ("received_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("last_action_at", models.DateTimeField(blank=True, null=True)),
                ("next_action", models.CharField(blank=True, max_length=240)),
                ("expected_disposal_at", models.DateTimeField(blank=True, null=True)),
                ("sla_due_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("bureau", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cases", to="complaints.bureaucell")),
                ("institution", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="cases", to="complaints.institution")),
            ],
            options={"ordering": ["-received_at", "-id"]},
        ),
        migrations.CreateModel(
            name="CaseAction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action_type", models.CharField(max_length=80)),
                ("actor_label", models.CharField(blank=True, max_length=160)),
                ("acted_at", models.DateTimeField(db_index=True)),
                ("remarks", models.TextField(blank=True)),
                ("document_reference", models.CharField(blank=True, max_length=500)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="complaint_actions", to=settings.AUTH_USER_MODEL)),
                ("case", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="actions", to="complaints.complaintcase")),
                ("from_bureau", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="actions_from", to="complaints.bureaucell")),
                ("to_bureau", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="actions_to", to="complaints.bureaucell")),
            ],
            options={"ordering": ["acted_at", "id"]},
        ),
        migrations.CreateModel(
            name="CaseLink",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("link_type", models.CharField(choices=[("overlap", "Potential overlap"), ("related", "Related"), ("duplicate", "Duplicate"), ("conflict", "Conflicting actions")], max_length=16)),
                ("review_state", models.CharField(choices=[("suggested", "Suggested"), ("confirmed", "Confirmed"), ("rejected", "Rejected")], default="suggested", max_length=16)),
                ("score", models.DecimalField(blank=True, decimal_places=4, max_digits=5, null=True)),
                ("explanation", models.JSONField(blank=True, default=dict)),
                ("decision_note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                ("case_a", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="links_as_a", to="complaints.complaintcase")),
                ("case_b", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="links_as_b", to="complaints.complaintcase")),
                ("decided_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="case_link_decisions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(max_length=80)),
                ("entity_type", models.CharField(max_length=80)),
                ("entity_id", models.CharField(max_length=120)),
                ("occurred_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("details", models.JSONField(blank=True, default=dict)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="complaint_audit_events", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-occurred_at", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="institutionalias",
            constraint=models.UniqueConstraint(fields=("institution", "normalized_alias"), name="unique_institution_normalized_alias"),
        ),
        migrations.AddConstraint(
            model_name="statusmap",
            constraint=models.UniqueConstraint(fields=("source_system", "source_status"), name="unique_source_status_mapping"),
        ),
        migrations.AddConstraint(
            model_name="complaintcase",
            constraint=models.UniqueConstraint(fields=("source_system", "source_case_id"), name="unique_case_per_source_system"),
        ),
        migrations.AddConstraint(
            model_name="caselink",
            constraint=models.UniqueConstraint(fields=("case_a", "case_b", "link_type"), name="unique_case_link_type"),
        ),
        migrations.AddConstraint(
            model_name="caselink",
            constraint=models.CheckConstraint(condition=~models.Q(case_a=models.F("case_b")), name="case_link_must_connect_distinct_cases"),
        ),
        migrations.AddIndex(model_name="institution", index=models.Index(fields=["state", "district"], name="complaints__state_district_idx")),
        migrations.AddIndex(model_name="complaintcase", index=models.Index(fields=["bureau", "status"], name="complaints__bureau__stat_idx")),
        migrations.AddIndex(model_name="complaintcase", index=models.Index(fields=["institution", "status"], name="complaints__institut_stat_idx")),
        migrations.AddIndex(model_name="caselink", index=models.Index(fields=["review_state", "link_type"], name="complaints__review__link_idx")),
    ]

