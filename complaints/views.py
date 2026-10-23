from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import BureauCell, CanonicalStatus, CaseLink, ComplaintCase, Institution, InstitutionMatchStatus
from .services.csv_import import CSVImportError, import_cases_csv
from .services.matching import resolve_institution
from .services.overlap import detect_overlaps_for_case, review_overlap


def case_list(request):
    cases = ComplaintCase.objects.select_related("institution", "bureau")
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    bureau = request.GET.get("bureau", "").strip()
    if query:
        cases = cases.filter(
            Q(case_number__icontains=query)
            | Q(source_case_id__icontains=query)
            | Q(raw_institution_name__icontains=query)
            | Q(institution__name__icontains=query)
        )
    if status in CanonicalStatus.values:
        cases = cases.filter(status=status)
    if bureau.isdigit():
        cases = cases.filter(bureau_id=int(bureau))
    paginator = Paginator(cases, 25)
    page = paginator.get_page(request.GET.get("page"))

    # Overlap stats for summary cards.
    pending_overlaps = CaseLink.objects.filter(
        link_type=CaseLink.LinkType.OVERLAP,
        review_state=CaseLink.ReviewState.SUGGESTED,
    ).count()

    return render(
        request,
        "complaints/case_list.html",
        {
            "page": page,
            "bureaus": BureauCell.objects.filter(is_active=True),
            "statuses": CanonicalStatus.choices,
            "filters": {"q": query, "status": status, "bureau": bureau},
            "total_cases": ComplaintCase.objects.count(),
            "unmapped_institutions": ComplaintCase.objects.filter(institution__isnull=True).count(),
            "pending_overlaps": pending_overlaps,
            "review_queue_count": ComplaintCase.objects.filter(
                match_status=InstitutionMatchStatus.FUZZY_SUGGESTED,
            ).count(),
        },
    )


def case_detail(request, pk):
    case = get_object_or_404(
        ComplaintCase.objects.select_related("institution", "bureau").prefetch_related("actions"),
        pk=pk,
    )

    # Find overlap links involving this case.
    overlap_links = CaseLink.objects.filter(
        Q(case_a=case) | Q(case_b=case),
        link_type=CaseLink.LinkType.OVERLAP,
    ).select_related("case_a__bureau", "case_b__bureau", "case_a__institution", "case_b__institution")

    # Find related / confirmed links.
    related_links = CaseLink.objects.filter(
        Q(case_a=case) | Q(case_b=case),
    ).exclude(
        link_type=CaseLink.LinkType.OVERLAP,
        review_state=CaseLink.ReviewState.REJECTED,
    ).select_related("case_a__bureau", "case_b__bureau")

    return render(request, "complaints/case_detail.html", {
        "case": case,
        "overlap_links": overlap_links,
        "related_links": related_links,
    })


def institution_detail(request, pk):
    institution = get_object_or_404(Institution, pk=pk)
    cases = institution.cases.select_related("bureau").order_by("-received_at", "-id")

    # Find bureaus with open cases for this institution.
    open_cases = cases.exclude(status=CanonicalStatus.DISPOSED)
    active_bureaus = list(
        open_cases.values_list("bureau__code", flat=True).distinct()
    )

    # Overlap links for this institution's cases.
    case_ids = list(cases.values_list("pk", flat=True))
    overlap_links = CaseLink.objects.filter(
        Q(case_a_id__in=case_ids) | Q(case_b_id__in=case_ids),
        link_type=CaseLink.LinkType.OVERLAP,
        review_state=CaseLink.ReviewState.SUGGESTED,
    ).select_related("case_a__bureau", "case_b__bureau")

    return render(
        request,
        "complaints/institution_detail.html",
        {
            "institution": institution,
            "cases": cases,
            "active_bureaus": active_bureaus,
            "has_overlap": len(active_bureaus) > 1,
            "overlap_links": overlap_links,
        },
    )


