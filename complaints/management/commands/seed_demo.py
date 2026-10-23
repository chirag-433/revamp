from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from complaints.models import (
    BureauCell,
    CanonicalStatus,
    CaseAction,
    ComplaintCase,
    Institution,
    InstitutionAlias,
    InstitutionMatchStatus,
    StatusMap,
)


class Command(BaseCommand):
    help = "Create or refresh a small, entirely synthetic demo dataset."

    def handle(self, *args, **options):
        bureaus = {
            "RB": "Regional Bureau",
            "PGRC": "Public Grievance Redressal Cell",
            "ACADEMIC": "Academic Coordination Cell",
        }
        bureau_objects = {
            code: BureauCell.objects.update_or_create(
                code=code, defaults={"name": name, "is_active": True}
            )[0]
            for code, name in bureaus.items()
        }
        institutions = [
            {
                "aicte_permanent_id": "DEMO-0001",
                "name": "Sahyadri Institute of Technology",
                "district": "Pune",
                "state": "Maharashtra",
                "region": "West",
            },
            {
                "aicte_permanent_id": "DEMO-0002",
                "name": "Eastern Valley College of Engineering",
                "district": "Guwahati",
                "state": "Assam",
                "region": "North East",
            },
            {
                "aicte_permanent_id": "DEMO-0003",
                "name": "Coastal School of Applied Sciences",
                "district": "Kochi",
                "state": "Kerala",
                "region": "South",
            },
        ]
        institution_objects = {}
        for values in institutions:
            institution, _ = Institution.objects.update_or_create(
                aicte_permanent_id=values["aicte_permanent_id"], defaults=values
            )
            institution_objects[values["aicte_permanent_id"]] = institution
        InstitutionAlias.objects.get_or_create(
            institution=institution_objects["DEMO-0001"],
            normalized_alias="sahyadri tech institute",
            defaults={"alias": "Sahyadri Tech Institute", "source": "synthetic demo"},
        )

        status_mapping = {
            "received": CanonicalStatus.PENDING,
            "pending": CanonicalStatus.PENDING,
            "in progress": CanonicalStatus.UNDER_PROCESS,
            "under process": CanonicalStatus.UNDER_PROCESS,
            "disposed": CanonicalStatus.DISPOSED,
            "closed": CanonicalStatus.DISPOSED,
            "transferred": CanonicalStatus.TRANSFERRED,
            "escalated": CanonicalStatus.ESCALATED,
        }
        for source_system in ("RB", "PGRC", "ACADEMIC", "DEMO"):
            for source_status, canonical_status in status_mapping.items():
                StatusMap.objects.update_or_create(
                    source_system=source_system,
                    source_status=source_status,
                    defaults={"canonical_status": canonical_status},
                )

        now = timezone.now()
        cases = [
            ("DEMO", "DEMO-RB-1001", "RB-1001", "DEMO-0001", "received", "Facilities", "Synthetic request for a laboratory safety inspection.", 12),
            ("DEMO", "DEMO-PGRC-2042", "PGRC-2042", "DEMO-0001", "in progress", "Facilities", "Synthetic complaint about delayed repair of a campus laboratory.", 7),
            ("DEMO", "DEMO-RB-1002", "RB-1002", "DEMO-0002", "pending", "Academic records", "Synthetic request to correct an examination record.", 4),
            ("DEMO", "DEMO-ACA-3007", "ACA-3007", "DEMO-0003", "disposed", "Student services", "Synthetic request for an update to a student service process.", 26),
            ("DEMO", "DEMO-PGRC-2043", "PGRC-2043", "UNKNOWN-001", "escalated", "Fee refund", "Synthetic inquiry about the status of a fee refund.", 2),
        ]
        for system, source_id, case_number, permanent_id, raw_status, category, description, age_days in cases:
            institution = institution_objects.get(permanent_id)
            bureau_code = "RB" if "RB-" in case_number else "PGRC" if "PGRC-" in case_number else "ACADEMIC"
            received_at = now - timedelta(days=age_days)
            case, _ = ComplaintCase.objects.update_or_create(
                source_system=system,
                source_case_id=source_id,
                defaults={
                    "case_number": case_number,
                    "institution": institution,
                    "raw_institution_name": institution.name if institution else "Unmatched Synthetic College",
                    "match_status": InstitutionMatchStatus.EXACT_ID if institution else InstitutionMatchStatus.UNMATCHED,
                    "bureau": bureau_objects[bureau_code],
                    "category": category,
                    "description": description,
                    "source_status": raw_status,
                    "status": status_mapping[raw_status],
                    "assigned_officer": "Demo Officer",
                    "received_at": received_at,
                    "last_action_at": received_at + timedelta(days=1),
                    "next_action": "Review source documents" if raw_status != "disposed" else "No further action",
                    "sla_due_at": received_at + timedelta(days=30),
                },
            )
            CaseAction.objects.get_or_create(
                case=case,
                action_type="demo_seed",
                actor_label="Synthetic seed data",
                defaults={
                    "acted_at": case.received_at or now,
                    "remarks": "Synthetic example created by seed_demo.",
                },
            )
        self.stdout.write(self.style.SUCCESS("Synthetic demo records are ready."))

