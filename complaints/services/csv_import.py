import csv
import io
from dataclasses import dataclass, field
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from complaints.models import (
    BureauCell,
    CanonicalStatus,
    CaseAction,
    ComplaintCase,
    Institution,
    InstitutionMatchStatus,
    StatusMap,
)


REQUIRED_COLUMNS = {
    "source_system",
    "source_case_id",
    "bureau_code",
    "institution_name",
    "source_status",
}
OPTIONAL_COLUMNS = {
    "case_number",
    "institution_permanent_id",
    "category",
    "description",
    "assigned_officer",
    "received_at",
    "last_action_at",
    "next_action",
    "expected_disposal_at",
    "sla_due_at",
    "action_remarks",
}
ALLOWED_COLUMNS = REQUIRED_COLUMNS | OPTIONAL_COLUMNS
MAX_UPLOAD_BYTES = 2 * 1024 * 1024


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    errors: list[str] = field(default_factory=list)


class CSVImportError(ValueError):
    pass


def _parse_datetime(value, row_number, field_name):
    value = (value or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CSVImportError(
            f"Row {row_number}: {field_name} must be an ISO 8601 date/time."
        ) from exc
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _value(row, key):
    return (row.get(key) or "").strip()


def _validate_row(row, row_number):
    for key in REQUIRED_COLUMNS:
        if not _value(row, key):
            raise CSVImportError(f"Row {row_number}: {key} is required.")
    for key, limit in (("source_system", 80), ("source_case_id", 120),
                       ("bureau_code", 32), ("institution_name", 240),
                       ("case_number", 120), ("category", 120),
                       ("assigned_officer", 160), ("source_status", 120),
                       ("institution_permanent_id", 64)):
        if len(_value(row, key)) > limit:
            raise CSVImportError(f"Row {row_number}: {key} exceeds {limit} characters.")


def _import_row(row, row_number):
    _validate_row(row, row_number)
    source_system = _value(row, "source_system")
    source_status = _value(row, "source_status")
    bureau = BureauCell.objects.filter(code__iexact=_value(row, "bureau_code"), is_active=True).first()
    if bureau is None:
        raise CSVImportError(
            f"Row {row_number}: unknown or inactive Bureau/Cell code '{_value(row, 'bureau_code')}'."
        )
    status_map = StatusMap.objects.filter(
        source_system__iexact=source_system,
        source_status__iexact=source_status,
    ).first()
    if status_map is None:
        raise CSVImportError(
            f"Row {row_number}: no status mapping for '{source_system}' / '{source_status}'."
        )

    permanent_id = _value(row, "institution_permanent_id")
    institution = None
    if permanent_id:
        institution = Institution.objects.filter(
            aicte_permanent_id__iexact=permanent_id,
            is_active=True,
        ).first()

    timestamps = {
        name: _parse_datetime(_value(row, name), row_number, name)
        for name in ("received_at", "last_action_at", "expected_disposal_at", "sla_due_at")
    }
    case, created = ComplaintCase.objects.get_or_create(
        source_system=source_system,
        source_case_id=_value(row, "source_case_id"),
        defaults={
            "bureau": bureau,
            "status": status_map.canonical_status,
            "source_status": source_status,
            "institution": institution,
            "raw_institution_name": _value(row, "institution_name"),
            "match_status": (
                InstitutionMatchStatus.EXACT_ID
                if institution
                else InstitutionMatchStatus.UNMATCHED
            ),
            "case_number": _value(row, "case_number"),
            "category": _value(row, "category"),
            "description": _value(row, "description"),
            "assigned_officer": _value(row, "assigned_officer"),
            "next_action": _value(row, "next_action"),
            **timestamps,
        },
    )
    if not created:
        case.bureau = bureau
        case.status = status_map.canonical_status
        case.source_status = source_status
        case.institution = institution
        case.raw_institution_name = _value(row, "institution_name")
        case.match_status = (
            InstitutionMatchStatus.EXACT_ID
            if institution
            else InstitutionMatchStatus.UNMATCHED
        )
        case.case_number = _value(row, "case_number")
        case.category = _value(row, "category")
        case.description = _value(row, "description")
        case.assigned_officer = _value(row, "assigned_officer")
        case.next_action = _value(row, "next_action")
        for name, value in timestamps.items():
            setattr(case, name, value)
        case.save()

    remarks = _value(row, "action_remarks") or "Imported from source CSV."
    CaseAction.objects.get_or_create(
        case=case,
        action_type="source_import",
        actor_label="CSV import",
        remarks=remarks,
        defaults={"acted_at": timestamps["last_action_at"] or timezone.now()},
    )
    return created


def import_cases_csv(uploaded_file):
    if uploaded_file.size > MAX_UPLOAD_BYTES:
        raise CSVImportError("CSV file exceeds the 2 MB upload limit.")
    try:
        text_file = io.TextIOWrapper(uploaded_file.file, encoding="utf-8-sig", newline="")
        reader = csv.DictReader(text_file)
        if reader.fieldnames is None:
            raise CSVImportError("The CSV file is empty or has no header row.")
        if any(not header or not header.strip() for header in reader.fieldnames):
            raise CSVImportError("Column names cannot be blank.")
        normalized_headers = [header.strip() for header in reader.fieldnames]
        if len(normalized_headers) != len(set(normalized_headers)):
            raise CSVImportError("Column names must be unique.")
        headers = set(normalized_headers)
        missing = sorted(REQUIRED_COLUMNS - headers)
        unknown = sorted(headers - ALLOWED_COLUMNS)
        if missing:
            raise CSVImportError("Missing required columns: " + ", ".join(missing))
        if unknown:
            raise CSVImportError("Unknown columns: " + ", ".join(unknown))

        result = ImportResult()
        for row_number, raw_row in enumerate(reader, start=2):
            if None in raw_row:
                result.errors.append(f"Row {row_number}: too many values for the CSV columns.")
                continue
            row = {(key or "").strip(): value or "" for key, value in raw_row.items()}
            if not any(value.strip() for value in row.values()):
                continue
            try:
                with transaction.atomic():
                    created = _import_row(row, row_number)
                result.created += int(created)
                result.updated += int(not created)
            except CSVImportError as exc:
                result.errors.append(str(exc))
        return result
    except UnicodeDecodeError as exc:
        raise CSVImportError("CSV must use UTF-8 encoding.") from exc
    except csv.Error as exc:
        raise CSVImportError(f"Could not read the CSV file: {exc}") from exc

