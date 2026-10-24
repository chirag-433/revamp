from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import generics, serializers, status
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .forms import CaseWorkflowForm
from .models import (
    AuditLog, BureauCell, CanonicalStatus, CaseAction, CaseTransfer, ComplaintCase, Institution,
    InstitutionMatchStatus,
)
from .services.csv_import import CSVImportError, import_cases_csv


def _scoped_cases(user):
    cases = ComplaintCase.objects.select_related("institution", "bureau")
    if user.is_superuser or user.is_staff or user.groups.filter(
        name__in=["overlap-managers", "senior-management", "admin"]
    ).exists():
        return cases
    bureau_codes = set(user.groups.filter(name__startswith="bureau:").values_list("name", flat=True))
    bureau_codes = {name.removeprefix("bureau:") for name in bureau_codes}
    regions = set(user.groups.filter(name__startswith="region:").values_list("name", flat=True))
    regions = {name.removeprefix("region:") for name in regions}
    if bureau_codes:
        cases = cases.filter(bureau__code__in=bureau_codes)
    if regions:
        cases = cases.filter(institution__region__in=regions)
    if settings_strict_role_scoping() and not bureau_codes and not regions:
        return cases.none()
    return cases


def settings_strict_role_scoping():
    from django.conf import settings
    return settings.STRICT_ROLE_SCOPING


class CaseSerializer(serializers.ModelSerializer):
    institution_name = serializers.CharField(source="institution.name", read_only=True, default="")
    permanent_id = serializers.CharField(source="institution.aicte_permanent_id", read_only=True, default="")
    bureau_code = serializers.CharField(source="bureau.code", read_only=True)
    actions = serializers.SerializerMethodField()

    class Meta:
        model = ComplaintCase
        fields = [
            "id", "case_number", "source_system", "source_case_id", "institution",
            "institution_name", "permanent_id", "raw_institution_name", "bureau",
            "bureau_code", "category", "description", "source_status", "status",
            "match_status", "match_confidence", "assigned_officer", "received_at",
            "last_action_at", "next_action", "expected_disposal_at", "sla_due_at", "actions",
        ]

    def get_actions(self, case):
        return [{
            "type": action.action_type,
            "actor": action.actor_label,
            "at": action.acted_at.isoformat(),
            "from_bureau": action.from_bureau.code if action.from_bureau else None,
            "to_bureau": action.to_bureau.code if action.to_bureau else None,
            "remarks": action.remarks,
        } for action in case.actions.select_related("from_bureau", "to_bureau").all()]


class InstitutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Institution
        fields = ["id", "aicte_permanent_id", "name", "address", "district", "state", "region"]


class CaseListAPI(generics.ListAPIView):
    serializer_class = CaseSerializer

    def get_queryset(self):
        cases = _scoped_cases(self.request.user)
        params = self.request.query_params
        for name, field in [("institution", "institution__name__icontains"),
                            ("permanent_id", "institution__aicte_permanent_id__icontains"),
                            ("region", "institution__region__iexact"),
                            ("category", "category__iexact")]:
            if params.get(name):
                cases = cases.filter(**{field: params[name]})
        if params.get("case_id"):
            cases = cases.filter(Q(case_number__icontains=params["case_id"])
                                 | Q(source_case_id__icontains=params["case_id"]))
        if params.get("bureau"):
            cases = cases.filter(bureau__code__iexact=params["bureau"])
        if params.get("status") in CanonicalStatus.values:
            cases = cases.filter(status=params["status"])
        if params.get("date_from"):
            cases = cases.filter(received_at__date__gte=params["date_from"])
        if params.get("date_to"):
            cases = cases.filter(received_at__date__lte=params["date_to"])
        return cases.order_by("-received_at", "-id")


class CaseDetailAPI(APIView):
    def get(self, request, pk):
        case = _scoped_cases(request.user).filter(pk=pk).first()
        if case is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(CaseSerializer(case).data)


