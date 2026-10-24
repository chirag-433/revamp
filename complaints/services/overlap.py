"""
Cross-bureau overlap detection.

Creates CaseLink suggestions when the same resolved Institution has open cases
in different Bureaus/Cells.  Overlaps are coordination suggestions, never
automatic case merges.
"""

from django.db.models import Q
from django.utils import timezone

from complaints.models import (
    AuditLog,
    CanonicalStatus,
    CaseLink,
    ComplaintCase,
)


def detect_overlaps_for_case(case: ComplaintCase) -> list[CaseLink]:
    """
    Given a single case that has a resolved institution, find open cases
    for the same institution in *different* Bureaus/Cells and create
    CaseLink records (type=overlap, review_state=suggested).

    Returns a list of newly created CaseLinks.
    """
    if not case.institution_id:
        return []

    if case.status == CanonicalStatus.DISPOSED:
        return []

    # Find open cases for the same institution in other bureaus.
    other_cases = (
        ComplaintCase.objects
        .filter(institution_id=case.institution_id)
        .exclude(pk=case.pk)
        .exclude(bureau_id=case.bureau_id)
        .exclude(status=CanonicalStatus.DISPOSED)
    )

    created_links = []

    for other in other_cases:
        # Normalise order so (a, b) is always (smaller_pk, larger_pk).
        a_id, b_id = sorted([case.pk, other.pk])

        # Check if this link already exists (any type, any state).
        existing = CaseLink.objects.filter(
            case_a_id=a_id,
            case_b_id=b_id,
            link_type=CaseLink.LinkType.OVERLAP,
        ).exists()

        if existing:
            continue

        case_obj_a = case if case.pk == a_id else other
        case_obj_b = other if case.pk == a_id else case

        explanation = {
            "reason": "Same institution has open cases in different Bureaus/Cells",
            "institution_id": case.institution_id,
            "institution_name": case.institution.name if case.institution else "",
            "case_a_bureau": case_obj_a.bureau.code,
            "case_b_bureau": case_obj_b.bureau.code,
            "case_a_status": case_obj_a.status,
            "case_b_status": case_obj_b.status,
            "case_a_category": case_obj_a.category,
            "case_b_category": case_obj_b.category,
            "detected_at": timezone.now().isoformat(),
        }

        link = CaseLink.objects.create(
            case_a_id=a_id,
            case_b_id=b_id,
            link_type=CaseLink.LinkType.OVERLAP,
            review_state=CaseLink.ReviewState.SUGGESTED,
            explanation=explanation,
        )
        created_links.append(link)

    return created_links


def detect_overlaps_for_institution(institution_id: int) -> list[CaseLink]:
    """
    Run overlap detection across all open cases for a given institution.
    Returns newly created CaseLinks.
    """
    open_cases = (
        ComplaintCase.objects
        .filter(institution_id=institution_id)
        .exclude(status=CanonicalStatus.DISPOSED)
        .select_related("bureau", "institution")
    )

    cases_list = list(open_cases)
    if len(cases_list) < 2:
        return []

    case_ids = [c.pk for c in cases_list]
    existing_pairs = set(
        CaseLink.objects.filter(
            case_a_id__in=case_ids,
            case_b_id__in=case_ids,
            link_type=CaseLink.LinkType.OVERLAP,
        ).values_list("case_a_id", "case_b_id")
    )

    links_to_create = []
    seen_pairs = set()

    for i, case_a in enumerate(cases_list):
        for case_b in cases_list[i + 1:]:
            if case_a.bureau_id == case_b.bureau_id:
                continue

            a_id, b_id = sorted([case_a.pk, case_b.pk])
            pair_key = (a_id, b_id)
            if pair_key in seen_pairs or pair_key in existing_pairs:
                continue
            seen_pairs.add(pair_key)
            existing_pairs.add(pair_key)

            case_obj_a = case_a if case_a.pk == a_id else case_b
            case_obj_b = case_b if case_a.pk == a_id else case_a

            explanation = {
                "reason": "Same institution has open cases in different Bureaus/Cells",
                "institution_id": institution_id,
                "institution_name": case_obj_a.institution.name if case_obj_a.institution else "",
                "case_a_bureau": case_obj_a.bureau.code,
                "case_b_bureau": case_obj_b.bureau.code,
                "case_a_status": case_obj_a.status,
                "case_b_status": case_obj_b.status,
                "case_a_category": case_obj_a.category,
                "case_b_category": case_obj_b.category,
                "detected_at": timezone.now().isoformat(),
            }

            links_to_create.append(CaseLink(
                case_a_id=a_id,
                case_b_id=b_id,
                link_type=CaseLink.LinkType.OVERLAP,
                review_state=CaseLink.ReviewState.SUGGESTED,
                explanation=explanation,
            ))

    if links_to_create:
        return CaseLink.objects.bulk_create(links_to_create)
    return []


def run_full_overlap_scan() -> dict:
    """
    Scan all institutions that have open cases in multiple bureaus
    and create overlap suggestions.  Returns a summary.
    """
    from django.db import transaction
    from django.db.models import Count

    # Find institutions with open cases in more than one bureau.
    institutions_with_multi_bureau = (
        ComplaintCase.objects
        .exclude(status=CanonicalStatus.DISPOSED)
        .filter(institution__isnull=False)
        .values("institution_id")
        .annotate(bureau_count=Count("bureau_id", distinct=True))
        .filter(bureau_count__gt=1)
    )

    stats = {"institutions_scanned": 0, "links_created": 0}

    with transaction.atomic():
        for row in institutions_with_multi_bureau:
            stats["institutions_scanned"] += 1
            links = detect_overlaps_for_institution(row["institution_id"])
            stats["links_created"] += len(links)

    return stats


def review_overlap(
    link: CaseLink,
    decision: str,
    user=None,
    note: str = "",
) -> CaseLink:
    """
    Record an officer's decision on an overlap suggestion.

    *decision*: "confirmed", "rejected", or "related".
    """
    valid_decisions = {
        "confirmed": CaseLink.ReviewState.CONFIRMED,
        "rejected": CaseLink.ReviewState.REJECTED,
    }

    if decision == "related":
        link.link_type = CaseLink.LinkType.RELATED
        link.review_state = CaseLink.ReviewState.CONFIRMED
    elif decision in valid_decisions:
        link.review_state = valid_decisions[decision]
    else:
        raise ValueError(f"Invalid decision: {decision}")

    link.decided_by = user
    link.decision_note = note
    link.decided_at = timezone.now()
    link.save()

    # Audit log.
    AuditLog.objects.create(
        actor=user,
        action=f"overlap_{decision}",
        entity_type="CaseLink",
        entity_id=str(link.pk),
        details={
            "case_a": link.case_a_id,
            "case_b": link.case_b_id,
            "decision": decision,
            "note": note,
        },
    )

    return link