def import_cases(request):
    if request.method == "POST":
        uploaded_file = request.FILES.get("csv_file")
        if uploaded_file is None:
            messages.error(request, "Choose a CSV file to import.")
            return redirect("complaints:import")
        try:
            result = import_cases_csv(uploaded_file)
        except CSVImportError as exc:
            messages.error(request, str(exc))
            return redirect("complaints:import")

        # Run matching and overlap detection on newly imported cases.
        match_count = 0
        overlap_count = 0
        recently_touched = ComplaintCase.objects.filter(
            match_status=InstitutionMatchStatus.UNMATCHED,
            institution__isnull=True,
        ).exclude(raw_institution_name="")

        for case in recently_touched:
            matched = resolve_institution(case)
            if matched:
                match_count += 1
                new_links = detect_overlaps_for_case(case)
                overlap_count += len(new_links)

        messages.success(
            request,
            f"Import finished: {result.created} created, {result.updated} updated, "
            f"{len(result.errors)} row errors. "
            f"Matching resolved {match_count} institutions, {overlap_count} overlaps detected.",
        )
        return render(
            request,
            "complaints/import_result.html",
            {"result": result, "match_count": match_count, "overlap_count": overlap_count},
        )
    return render(request, "complaints/import.html")


# -----------------------------------------------------------------------
# Phase 3: Match review queue
# -----------------------------------------------------------------------

def match_review_queue(request):
    """List cases with fuzzy-suggested institution matches awaiting review."""
    cases = (
        ComplaintCase.objects
        .filter(match_status=InstitutionMatchStatus.FUZZY_SUGGESTED)
        .select_related("institution", "bureau")
        .order_by("-match_confidence", "-received_at")
    )
    paginator = Paginator(cases, 25)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "complaints/match_review_queue.html", {
        "page": page,
    })


def match_review_action(request, pk):
    """Confirm or reject a fuzzy institution match."""
    case = get_object_or_404(ComplaintCase, pk=pk)

    if request.method != "POST":
        return redirect("complaints:match_review_queue")

    decision = request.POST.get("decision", "").strip()

    if decision == "confirm":
        case.match_status = InstitutionMatchStatus.CONFIRMED
        case.save(update_fields=["match_status", "updated_at"])
        # Trigger overlap detection now that institution is confirmed.
        new_links = detect_overlaps_for_case(case)
        messages.success(
            request,
            f"Institution match confirmed for {case}. "
            f"{len(new_links)} overlap(s) detected.",
        )
    elif decision == "reject":
        case.institution = None
        case.match_status = InstitutionMatchStatus.UNMATCHED
        case.match_confidence = None
        case.save(update_fields=["institution", "match_status", "match_confidence", "updated_at"])
        messages.info(request, f"Institution match rejected for {case}.")
    else:
        messages.error(request, "Invalid decision.")

    return redirect("complaints:match_review_queue")


# -----------------------------------------------------------------------
# Phase 3: Overlap review
# -----------------------------------------------------------------------

def overlap_list(request):
    """List all overlap links, filterable by review state."""
    state_filter = request.GET.get("state", "suggested").strip()
    links = CaseLink.objects.filter(
        link_type=CaseLink.LinkType.OVERLAP,
    ).select_related(
        "case_a__institution", "case_a__bureau",
        "case_b__institution", "case_b__bureau",
        "decided_by",
    ).order_by("-created_at")

    if state_filter in CaseLink.ReviewState.values:
        links = links.filter(review_state=state_filter)

    paginator = Paginator(links, 20)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "complaints/overlap_list.html", {
        "page": page,
        "state_filter": state_filter,
        "review_states": CaseLink.ReviewState.choices,
        "pending_count": CaseLink.objects.filter(
            link_type=CaseLink.LinkType.OVERLAP,
            review_state=CaseLink.ReviewState.SUGGESTED,
        ).count(),
    })


def overlap_detail(request, pk):
    """Side-by-side comparison of two overlapping cases."""
    link = get_object_or_404(
        CaseLink.objects.select_related(
            "case_a__institution", "case_a__bureau",
            "case_b__institution", "case_b__bureau",
            "decided_by",
        ),
        pk=pk,
    )

    if request.method == "POST":
        decision = request.POST.get("decision", "").strip()
        note = request.POST.get("note", "").strip()
        user = request.user if request.user.is_authenticated else None

        try:
            review_overlap(link, decision, user=user, note=note)
            messages.success(request, f"Overlap marked as: {decision}.")
        except ValueError as exc:
            messages.error(request, str(exc))

        return redirect("complaints:overlap_detail", pk=pk)

    return render(request, "complaints/overlap_detail.html", {
        "link": link,
    })
