from django.contrib import admin

from .models import (
    AuditLog,
    BureauCell,
    CaseAction,
    CaseLink,
    ComplaintCase,
    Institution,
    InstitutionAlias,
    StatusMap,
)


@admin.register(BureauCell)
class BureauCellAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    search_fields = ("code", "name")
    list_filter = ("is_active",)


class InstitutionAliasInline(admin.TabularInline):
    model = InstitutionAlias
    extra = 0


@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ("name", "aicte_permanent_id", "district", "state", "region")
    search_fields = ("name", "aicte_permanent_id", "district", "state")
    list_filter = ("state", "region", "is_active")
    inlines = (InstitutionAliasInline,)


@admin.register(ComplaintCase)
class ComplaintCaseAdmin(admin.ModelAdmin):
    list_display = (
        "case_number",
        "source_system",
        "institution",
        "bureau",
        "status",
        "match_status",
        "sla_due_at",
    )
    search_fields = (
        "case_number",
        "source_case_id",
        "raw_institution_name",
        "institution__name",
    )
    list_filter = ("source_system", "bureau", "status", "match_status", "category")
    date_hierarchy = "received_at"


@admin.register(CaseAction)
class CaseActionAdmin(admin.ModelAdmin):
    list_display = ("case", "action_type", "actor_label", "acted_at")
    list_filter = ("action_type", "from_bureau", "to_bureau")
    search_fields = ("case__case_number", "remarks", "actor_label")
    date_hierarchy = "acted_at"


@admin.register(CaseLink)
class CaseLinkAdmin(admin.ModelAdmin):
    list_display = ("case_a", "case_b", "link_type", "review_state", "score", "created_at")
    list_filter = ("link_type", "review_state")
    search_fields = ("case_a__case_number", "case_b__case_number")
    readonly_fields = ("created_at",)


@admin.register(StatusMap)
class StatusMapAdmin(admin.ModelAdmin):
    list_display = ("source_system", "source_status", "canonical_status")
    list_filter = ("source_system", "canonical_status")
    search_fields = ("source_system", "source_status")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "actor", "action", "entity_type", "entity_id")
    list_filter = ("action", "entity_type")
    search_fields = ("entity_type", "entity_id", "action")
    readonly_fields = ("actor", "action", "entity_type", "entity_id", "occurred_at", "details")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
