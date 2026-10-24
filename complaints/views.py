import csv
import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import (
    AuditLog, BureauCell, CanonicalStatus, CaseAction, CaseLink, ComplaintCase,
    CoordinationMessage, CoordinationNotification, Institution,
    InstitutionMatchStatus, SlaAlert, SyntheticMatchLabel,
)
from .forms import CaseWorkflowForm
from .services.ai_helpdesk import AIHelpdeskError, ask_sarvam
from .services.csv_import import CSVImportError, import_cases_csv
from .services.matching import (
    AUTO_THRESHOLD, REVIEW_THRESHOLD, find_candidates, resolve_institution,
)
from .services.overlap import (
    detect_overlaps_for_case, suggested_overlap_links, sync_overlap_suggestions,
)
from .services.sla import refresh_sla_alerts


def _bureau_group_codes(user):
    if not user.is_authenticated:
        return set()
    return {name.removeprefix("bureau:") for name in
            user.groups.filter(name__startswith="bureau:").values_list("name", flat=True)}


def _is_overlap_manager(user):
    return user.is_authenticated and (user.is_superuser or user.is_staff or
                                      user.groups.filter(name="overlap-managers").exists())


def _scope_overlap_links(user, queryset):
    codes = _bureau_group_codes(user)
    if codes and not _is_overlap_manager(user):
        return queryset.filter(Q(case_a__bureau__code__in=codes) | Q(case_b__bureau__code__in=codes))
    return queryset


def _can_access_case_pair(user, case_a, case_b):
    if _is_overlap_manager(user):
        return True
    codes = _bureau_group_codes(user)
    return not codes or case_a.bureau.code in codes or case_b.bureau.code in codes


def _scope_cases(user, queryset):
    codes = _bureau_group_codes(user)
    if codes and not _is_overlap_manager(user):
        return queryset.filter(bureau__code__in=codes)
    return queryset


def dashboard(request):
    refresh_sla_alerts()
    cases = _scope_cases(request.user, ComplaintCase.objects.select_related("institution", "bureau"))
    total = cases.count()
    open_cases = cases.exclude(status=CanonicalStatus.DISPOSED).count()
    escalated = cases.filter(status=CanonicalStatus.ESCALATED).count()
    unmatched = cases.filter(institution__isnull=True).count()
    needs_attention = cases.filter(
        Q(status=CanonicalStatus.ESCALATED)
        | Q(institution__isnull=True)
        | (Q(sla_due_at__lt=timezone.now()) & ~Q(status=CanonicalStatus.DISPOSED))
    ).order_by("sla_due_at", "-received_at")[:6]
    bureau_codes = _bureau_group_codes(request.user)
    bureau_rows = BureauCell.objects.filter(is_active=True)
    if bureau_codes and not _is_overlap_manager(request.user):
        bureau_rows = bureau_rows.filter(code__in=bureau_codes)
    bureau_load = list(
        bureau_rows.annotate(case_count=Count("cases", filter=Q(cases__in=cases)))
        .filter(case_count__gt=0).order_by("-case_count", "name")
    )
    max_load = max((bureau.case_count for bureau in bureau_load), default=1)
    for bureau in bureau_load:
        bureau.load_percent = round(bureau.case_count / max_load * 100)
    can_review = request.user.is_authenticated and request.user.has_perm("complaints.view_caselink")
    if can_review and request.user.has_perm("complaints.add_caselink"):
        sync_overlap_suggestions()
    overlap_links = []
    if can_review:
        overlap_links = list(
            _scope_overlap_links(request.user, suggested_overlap_links())
            .select_related("case_a__institution", "case_a__bureau",
                            "case_b__institution", "case_b__bureau")[:4]
        )
    now = timezone.now()
    due_soon_cases = cases.filter(
        sla_due_at__gt=now, sla_due_at__lte=now + timedelta(days=3)
    ).exclude(status=CanonicalStatus.DISPOSED).count()
    overdue_cases = cases.filter(sla_due_at__lt=now).exclude(status=CanonicalStatus.DISPOSED).count()
    active_sla_alerts = SlaAlert.objects.filter(
        resolved_at__isnull=True, case__in=cases
    ).select_related("case", "case__bureau", "case__institution").order_by(
        "case__sla_due_at", "opened_at"
    )[:8]
    return render(request, "complaints/dashboard.html", {
        "total_cases": total, "open_cases": open_cases,
        "escalated_cases": escalated, "unmatched_cases": unmatched,
        "due_soon_cases": due_soon_cases, "overdue_cases": overdue_cases,
        "sla_alerts": active_sla_alerts,
        "attention_cases": needs_attention,
        "recent_cases": cases.order_by("-received_at", "-id")[:6],
        "bureau_load": bureau_load,
        "status_rows": [(label, cases.filter(status=value).count(), value)
                        for value, label in CanonicalStatus.choices],
        "overlap_links": overlap_links,
        "overlap_alert_count": _scope_overlap_links(request.user, suggested_overlap_links()).count(),
        "borderline_match_count": _scope_cases(request.user, ComplaintCase.objects.filter(
            match_status=InstitutionMatchStatus.FUZZY_SUGGESTED)).count(),
        "can_review_overlaps": can_review,
    })


