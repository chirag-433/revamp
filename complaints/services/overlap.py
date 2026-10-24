from itertools import combinations
import math
import re

from django.db import transaction
from django.utils import timezone
from django.db.models import Exists, F, OuterRef, Q

from complaints.models import (
    AuditLog, CanonicalStatus, CaseAction, CaseLink, ComplaintCase,
    ConflictRule, InstitutionMatchStatus,
)


def case_confidence(case):
    if case.match_confidence is not None:
        return float(case.match_confidence)
    if case.match_status == InstitutionMatchStatus.EXACT_ID:
        return 1.0
    return None


def compare_case_text(left, right):
    left_tokens = re.findall(r"\w+", f"{left.category} {left.description}".casefold())
    right_tokens = re.findall(r"\w+", f"{right.category} {right.description}".casefold())
    if not left_tokens or not right_tokens:
        return 0.0
    left_counts = {token: left_tokens.count(token) for token in set(left_tokens)}
    right_counts = {token: right_tokens.count(token) for token in set(right_tokens)}
    vocabulary = left_counts.keys() | right_counts.keys()
    left_vector = {}
    right_vector = {}
    for token in vocabulary:
        in_left = token in left_counts
        in_right = token in right_counts
        inverse_document_frequency = math.log(3 / (1 + int(in_left) + int(in_right))) + 1
        left_vector[token] = left_counts.get(token, 0) * inverse_document_frequency
        right_vector[token] = right_counts.get(token, 0) * inverse_document_frequency
    dot = sum(left_vector[token] * right_vector[token] for token in vocabulary)
    left_norm = math.sqrt(sum(value * value for value in left_vector.values()))
    right_norm = math.sqrt(sum(value * value for value in right_vector.values()))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


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
    by_institution = {}
    for case in cases.order_by("institution_id", "id"):
        by_institution.setdefault(case.institution_id, []).append(case)
    case_ids = [case.pk for group in by_institution.values() for case in group]
    existing_links = CaseLink.objects.filter(
        Q(case_a_id__in=case_ids) | Q(case_b_id__in=case_ids)
    ).values_list("case_a_id", "case_b_id", "link_type", "review_state") if case_ids else []
    existing_overlap_pairs = set()
    confirmed_related_pairs = set()
    for case_a_id, case_b_id, link_type, review_state in existing_links:
        pair = (case_a_id, case_b_id)
        if link_type == CaseLink.LinkType.OVERLAP:
            existing_overlap_pairs.add(pair)
        elif (link_type == CaseLink.LinkType.RELATED
              and review_state == CaseLink.ReviewState.CONFIRMED):
            confirmed_related_pairs.add(pair)

    pending_links = []
    for institution_cases in by_institution.values():
        for first, second in combinations(institution_cases, 2):
            if first.bureau_id == second.bureau_id:
                continue
            case_a, case_b = sorted((first, second), key=lambda case: case.pk)
            pair = (case_a.pk, case_b.pk)
            if pair in confirmed_related_pairs or pair in existing_overlap_pairs:
                continue
            details, _confidence = overlap_details(case_a, case_b)
            pending_links.append(CaseLink(
                case_a=case_a, case_b=case_b, link_type=CaseLink.LinkType.OVERLAP,
                review_state=CaseLink.ReviewState.SUGGESTED,
                score=None, explanation=details,
            ))
            existing_overlap_pairs.add(pair)
    if pending_links:
        CaseLink.objects.bulk_create(
            pending_links, batch_size=500, ignore_conflicts=True
            )
        pending_pairs = {(link.case_a_id, link.case_b_id) for link in pending_links}
        return [
            link for link in CaseLink.objects.filter(
                link_type=CaseLink.LinkType.OVERLAP,
            ).filter(Q(case_a_id__in=case_ids) | Q(case_b_id__in=case_ids))
            if (link.case_a_id, link.case_b_id) in pending_pairs
        ]
    return []


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
    institution_count = institutions.count()
    return {
        "institutions_scanned": institution_count,
        "links_created": len(sync_overlap_suggestions()),
    }


@transaction.atomic
def sync_conflict_suggestions():
    """Create review suggestions when configured contradictory actions coexist."""
    created = []
    for rule in ConflictRule.objects.filter(is_active=True):
        first_actions = CaseAction.objects.filter(
            action_type__iexact=rule.action_type_a,
            case__institution__isnull=False,
        ).select_related("case__institution", "case__bureau")
        for first_action in first_actions.iterator(chunk_size=500):
            first_case = first_action.case
            other_actions = CaseAction.objects.filter(
                action_type__iexact=rule.action_type_b,
                case__institution_id=first_case.institution_id,
            ).exclude(case__bureau_id=first_case.bureau_id).exclude(
                case_id=first_case.pk
            ).select_related("case__institution", "case__bureau")
            for second_action in other_actions.iterator(chunk_size=500):
                second_case = second_action.case
                case_a, case_b = sorted((first_case, second_case), key=lambda case: case.pk)
                explanation = {
                    "rule": rule.name,
                    "reason": rule.explanation,
                    "actions": [first_action.action_type, second_action.action_type],
                    "bureaus": [case_a.bureau.code, case_b.bureau.code],
                    "severity": "High",
                }
                link, was_created = CaseLink.objects.get_or_create(
                    case_a=case_a, case_b=case_b,
                    link_type=CaseLink.LinkType.CONFLICT,
                    defaults={"review_state": CaseLink.ReviewState.SUGGESTED,
                              "explanation": explanation},
                )
                if was_created:
                    created.append(link)
    return created


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
