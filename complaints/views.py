from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import BureauCell, CanonicalStatus, ComplaintCase, Institution
from .services.csv_import import CSVImportError, import_cases_csv


def dashboard(request):
    cases = ComplaintCase.objects.select_related("institution", "bureau")
    total = cases.count()
    open_cases = cases.exclude(status=CanonicalStatus.DISPOSED).count()
    escalated = cases.filter(status=CanonicalStatus.ESCALATED).count()
    unmatched = cases.filter(institution__isnull=True).count()
    needs_attention = cases.filter(
        Q(status=CanonicalStatus.ESCALATED)
        | Q(institution__isnull=True)
        | (
            Q(sla_due_at__lt=timezone.now())
            & ~Q(status=CanonicalStatus.DISPOSED)
        )
    ).order_by("sla_due_at", "-received_at")[:6]
    bureau_load = list(
        BureauCell.objects.filter(is_active=True)
        .annotate(case_count=Count("cases"))
        .filter(case_count__gt=0)
        .order_by("-case_count", "name")
    )
    max_load = max((bureau.case_count for bureau in bureau_load), default=1)
    for bureau in bureau_load:
        bureau.load_percent = round(bureau.case_count / max_load * 100)

    return render(
        request,
        "complaints/dashboard.html",
        {
            "total_cases": total,
            "open_cases": open_cases,
            "escalated_cases": escalated,
            "unmatched_cases": unmatched,
            "attention_cases": needs_attention,
            "recent_cases": cases.order_by("-received_at", "-id")[:6],
            "bureau_load": bureau_load,
            "status_rows": [
                (label, cases.filter(status=value).count(), value)
                for value, label in CanonicalStatus.choices
            ],
        },
    )


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
        },
    )


def case_detail(request, pk):
    case = get_object_or_404(
        ComplaintCase.objects.select_related("institution", "bureau").prefetch_related("actions"),
        pk=pk,
    )
    return render(request, "complaints/case_detail.html", {"case": case})


def institution_detail(request, pk):
    institution = get_object_or_404(Institution, pk=pk)
    cases = institution.cases.select_related("bureau").order_by("-received_at", "-id")
    return render(
        request,
        "complaints/institution_detail.html",
        {"institution": institution, "cases": cases},
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
        messages.success(
            request,
            f"Import finished: {result.created} created, {result.updated} updated, "
            f"{len(result.errors)} row errors.",
        )
        return render(
            request,
            "complaints/import_result.html",
            {"result": result},
        )
    return render(request, "complaints/import.html")