def case_list(request):
    cases = _scope_cases(request.user, ComplaintCase.objects.select_related("institution", "bureau"))
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    bureau = request.GET.get("bureau", "").strip()
    sla = request.GET.get("sla", "").strip()
    if query:
        cases = cases.filter(Q(case_number__icontains=query)
                             | Q(source_case_id__icontains=query)
                             | Q(raw_institution_name__icontains=query)
                             | Q(institution__name__icontains=query))
    if status in CanonicalStatus.values:
        cases = cases.filter(status=status)
    if bureau.isdigit():
        cases = cases.filter(bureau_id=int(bureau))
    now = timezone.now()
    if sla == "overdue":
        cases = cases.filter(sla_due_at__lt=now).exclude(status=CanonicalStatus.DISPOSED)
    elif sla == "due_soon":
        cases = cases.filter(sla_due_at__gt=now, sla_due_at__lte=now + timedelta(days=3)).exclude(
            status=CanonicalStatus.DISPOSED
        )
    paginator = Paginator(cases, 25)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "complaints/case_list.html", {
        "page": page, "bureaus": BureauCell.objects.filter(is_active=True,
            **({"code__in": _bureau_group_codes(request.user)} if _bureau_group_codes(request.user)
               and not _is_overlap_manager(request.user) else {})),
        "statuses": CanonicalStatus.choices,
        "filters": {"q": query, "status": status, "bureau": bureau, "sla": sla},
        "total_cases": _scope_cases(request.user, ComplaintCase.objects.all()).count(),
        "unmapped_institutions": _scope_cases(request.user, ComplaintCase.objects.filter(institution__isnull=True)).count(),
        "pending_overlaps": _scope_overlap_links(request.user, CaseLink.objects.filter(
            link_type=CaseLink.LinkType.OVERLAP, review_state=CaseLink.ReviewState.SUGGESTED)).count(),
        "review_queue_count": _scope_cases(request.user, ComplaintCase.objects.filter(
            match_status=InstitutionMatchStatus.FUZZY_SUGGESTED)).count(),
    })


def case_detail(request, pk):
    refresh_sla_alerts()
    case = get_object_or_404(_scope_cases(request.user,
        ComplaintCase.objects.select_related("institution", "bureau").prefetch_related("actions")), pk=pk)
    related_links = []
    if request.user.is_authenticated and request.user.has_perm("complaints.view_caselink"):
        related_links = _scope_overlap_links(request.user, CaseLink.objects.filter(
            link_case_query_for_case(case), review_state=CaseLink.ReviewState.CONFIRMED
        ).exclude(link_type=CaseLink.LinkType.OVERLAP)).select_related(
            "case_a", "case_b", "case_a__bureau", "case_b__bureau"
        )
    overlap_links = _scope_overlap_links(request.user, CaseLink.objects.filter(
        link_case_query_for_case(case), link_type=CaseLink.LinkType.OVERLAP)).select_related(
            "case_a__bureau", "case_b__bureau", "case_a__institution", "case_b__institution")
    form = CaseWorkflowForm(initial={
        "status": case.status, "next_action": case.next_action,
        "sla_due_at": timezone.localtime(case.sla_due_at).strftime("%Y-%m-%dT%H:%M") if case.sla_due_at else "",
    })
    can_update = request.user.is_authenticated and request.user.has_perm("complaints.manage_case_workflow")
    return render(request, "complaints/case_detail.html", {
        "case": case, "related_links": related_links, "overlap_links": overlap_links,
        "workflow_form": form, "can_update_workflow": can_update,
    })