class CaseActionAPI(APIView):
    def post(self, request, pk):
        if not request.user.has_perm("complaints.manage_case_workflow"):
            return Response({"detail": "Workflow permission required."}, status=status.HTTP_403_FORBIDDEN)
        case = _scoped_cases(request.user).filter(pk=pk).first()
        if case is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        form = CaseWorkflowForm(request.data)
        if not form.is_valid():
            return Response({"errors": form.errors}, status=status.HTTP_400_BAD_REQUEST)
        values = form.cleaned_data
        with transaction.atomic():
            case = ComplaintCase.objects.select_for_update().get(pk=case.pk)
            previous_status = case.status
            case.status = values["status"]
            case.next_action = values["next_action"]
            case.last_action_at = timezone.now()
            case.sla_due_at = values["sla_due_at"]
            case.save(update_fields=["status", "next_action", "last_action_at", "sla_due_at", "updated_at"])
            transfer_to = values.get("transfer_to")
            if transfer_to:
                CaseTransfer.objects.create(
                    case=case, from_bureau=case.bureau, to_bureau=transfer_to,
                    requested_by=request.user, previous_status=previous_status,
                    note=values["remarks"],
                )
            CaseAction.objects.create(
                case=case, action_type="transfer_requested" if transfer_to else f"Updated to {case.get_status_display()}",
                from_bureau=case.bureau, to_bureau=transfer_to, actor=request.user,
                actor_label=request.user.get_full_name() or request.user.get_username(),
                acted_at=case.last_action_at, remarks=values["remarks"],
            )
            AuditLog.objects.create(
                actor=request.user, action="case_workflow_updated", entity_type="ComplaintCase",
                entity_id=str(case.pk), details={"previous_status": previous_status, "status": case.status,
                                                 "transfer_to_bureau": transfer_to.code if transfer_to else None},
            )
        return Response(CaseSerializer(case).data, status=status.HTTP_200_OK)


class InstitutionListAPI(generics.ListAPIView):
    serializer_class = InstitutionSerializer

    def get_queryset(self):
        allowed_institutions = _scoped_cases(self.request.user).values("institution_id")
        institutions = Institution.objects.filter(is_active=True, pk__in=allowed_institutions).distinct()
        if self.request.query_params.get("q"):
            query = self.request.query_params["q"]
            institutions = institutions.filter(
                Q(name__icontains=query) | Q(aicte_permanent_id__icontains=query)
            )
        return institutions.order_by("name")


class InstitutionDetailAPI(APIView):
    def get(self, request, pk):
        cases = _scoped_cases(request.user).filter(institution_id=pk)
        institution = Institution.objects.filter(pk=pk, is_active=True, pk__in=cases.values("institution_id")).first()
        if institution is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        cases = cases.filter(institution=institution)
        return Response({
            **InstitutionSerializer(institution).data,
            "active_bureaus": list(cases.exclude(status=CanonicalStatus.DISPOSED)
                                    .values_list("bureau__code", flat=True).distinct()),
            "cases": CaseSerializer(cases.order_by("-received_at"), many=True).data,
        })


class DashboardSummaryAPI(APIView):
    def get(self, request):
        cases = _scoped_cases(request.user)
        now = timezone.now()
        return Response({
            "total": cases.count(),
            "by_status": {value: cases.filter(status=value).count() for value, _ in CanonicalStatus.choices},
            "overdue": cases.filter(sla_due_at__lt=now).exclude(status=CanonicalStatus.DISPOSED).count(),
            "due_soon": cases.filter(sla_due_at__gte=now, sla_due_at__lte=now + timedelta(days=3))
                .exclude(status=CanonicalStatus.DISPOSED).count(),
            "workload_by_bureau": list(cases.values("bureau__code").annotate(total=Count("id"))
                                        .order_by("bureau__code")),
            "ageing_days": {
                "0_15": cases.filter(received_at__gte=now - timedelta(days=15)).count(),
                "16_30": cases.filter(received_at__lt=now - timedelta(days=15),
                                      received_at__gte=now - timedelta(days=30)).count(),
                "31_60": cases.filter(received_at__lt=now - timedelta(days=30),
                                      received_at__gte=now - timedelta(days=60)).count(),
                "over_60": cases.filter(received_at__lt=now - timedelta(days=60)).count(),
            },
        })


class CaseIngestAPI(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        if not request.user.has_perm("complaints.add_complaintcase"):
            return Response({"detail": "Import permission required."}, status=status.HTTP_403_FORBIDDEN)
        uploaded = request.FILES.get("file")
        if uploaded is None:
            return Response({"detail": "Attach a CSV file in the `file` field."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            result = import_cases_csv(uploaded)
        except CSVImportError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"created": result.created, "updated": result.updated,
                         "errors": result.errors}, status=status.HTTP_200_OK)
