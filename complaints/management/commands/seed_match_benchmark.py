from django.core.management.base import BaseCommand
from django.utils import timezone

from complaints.models import (
    BureauCell, CanonicalStatus, ComplaintCase, Institution,
    InstitutionMatchStatus, SyntheticMatchLabel,
)


class Command(BaseCommand):
    help = "Create an isolated, reproducible labelled synthetic institution-match benchmark."

    def handle(self, *args, **options):
        bureau = BureauCell.objects.filter(is_active=True).order_by("code").first()
        if bureau is None:
            bureau = BureauCell.objects.create(code="BMARK", name="Synthetic Benchmark")
        now = timezone.now()
        labels_created = 0
        for index in range(1, 13):
            name = f"Benchmark {index:02d} Institute of Public Policy"
            institution, _ = Institution.objects.update_or_create(
                name=name,
                defaults={"district": "Synthetic District", "state": "Synthetic State",
                          "region": "Benchmark", "address": "Synthetic benchmark only",
                          "is_active": True},
            )
            cases = [
                (f"BMARK-POS-{index:02d}", name, institution),
                (f"BMARK-NEG-{index:02d}", f"Unregistered Maritime Academy {index:02d}", None),
            ]
            for source_id, raw_name, expected in cases:
                case, _ = ComplaintCase.objects.update_or_create(
                    source_system="BENCHMARK", source_case_id=source_id,
                    defaults={"case_number": source_id, "bureau": bureau,
                              "raw_institution_name": raw_name, "institution": None,
                              "match_status": InstitutionMatchStatus.UNMATCHED,
                              "status": CanonicalStatus.PENDING,
                              "category": "Synthetic matching benchmark",
                              "description": "Synthetic; contains no real complaint data.",
                              "received_at": now},
                )
                SyntheticMatchLabel.objects.update_or_create(
                    case=case,
                    defaults={"expected_institution": expected, "dataset": "demo-match-v1"},
                )
                labels_created += 1
        self.stdout.write(self.style.SUCCESS(
            f"Prepared {labels_created} labelled benchmark cases (12 expected matches, 12 expected non-matches)."
        ))
