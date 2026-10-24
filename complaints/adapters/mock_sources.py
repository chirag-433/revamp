import csv
import json
from abc import ABC, abstractmethod
from pathlib import Path

from django.conf import settings


class SourceAdapter(ABC):
    """Read a source-specific fixture and map rows to the importer contract."""

    source_system = ""

    @abstractmethod
    def fetch_changes(self):
        """Yield dictionaries from one source snapshot."""

    @abstractmethod
    def map_to_canonical(self, row):
        """Return fields accepted by the shared CSV importer."""

    def canonical_rows(self):
        for row in self.fetch_changes():
            yield self.map_to_canonical(row)


class MockRBAdapter(SourceAdapter):
    source_system = "MOCK_RB"

    def fetch_changes(self):
        path = Path(settings.BASE_DIR) / "static" / "sample_data" / "mock_rb.json"
        return iter(json.loads(path.read_text(encoding="utf-8")))

    def map_to_canonical(self, row):
        return {
            "source_system": self.source_system,
            "source_case_id": str(row.get("reference", "")),
            "case_number": str(row.get("display_no", "")),
            "bureau_code": "RB",
            "institution_name": str(row.get("college", "")),
            "institution_permanent_id": str(row.get("aicte_id", "")),
            "source_status": str(row.get("state", "")),
            "category": str(row.get("issue", "")),
            "description": str(row.get("summary", "")),
            "assigned_officer": str(row.get("owner", "")),
            "next_action": str(row.get("next_step", "")),
            "received_at": str(row.get("received", "")),
            "action_remarks": str(row.get("latest_note", "")),
        }


class MockPGRCAdapter(SourceAdapter):
    source_system = "MOCK_PGRC"

    def fetch_changes(self):
        path = Path(settings.BASE_DIR) / "static" / "sample_data" / "mock_pgrc.csv"
        with path.open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))

    def map_to_canonical(self, row):
        return {
            "source_system": self.source_system,
            "source_case_id": str(row.get("ticket", "")),
            "case_number": str(row.get("grievance_ref", "")),
            "bureau_code": "PGRC",
            "institution_name": str(row.get("institute", "")),
            "institution_permanent_id": str(row.get("permanent_code", "")),
            "source_status": str(row.get("workflow", "")),
            "category": str(row.get("subject", "")),
            "description": str(row.get("details", "")),
            "assigned_officer": str(row.get("case_worker", "")),
            "next_action": str(row.get("follow_up", "")),
            "received_at": str(row.get("created", "")),
            "action_remarks": str(row.get("officer_note", "")),
        }
