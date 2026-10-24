"""
Institution matching: resolve a complaint case to a canonical Institution.

Three tiers:
  1. Exact AICTE Permanent ID match → confidence 1.0, auto-linked.
  2. Normalized name exact match → confidence 0.95, auto-linked.
  3. Fuzzy composite score → auto if ≥ 0.90, review if 0.70–0.90, else unmatched.

Composite weights (configurable):
  name_similarity  0.55
  token_overlap    0.15
  same_district    0.15
  same_state       0.15

Uses Python's difflib.SequenceMatcher so it works on SQLite and PostgreSQL.
"""

from dataclasses import dataclass
from difflib import SequenceMatcher

from complaints.models import (
    ComplaintCase,
    Institution,
    InstitutionAlias,
    InstitutionMatchStatus,
)
from complaints.services.normalization import normalize_institution_name


# Thresholds — tune these against labelled ground truth.
AUTO_THRESHOLD = 0.90
REVIEW_THRESHOLD = 0.70

# Composite score weights.
WEIGHT_NAME = 0.55
WEIGHT_TOKEN = 0.15
WEIGHT_DISTRICT = 0.15
WEIGHT_STATE = 0.15


@dataclass
class MatchCandidate:
    institution: Institution
    score: float
    tier: str          # "exact_id", "exact_name", "fuzzy"
    explanation: dict  # structured reasons


