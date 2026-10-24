from difflib import SequenceMatcher
from itertools import combinations

from django.db import transaction
from django.utils import timezone
from django.db.models import Exists, F, OuterRef

from complaints.models import (
    AuditLog, CanonicalStatus, CaseLink, ComplaintCase, InstitutionMatchStatus,
)


def case_confidence(case):
    if case.match_confidence is not None:
        return float(case.match_confidence)
    if case.match_status == InstitutionMatchStatus.EXACT_ID:
        return 1.0
    return None


def compare_case_text(left, right):
    left_text = " ".join((left.category + " " + left.description).casefold().split())
    right_text = " ".join((right.category + " " + right.description).casefold().split())
    if not left_text or not right_text:
        return 0.0
    return SequenceMatcher(None, left_text, right_text).ratio()


def overlap_details(case_a, case_b):
    similarity = compare_case_text(case_a, case_b)
    same_category = bool(case_a.category and case_a.category.casefold() == case_b.category.casefold())
    confidence_values = [case_confidence(case_a), case_confidence(case_b)]
    confidence = min(confidence_values) if all(value is not None for value in confidence_values) else None
    if similarity > 0.75 and same_category:
        severity = "High"
    elif similarity > 0.5 or same_category:
        severity = "Medium"
    else:
        severity = "Low"
    highlights = []
    if same_category:
        highlights.append(f"Both cases are categorized as {case_a.category}.")
    else:
        highlights.append("The case categories differ.")
    highlights.append(f"Description text similarity: {similarity:.0%}.")
    explanation = (
        "Both cases are open, have the same resolved institution, and belong to different "
        f"Bureaus/Cells ({case_a.bureau.code} and {case_b.bureau.code}). "
        + " ".join(highlights)
    )
    return {
        "institution_match_method": "confirmed institution assignment",
        "institution_confidence": round(confidence, 4) if confidence is not None else None,
        "institution_confidence_percent": round(confidence * 100) if confidence is not None else None,
        "institution_confidence_display": f"{confidence:.0%}" if confidence is not None else "Not scored",
        "both_open": True,
        "bureaus": [case_a.bureau.code, case_b.bureau.code],
        "same_category": same_category,
        "text_similarity": round(similarity, 4),
        "severity": severity,
        "similarity_highlights": highlights,
        "readable_explanation": explanation,
    }, confidence


@transaction.atomic
def sync_overlap_suggestions(institution_id=None):
    """Create missing suggestions using the established resolved-institution rule."""
    cases = ComplaintCase.objects.filter(
        institution__isnull=False, match_status__in=[
            InstitutionMatchStatus.EXACT_ID, InstitutionMatchStatus.CONFIRMED
        ]
    ).exclude(status=CanonicalStatus.DISPOSED).select_related("institution", "bureau")
    if institution_id is not None:
        cases = cases.filter(institution_id=institution_id)
    created = []
    by_institution = {}
    for case in cases.order_by("institution_id", "id"):
        by_institution.setdefault(case.institution_id, []).append(case)
    for institution_cases in by_institution.values():
        for first, second in combinations(institution_cases, 2):
            if first.bureau_id == second.bureau_id:
                continue
            case_a, case_b = sorted((first, second), key=lambda case: case.pk)
            if CaseLink.objects.filter(
                case_a=case_a, case_b=case_b,
                link_type=CaseLink.LinkType.RELATED,
                review_state=CaseLink.ReviewState.CONFIRMED,
            ).exists():
                continue
            details, confidence = overlap_details(case_a, case_b)
            link, was_created = CaseLink.objects.get_or_create(
                case_a=case_a, case_b=case_b, link_type=CaseLink.LinkType.OVERLAP,
                defaults={"review_state": CaseLink.ReviewState.SUGGESTED,
                          "score": None, "explanation": details},
            )
            if was_created:
                created.append(link)
    return created


def suggested_overlap_links():
    active_related = CaseLink.objects.filter(
        case_a_id=OuterRef("case_a_id"),
        case_b_id=OuterRef("case_b_id"),
        link_type=CaseLink.LinkType.RELATED,
        review_state=CaseLink.ReviewState.CONFIRMED,
    )
    return CaseLink.objects.filter(
        link_type=CaseLink.LinkType.OVERLAP,
        review_state=CaseLink.ReviewState.SUGGESTED,
        case_a__status__in=[CanonicalStatus.PENDING, CanonicalStatus.UNDER_PROCESS,
                            CanonicalStatus.TRANSFERRED, CanonicalStatus.ESCALATED],
        case_b__status__in=[CanonicalStatus.PENDING, CanonicalStatus.UNDER_PROCESS,
                            CanonicalStatus.TRANSFERRED, CanonicalStatus.ESCALATED],
        case_a__institution_id=F("case_b__institution_id"),
    ).exclude(case_a__bureau_id=F("case_b__bureau_id")).annotate(
        has_related_link=Exists(active_related)
    ).filter(has_related_link=False)


# Phase 3 service API retained for the matching command and existing callers.
def detect_overlaps_for_case(case):
    if (not case.institution_id or case.status == CanonicalStatus.DISPOSED
            or case.match_status not in {InstitutionMatchStatus.EXACT_ID, InstitutionMatchStatus.CONFIRMED}):
        return []
    created = sync_overlap_suggestions(institution_id=case.institution_id)
    return [link for link in created if case.pk in {link.case_a_id, link.case_b_id}]


def detect_overlaps_for_institution(institution_id):
    return sync_overlap_suggestions(institution_id=institution_id)


def run_full_overlap_scan():
    from django.db.models import Count
    institutions = (
        ComplaintCase.objects.filter(
            institution__isnull=False,
            match_status__in=[InstitutionMatchStatus.EXACT_ID, InstitutionMatchStatus.CONFIRMED],
        ).exclude(status=CanonicalStatus.DISPOSED)
        .values("institution_id")
        .annotate(bureau_count=Count("bureau_id", distinct=True))
        .filter(bureau_count__gt=1)
    )
    stats = {"institutions_scanned": 0, "links_created": 0}
    for row in institutions:
        stats["institutions_scanned"] += 1
        stats["links_created"] += len(sync_overlap_suggestions(row["institution_id"]))
    return stats


def review_overlap(link, decision, user=None, note=""):
    """Compatibility API for Phase 3 callers; decisions remain audited."""
    choices = {
        "confirmed": (CaseLink.LinkType.OVERLAP, CaseLink.ReviewState.CONFIRMED, "overlap_confirmed"),
        "rejected": (CaseLink.LinkType.OVERLAP, CaseLink.ReviewState.REJECTED, "overlap_rejected"),
        "related": (CaseLink.LinkType.RELATED, CaseLink.ReviewState.CONFIRMED, "overlap_linked_as_related"),
    }
    if decision not in choices:
        raise ValueError(f"Invalid decision: {decision}")
    link.link_type, link.review_state, action = choices[decision]
    link.decided_by = user
    link.decision_note = note
    link.decided_at = timezone.now()
    link.save()
    AuditLog.objects.create(
        actor=user, action=action, entity_type="CaseLink", entity_id=str(link.pk),
        details={"case_a": link.case_a_id, "case_b": link.case_b_id,
                 "decision": decision, "reason": note, "note": note},
    )
    return link