@login_required
@permission_required("complaints.manage_case_workflow", raise_exception=True)
def record_case_action(request, pk):
    if request.method != "POST":
        return redirect("complaints:case_detail", pk=pk)
    case = get_object_or_404(_scope_cases(request.user,
        ComplaintCase.objects.select_related("bureau")), pk=pk)
    form = CaseWorkflowForm(request.POST)
    if not form.is_valid():
        details = " ".join(
            f"{label}: {', '.join(errors)}"
            for label, errors in form.errors.items()
        )
        messages.error(request, f"Please correct the workflow update. {details}")
        return redirect("complaints:case_detail", pk=case.pk)
    values = form.cleaned_data
    with transaction.atomic():
        case = ComplaintCase.objects.select_for_update().get(pk=case.pk)
        previous_status = case.status
        case.status = values["status"]
        case.next_action = values["next_action"]
        case.last_action_at = timezone.now()
        case.sla_due_at = values["sla_due_at"]
        case.save(update_fields=["status", "next_action", "last_action_at", "sla_due_at", "updated_at"])
        CaseAction.objects.create(
            case=case, action_type=f"Updated to {case.get_status_display()}", from_bureau=case.bureau,
            actor=request.user, actor_label=request.user.get_full_name() or request.user.get_username(),
            acted_at=case.last_action_at, remarks=values["remarks"],
        )
        AuditLog.objects.create(
            actor=request.user, action="case_workflow_updated", entity_type="ComplaintCase",
            entity_id=str(case.pk), details={"previous_status": previous_status,
                                             "status": case.status,
                                             "sla_due_at": case.sla_due_at.isoformat() if case.sla_due_at else None},
        )
    refresh_sla_alerts(case_ids=[case.pk])
    messages.success(request, "Case update recorded in the audit history.")
    return redirect("complaints:case_detail", pk=case.pk)


@login_required
@permission_required("complaints.view_complaintcase", raise_exception=True)
def reports(request):
    refresh_sla_alerts()
    cases = _scope_cases(request.user, ComplaintCase.objects.select_related("bureau", "institution"))
    now = timezone.now()
    labels = SyntheticMatchLabel.objects.filter(
        dataset="demo-match-v1", case__in=cases
    ).select_related("case", "expected_institution")
    evaluated = 0
    expected_matches = 0
    predicted_matches = 0
    true_positives = 0
    for label in labels:
        expected = label.expected_institution
        if expected:
            expected_matches += 1
        candidate = find_candidates(label.case.raw_institution_name, top_n=1)
        predicted = candidate[0].institution if candidate and candidate[0].score >= REVIEW_THRESHOLD else None
        if predicted:
            predicted_matches += 1
        if predicted and expected and predicted.pk == expected.pk:
            true_positives += 1
        evaluated += 1
    return render(request, "complaints/reports.html", {
        "total_cases": cases.count(),
        "open_cases": cases.exclude(status=CanonicalStatus.DISPOSED).count(),
        "overdue_cases": cases.filter(sla_due_at__lt=now).exclude(status=CanonicalStatus.DISPOSED).count(),
        "due_soon_cases": cases.filter(sla_due_at__gt=now, sla_due_at__lte=now + timedelta(days=3)).exclude(status=CanonicalStatus.DISPOSED).count(),
        "evaluated": evaluated,
        "expected_matches": expected_matches,
        "predicted_matches": predicted_matches,
        "true_positives": true_positives,
        "precision": round(true_positives / predicted_matches * 100, 1) if predicted_matches else None,
        "recall": round(true_positives / expected_matches * 100, 1) if expected_matches else None,
        "auto_threshold": AUTO_THRESHOLD,
        "review_threshold": REVIEW_THRESHOLD,
    })