def _name_similarity(a: str, b: str) -> float:
    """Ratio between two normalised name strings."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _token_overlap(a: str, b: str) -> float:
    """Jaccard overlap of word tokens."""
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def _normalised_match(val_a: str, val_b: str) -> float:
    """1.0 if both values are nonempty and match (case-insensitive), else 0.0."""
    a = (val_a or "").strip().lower()
    b = (val_b or "").strip().lower()
    if a and b and a == b:
        return 1.0
    return 0.0


def find_candidates(
    raw_name: str,
    district: str = "",
    state: str = "",
    exclude_id: int | None = None,
    top_n: int = 10,
) -> list[MatchCandidate]:
    """
    Return up to *top_n* candidate Institutions ranked by composite score.

    *exclude_id* can be used to skip a known-wrong institution.
    """
    norm_name = normalize_institution_name(raw_name)
    if not norm_name:
        return []

    candidates: list[MatchCandidate] = []

    # Collect all active institutions.
    institutions = Institution.objects.filter(is_active=True)
    if exclude_id:
        institutions = institutions.exclude(pk=exclude_id)

    for inst in institutions:
        best_name_sim = _name_similarity(norm_name, inst.normalized_name)
        best_token_ov = _token_overlap(norm_name, inst.normalized_name)
        matched_via = "name"

        # Also check aliases for a better match.
        for alias in InstitutionAlias.objects.filter(institution=inst):
            alias_sim = _name_similarity(norm_name, alias.normalized_alias)
            alias_tok = _token_overlap(norm_name, alias.normalized_alias)
            if alias_sim > best_name_sim:
                best_name_sim = alias_sim
                best_token_ov = alias_tok
                matched_via = f"alias:{alias.alias}"

        # Exact normalised name match is tier 2.
        if norm_name == inst.normalized_name:
            candidates.append(MatchCandidate(
                institution=inst,
                score=0.95,
                tier="exact_name",
                explanation={
                    "tier": "exact_name",
                    "normalized_query": norm_name,
                    "normalized_match": inst.normalized_name,
                },
            ))
            continue

        # Check aliases for exact match too.
        exact_alias = InstitutionAlias.objects.filter(
            institution=inst, normalized_alias=norm_name
        ).first()
        if exact_alias:
            candidates.append(MatchCandidate(
                institution=inst,
                score=0.95,
                tier="exact_name",
                explanation={
                    "tier": "exact_name_via_alias",
                    "alias": exact_alias.alias,
                    "normalized_query": norm_name,
                    "normalized_match": exact_alias.normalized_alias,
                },
            ))
            continue

        # Fuzzy composite: dynamically normalize across available signals
        dist_match = _normalised_match(district, inst.district)
        state_match = _normalised_match(state, inst.state)

        active_weight = WEIGHT_NAME + WEIGHT_TOKEN
        raw_score = WEIGHT_NAME * best_name_sim + WEIGHT_TOKEN * best_token_ov

        if district:
            active_weight += WEIGHT_DISTRICT
            raw_score += WEIGHT_DISTRICT * dist_match
        if state:
            active_weight += WEIGHT_STATE
            raw_score += WEIGHT_STATE * state_match

        composite = raw_score / active_weight if active_weight > 0 else 0.0

        if composite < 0.30:
            # Skip very weak matches to save space.
            continue

        candidates.append(MatchCandidate(
            institution=inst,
            score=round(composite, 4),
            tier="fuzzy",
            explanation={
                "tier": "fuzzy",
                "name_similarity": round(best_name_sim, 4),
                "token_overlap": round(best_token_ov, 4),
                "district_match": dist_match,
                "state_match": state_match,
                "composite_score": round(composite, 4),
                "matched_via": matched_via,
            },
        ))

    # Sort by score descending, return the top N.
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:top_n]


def resolve_institution(case: ComplaintCase) -> MatchCandidate | None:
    """
    Try to resolve a case to an institution.  Returns the best candidate if any
    meets the review threshold, or None.

    Side-effects: updates case.institution, case.match_status,
    case.match_confidence.
    """
    # Tier 1: exact Permanent ID (already handled in csv_import for the easy path,
    # but we also handle it here for cases that arrive without).
    # Skip if already exactly matched.
    if case.match_status == InstitutionMatchStatus.EXACT_ID and case.institution:
        return None

    # Try all candidates.
    candidates = find_candidates(
        raw_name=case.raw_institution_name,
        district=case.institution.district if case.institution else "",
        state=case.institution.state if case.institution else "",
    )

    if not candidates:
        case.match_status = InstitutionMatchStatus.UNMATCHED
        case.match_confidence = None
        case.save(update_fields=["match_status", "match_confidence", "updated_at"])
        return None

    best = candidates[0]

    if best.score >= AUTO_THRESHOLD:
        case.institution = best.institution
        case.match_status = InstitutionMatchStatus.EXACT_ID if best.tier == "exact_id" else InstitutionMatchStatus.CONFIRMED
        case.match_confidence = best.score
        case.save(update_fields=[
            "institution", "match_status", "match_confidence", "updated_at",
        ])
        return best

    if best.score >= REVIEW_THRESHOLD:
        case.institution = best.institution
        case.match_status = InstitutionMatchStatus.FUZZY_SUGGESTED
        case.match_confidence = best.score
        case.save(update_fields=[
            "institution", "match_status", "match_confidence", "updated_at",
        ])
        return best

    # Below review threshold — leave unmatched.
    case.match_status = InstitutionMatchStatus.UNMATCHED
    case.match_confidence = best.score
    case.save(update_fields=["match_status", "match_confidence", "updated_at"])
    return None


def resolve_unmatched_cases() -> dict:
    """
    Batch-resolve all cases that are currently unmatched (no institution linked).
    Returns a summary dict.
    """
    unmatched = ComplaintCase.objects.filter(
        match_status=InstitutionMatchStatus.UNMATCHED,
        institution__isnull=True,
    ).exclude(raw_institution_name="")

    stats = {"resolved_auto": 0, "suggested_review": 0, "still_unmatched": 0}

    for case in unmatched:
        result = resolve_institution(case)
        if result is None:
            stats["still_unmatched"] += 1
        elif case.match_status == InstitutionMatchStatus.FUZZY_SUGGESTED:
            stats["suggested_review"] += 1
        else:
            stats["resolved_auto"] += 1

    return stats