@login_required
@permission_required("complaints.view_complaintcase", raise_exception=True)
def export_cases_csv(request):
    cases = _scope_cases(request.user, ComplaintCase.objects.select_related("institution", "bureau"))
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="institution-cases.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(["case_number", "source_system", "source_case_id", "institution",
                     "bureau", "category", "status", "received_at", "sla_due_at"])
    for case in cases.iterator(chunk_size=500):
        writer.writerow([case.case_number, case.source_system, case.source_case_id,
                         case.institution.name if case.institution else case.raw_institution_name,
                         case.bureau.code, case.category, case.get_status_display(),
                         case.received_at.isoformat() if case.received_at else "",
                         case.sla_due_at.isoformat() if case.sla_due_at else ""])
    return response


def link_case_query_for_case(case):
    return Q(case_a=case) | Q(case_b=case)


def institution_detail(request, pk):
    institution = get_object_or_404(Institution, pk=pk)
    cases = _scope_cases(request.user, institution.cases.select_related("bureau")).order_by("-received_at", "-id")
    can_review = request.user.is_authenticated and request.user.has_perm("complaints.view_caselink")
    links = []
    if can_review:
        if request.user.has_perm("complaints.add_caselink"):
            sync_overlap_suggestions(institution_id=institution.pk)
        case_ids = cases.values_list("pk", flat=True)
        links = _scope_overlap_links(request.user, suggested_overlap_links()).filter(
            Q(case_a_id__in=case_ids) | Q(case_b_id__in=case_ids)
        ).select_related("case_a__bureau", "case_b__bureau")
    has_overlap_alert = _scope_overlap_links(request.user, suggested_overlap_links()).filter(
        Q(case_a__institution_id=institution.pk) | Q(case_b__institution_id=institution.pk)
    ).exists()
    active_bureaus = list(cases.exclude(status=CanonicalStatus.DISPOSED).values_list("bureau__code", flat=True).distinct())
    return render(request, "complaints/institution_detail.html", {
        "institution": institution, "cases": cases, "overlap_links": links,
        "has_overlap_alert": has_overlap_alert, "has_overlap": len(active_bureaus) > 1,
        "active_bureaus": active_bureaus, "can_review_overlaps": can_review,
    })


@login_required
@permission_required("complaints.add_complaintcase", raise_exception=True)
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
        match_count = overlap_count = 0
        unresolved = ComplaintCase.objects.filter(match_status=InstitutionMatchStatus.UNMATCHED, institution__isnull=True).exclude(raw_institution_name="")
        for case in unresolved:
            matched = resolve_institution(case)
            if matched and case.match_status in {InstitutionMatchStatus.EXACT_ID, InstitutionMatchStatus.CONFIRMED}:
                match_count += 1
                overlap_count += len(detect_overlaps_for_case(case))
        messages.success(request,
            f"Import finished: {result.created} created, {result.updated} updated, "
            f"{len(result.errors)} row errors. Matching resolved {match_count} institutions, "
            f"{overlap_count} overlaps detected.")
        return render(request, "complaints/import_result.html", {"result": result, "match_count": match_count, "overlap_count": overlap_count})
    return render(request, "complaints/import.html")


# Disha AI help desk endpoint.
def ai_helpdesk(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST requests are allowed."}, status=405)
    try:
        payload = json.loads(request.body)
    except (TypeError, ValueError):
        return JsonResponse({"error": "Send a valid JSON message."}, status=400)

    message = str(payload.get("message", "")).strip()
    if not message:
        return JsonResponse({"error": "Please enter a question."}, status=400)
    if len(message) > 2000:
        return JsonResponse({"error": "Please keep your question under 2,000 characters."}, status=400)

    try:
        answer = ask_sarvam(message)
    except AIHelpdeskError as exc:
        return JsonResponse({"error": str(exc)}, status=503)
    return JsonResponse({"answer": answer})


@login_required
@permission_required("complaints.view_caselink", raise_exception=True)
def match_review_queue(request):
    cases = _scope_cases(request.user, ComplaintCase.objects.filter(
        match_status=InstitutionMatchStatus.FUZZY_SUGGESTED
    )).select_related("institution", "bureau").order_by("-match_confidence", "-received_at")
    page = Paginator(cases, 25).get_page(request.GET.get("page"))
    return render(request, "complaints/match_review_queue.html", {
        "page": page,
        "can_review": request.user.has_perm("complaints.review_case_links"),
    })


@login_required
@permission_required("complaints.review_case_links", raise_exception=True)
def match_review_action(request, pk):
    if request.method != "POST":
        return redirect("complaints:match_review_queue")
    case = get_object_or_404(ComplaintCase.objects.select_related("bureau", "institution"),
                             pk=pk, match_status=InstitutionMatchStatus.FUZZY_SUGGESTED)
    codes = _bureau_group_codes(request.user)
    if codes and not _is_overlap_manager(request.user) and case.bureau.code not in codes:
        return HttpResponseForbidden("You do not have access to this Bureau/Cell.")
    decision = request.POST.get("decision", "").strip()
    if decision == "confirm":
        case.match_status = InstitutionMatchStatus.CONFIRMED
        case.save(update_fields=["match_status", "updated_at"])
        created = sync_overlap_suggestions(institution_id=case.institution_id) if case.institution_id else []
        AuditLog.objects.create(actor=request.user, action="institution_match_confirmed",
                                entity_type="ComplaintCase", entity_id=str(case.pk),
                                details={"institution_id": case.institution_id})
        messages.success(request, f"Institution match confirmed for {case}. {len(created)} overlap(s) detected.")
    elif decision == "reject":
        previous_institution = case.institution_id
        case.institution = None
        case.match_status = InstitutionMatchStatus.UNMATCHED
        case.match_confidence = None
        case.save(update_fields=["institution", "match_status", "match_confidence", "updated_at"])
        AuditLog.objects.create(actor=request.user, action="institution_match_rejected",
                                entity_type="ComplaintCase", entity_id=str(case.pk),
                                details={"previous_institution_id": previous_institution})
        messages.info(request, f"Institution match rejected for {case}.")
    else:
        messages.error(request, "Invalid decision.")
    return redirect("complaints:match_review_queue")


@login_required
@permission_required("complaints.view_caselink", raise_exception=True)
def overlap_list(request):
    state_filter = request.GET.get("state", "suggested").strip()
    links = _scope_overlap_links(request.user, CaseLink.objects.filter(
        link_type=CaseLink.LinkType.OVERLAP
    )).select_related("case_a__institution", "case_a__bureau", "case_b__institution",
                        "case_b__bureau", "decided_by")
    if state_filter in CaseLink.ReviewState.values:
        links = links.filter(review_state=state_filter)
    page = Paginator(links.order_by("-created_at"), 20).get_page(request.GET.get("page"))
    pending_count = _scope_overlap_links(request.user, CaseLink.objects.filter(
        link_type=CaseLink.LinkType.OVERLAP, review_state=CaseLink.ReviewState.SUGGESTED
    )).count()
    return render(request, "complaints/overlap_list.html", {
        "page": page, "state_filter": state_filter,
        "review_states": CaseLink.ReviewState.choices, "pending_count": pending_count,
    })


@login_required
@permission_required("complaints.view_caselink", raise_exception=True)
def overlap_center(request):
    if request.user.has_perm("complaints.add_caselink"):
        sync_overlap_suggestions()
    suggestions = _scope_overlap_links(request.user, suggested_overlap_links()).select_related(
        "case_a__institution", "case_a__bureau", "case_b__institution", "case_b__bureau"
    )
    related_links = _scope_overlap_links(request.user, CaseLink.objects.filter(
        link_type=CaseLink.LinkType.RELATED, review_state=CaseLink.ReviewState.CONFIRMED
    )).select_related("case_a__bureau", "case_b__bureau")
    borderline_cases = _scope_cases(request.user, ComplaintCase.objects.filter(
        match_status=InstitutionMatchStatus.FUZZY_SUGGESTED
    )).select_related("institution", "bureau")
    return render(request, "complaints/overlap_center.html", {
        "suggestions": suggestions, "related_links": related_links,
        "borderline_cases": borderline_cases,
        "institutions": Institution.objects.filter(is_active=True),
        "can_edit": request.user.has_perm("complaints.review_case_links"),
        "can_message": request.user.has_perm("complaints.add_coordinationmessage"),
        "manual_link_cases": ComplaintCase.objects.select_related(
            "bureau", "institution"
        ).order_by("case_number", "pk")[:500],
    })


@login_required
@permission_required("complaints.view_caselink", raise_exception=True)
def overlap_detail(request, pk):
    if request.method == "POST":
        data = request.POST.copy()
        legacy_decisions = {"confirmed": "confirm", "rejected": "reject", "related": "related"}
        data["decision"] = legacy_decisions.get(data.get("decision", ""), data.get("decision", ""))
        data["reason"] = data.get("reason", data.get("note", ""))
        request.POST = data
        return decide_overlap(request, pk)
    link = get_object_or_404(
        CaseLink.objects.select_related(
            "case_a__institution", "case_a__bureau", "case_b__institution", "case_b__bureau"
        ).prefetch_related("messages__author", "messages__mentioned_bureau"), pk=pk
    )
    if not _can_access_case_pair(request.user, link.case_a, link.case_b):
        return HttpResponseForbidden("You do not have access to these Bureaus/Cells.")
    context = {
        "link": link,
        "case_a": link.case_a, "case_b": link.case_b,
        "other_bureaus": [link.case_a.bureau, link.case_b.bureau],
        "can_edit": request.user.has_perm("complaints.review_case_links"),
        "can_message": request.user.has_perm("complaints.add_coordinationmessage"),
        "related_cases": ComplaintCase.objects.exclude(
            pk__in=[link.case_a_id, link.case_b_id]
        ).select_related("bureau", "institution").order_by("case_number", "pk")[:500],
    }
    return render(request, "complaints/overlap_detail.html", context)


@login_required
@permission_required("complaints.review_case_links", raise_exception=True)
def decide_overlap(request, pk):
    if request.method != "POST":
        return redirect("complaints:overlap_center")
    with transaction.atomic():
        link = get_object_or_404(CaseLink.objects.select_for_update(), pk=pk)
        if not _can_access_case_pair(request.user, link.case_a, link.case_b):
            return HttpResponseForbidden("You do not have access to these Bureaus/Cells.")
        decision = request.POST.get("decision")
        note = request.POST.get("reason", "").strip()[:4000]
        if decision not in {"confirm", "related", "reject"}:
            messages.error(request, "Choose a valid overlap decision.")
            return redirect("complaints:overlap_detail", pk=link.pk)
        if (link.link_type != CaseLink.LinkType.OVERLAP
                or link.review_state != CaseLink.ReviewState.SUGGESTED):
            messages.info(request, "This overlap suggestion has already been reviewed. No changes were made.")
            return redirect("complaints:overlap_center")
        old_link_type = link.link_type
        if decision == "related":
            existing_related = CaseLink.objects.filter(
                case_a_id=link.case_a_id, case_b_id=link.case_b_id,
                link_type=CaseLink.LinkType.RELATED,
            ).first()
            if existing_related:
                existing_related.review_state = CaseLink.ReviewState.CONFIRMED
                existing_related.decided_by = request.user
                existing_related.decided_at = timezone.now()
                existing_related.decision_note = note
                existing_related.save()
                link.review_state = CaseLink.ReviewState.REJECTED
                link.decided_by = request.user
                link.decided_at = existing_related.decided_at
                link.decision_note = "Linked as related using existing link. " + note
                link.save()
                AuditLog.objects.create(actor=request.user, action="overlap_linked_as_related",
                                        entity_type="CaseLink", entity_id=str(link.pk),
                                        details={"decision": decision, "reason": note,
                                                 "related_link_id": existing_related.pk,
                                                 "case_a_id": link.case_a_id,
                                                 "case_b_id": link.case_b_id})
                messages.success(request, "The cases are linked as related.")
                return redirect("complaints:overlap_center")
            link.link_type = CaseLink.LinkType.RELATED
            link.review_state = CaseLink.ReviewState.CONFIRMED
            action = "overlap_linked_as_related"
        elif decision == "confirm":
            link.review_state = CaseLink.ReviewState.CONFIRMED
            action = "overlap_confirmed"
        else:
            link.review_state = CaseLink.ReviewState.REJECTED
            action = "overlap_rejected"
        link.decided_by = request.user
        link.decided_at = timezone.now()
        link.decision_note = note
        try:
            link.save()
        except Exception:
            if decision == "related":
                messages.error(request, "These cases already have a related-case link.")
                return redirect("complaints:overlap_detail", pk=link.pk)
            raise
        AuditLog.objects.create(actor=request.user, action=action,
                                entity_type="CaseLink", entity_id=str(link.pk),
                                details={"decision": decision, "reason": note,
                                         "case_a_id": link.case_a_id,
                                         "case_b_id": link.case_b_id,
                                         "previous_link_type": old_link_type})
    messages.success(request, "The overlap decision was recorded.")
    return redirect("complaints:overlap_center")


@login_required
@permission_required("complaints.review_case_links", raise_exception=True)
def link_cases(request):
    if request.method != "POST":
        return redirect("complaints:overlap_center")
    first_id, second_id = request.POST.get("case_a", ""), request.POST.get("case_b", "")
    if not first_id.isdigit() or not second_id.isdigit():
        messages.error(request, "Choose two valid cases.")
        return redirect("complaints:overlap_center")
    first = get_object_or_404(ComplaintCase, pk=first_id)
    second = get_object_or_404(ComplaintCase, pk=second_id)
    if not _can_access_case_pair(request.user, first, second):
        return HttpResponseForbidden("You do not have access to these Bureaus/Cells.")
    if first.pk == second.pk:
        messages.error(request, "Choose two different cases.")
        return redirect("complaints:overlap_center")
    with transaction.atomic():
        link, created = CaseLink.objects.get_or_create(
            case_a=min(first, second, key=lambda case: case.pk),
            case_b=max(first, second, key=lambda case: case.pk),
            link_type=CaseLink.LinkType.RELATED,
            defaults={"review_state": CaseLink.ReviewState.CONFIRMED},
        )
        link.review_state = CaseLink.ReviewState.CONFIRMED
        link.decided_by = request.user
        link.decided_at = timezone.now()
        link.decision_note = request.POST.get("reason", "").strip()[:4000]
        link.save()
        AuditLog.objects.create(actor=request.user, action="cases_manually_linked",
                                entity_type="CaseLink", entity_id=str(link.pk),
                                details={"case_a_id": link.case_a_id,
                                         "case_b_id": link.case_b_id,
                                         "reason": link.decision_note, "created": created})
    messages.success(request, "The cases are linked as related.")
    return redirect("complaints:overlap_detail", pk=link.pk)


@login_required
@permission_required("complaints.review_case_links", raise_exception=True)
def unlink_cases(request, pk):
    if request.method != "POST":
        return redirect("complaints:overlap_center")
    with transaction.atomic():
        link = get_object_or_404(CaseLink.objects.select_for_update(), pk=pk,
                                 link_type=CaseLink.LinkType.RELATED,
                                 review_state=CaseLink.ReviewState.CONFIRMED)
        if not _can_access_case_pair(request.user, link.case_a, link.case_b):
            return HttpResponseForbidden("You do not have access to these Bureaus/Cells.")
        link.review_state = CaseLink.ReviewState.REJECTED
        link.decided_by = request.user
        link.decided_at = timezone.now()
        link.decision_note = request.POST.get("reason", "").strip()[:4000]
        link.save()
        AuditLog.objects.create(actor=request.user, action="cases_manually_unlinked",
                                entity_type="CaseLink", entity_id=str(link.pk),
                                details={"case_a_id": link.case_a_id,
                                         "case_b_id": link.case_b_id,
                                         "reason": link.decision_note})
    messages.success(request, "The related-case link was removed.")
    return redirect("complaints:overlap_center")


@login_required
@permission_required("complaints.add_coordinationmessage", raise_exception=True)
def post_coordination_message(request, pk):
    if request.method != "POST":
        return redirect("complaints:overlap_detail", pk=pk)
    link = get_object_or_404(CaseLink.objects.select_related("case_a__bureau", "case_b__bureau"), pk=pk)
    mentioned_id = request.POST.get("mentioned_bureau", "")
    if not mentioned_id.isdigit():
        messages.error(request, "Choose one of the case Bureaus/Cells.")
        return redirect("complaints:overlap_detail", pk=pk)
    if not _can_access_case_pair(request.user, link.case_a, link.case_b):
        return HttpResponseForbidden("You do not have access to these Bureaus/Cells.")
    mentioned_bureau = get_object_or_404(
        BureauCell, pk=mentioned_id, pk__in=[link.case_a.bureau_id, link.case_b.bureau_id]
    )
    body = request.POST.get("body", "").strip()
    if not body or len(body) > 4000:
        messages.error(request, "Enter a message of 1 to 4,000 characters.")
        return redirect("complaints:overlap_detail", pk=pk)
    with transaction.atomic():
        thread_message = CoordinationMessage.objects.create(
            link=link, author=request.user, mentioned_bureau=mentioned_bureau, body=body
        )
        group_names = [f"bureau:{mentioned_bureau.code}", "overlap-managers"]
        recipients = request.user.__class__.objects.filter(is_active=True).filter(
            Q(groups__name__in=group_names) | Q(is_staff=True) | Q(is_superuser=True)
        ).exclude(pk=request.user.pk).distinct()
        notifications = [CoordinationNotification(recipient=user, message=thread_message)
                         for user in recipients]
        CoordinationNotification.objects.bulk_create(notifications, ignore_conflicts=True)
        notification_count = len(notifications)
        AuditLog.objects.create(actor=request.user, action="coordination_message_posted",
                                entity_type="CaseLink", entity_id=str(link.pk),
                                details={"message_id": thread_message.pk,
                                         "mentioned_bureau": mentioned_bureau.code})
    if notification_count:
        messages.success(
            request,
            f"Message posted to {mentioned_bureau.code}; notifications created for "
            f"{notification_count} recipient(s).",
        )
    else:
        messages.warning(
            request,
            f"Message posted to {mentioned_bureau.code}, but no active notification recipients "
            "were found. Check Bureau and overlap-manager group assignments.",
        )
    return redirect("complaints:overlap_detail", pk=pk)


@login_required
@permission_required("complaints.view_caselink", raise_exception=True)
def coordination_notifications(request):
    notices = CoordinationNotification.objects.filter(recipient=request.user).select_related(
        "message__link__case_a", "message__link__case_b", "message__author",
        "message__mentioned_bureau"
    )
    if request.method == "POST":
        notice = get_object_or_404(notices, pk=request.POST.get("notification_id"))
        if notice.read_at is None:
            notice.read_at = timezone.now()
            notice.save(update_fields=["read_at"])
        return redirect("complaints:overlap_detail", pk=notice.message.link_id)
    return render(request, "complaints/coordination_notifications.html", {
        "notifications": notices, "unread_count": notices.filter(read_at__isnull=True).count()
    })


@login_required
@permission_required("complaints.review_case_links", raise_exception=True)
def review_institution_match(request, pk):
    if request.method != "POST":
        return redirect("complaints:overlap_center")
    case = get_object_or_404(
        ComplaintCase.objects.select_related("institution", "bureau"), pk=pk,
        match_status=InstitutionMatchStatus.FUZZY_SUGGESTED
    )
    bureau_codes = _bureau_group_codes(request.user)
    if bureau_codes and not _is_overlap_manager(request.user) and case.bureau.code not in bureau_codes:
        return HttpResponseForbidden("You do not have access to this Bureau/Cell.")
    institution_id = request.POST.get("institution_id", "")
    if not institution_id.isdigit():
        messages.error(request, "Choose a valid institution.")
        return redirect("complaints:overlap_center")
    institution = get_object_or_404(Institution, pk=institution_id, is_active=True)
    old_institution_id = case.institution_id
    with transaction.atomic():
        case.institution = institution
        case.match_status = InstitutionMatchStatus.CONFIRMED
        case.save(update_fields=["institution", "match_status", "updated_at"])
        AuditLog.objects.create(actor=request.user, action="institution_match_confirmed",
                                entity_type="ComplaintCase", entity_id=str(case.pk),
                                details={"previous_institution_id": old_institution_id,
                                         "institution_id": institution.pk})
        created = sync_overlap_suggestions(institution_id=institution.pk)
    messages.success(request, f"Institution match confirmed. {len(created)} new overlap suggestion(s) checked.")
    return redirect("complaints:overlap_center")
