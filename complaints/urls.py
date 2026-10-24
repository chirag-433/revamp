from django.urls import path
from rest_framework.authtoken.views import obtain_auth_token

from . import api, views

app_name = "complaints"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("cases/", views.case_list, name="case_list"),
    path("cases/<int:pk>/", views.case_detail, name="case_detail"),
    path("cases/<int:pk>/action/", views.record_case_action, name="record_case_action"),
    path("transfers/<int:pk>/respond/", views.respond_to_transfer, name="respond_to_transfer"),
    path("reports/", views.reports, name="reports"),
    path("reports/cases.csv", views.export_cases_csv, name="export_cases_csv"),
    path("reports/cases.xlsx", views.export_cases_xlsx, name="export_cases_xlsx"),
    path("reports/cases.pdf", views.export_cases_pdf, name="export_cases_pdf"),
    path("institutions/<int:pk>/", views.institution_detail, name="institution_detail"),
    path("import/", views.import_cases, name="import"),
    path("matches/", views.match_review_queue, name="match_review_queue"),
    path("matches/<int:pk>/action/", views.match_review_action, name="match_review_action"),
    path("overlaps/", views.overlap_list, name="overlap_list"),
    path("overlaps/<int:pk>/", views.overlap_detail, name="overlap_detail_legacy"),
    path("overlap/", views.overlap_center, name="overlap_center"),
    path("overlap/links/", views.link_cases, name="link_cases"),
    path("overlap/<int:pk>/", views.overlap_detail, name="overlap_detail"),
    path("overlap/<int:pk>/decision/", views.decide_overlap, name="decide_overlap"),
    path("overlap/<int:pk>/unlink/", views.unlink_cases, name="unlink_cases"),
    path("overlap/<int:pk>/messages/", views.post_coordination_message, name="post_coordination_message"),
    path("overlap/institution-matches/<int:pk>/", views.review_institution_match, name="review_institution_match"),
    path("coordination/notifications/", views.coordination_notifications, name="coordination_notifications"),
    path("api/ai-helpdesk/", views.ai_helpdesk, name="ai_helpdesk"),
    path("api/auth/login/", obtain_auth_token, name="api_token_login"),
    path("api/cases/", api.CaseListAPI.as_view(), name="api_cases"),
    path("api/cases/<int:pk>/", api.CaseDetailAPI.as_view(), name="api_case_detail"),
    path("api/cases/<int:pk>/actions/", api.CaseActionAPI.as_view(), name="api_case_actions"),
    path("api/institutions/", api.InstitutionListAPI.as_view(), name="api_institutions"),
    path("api/institutions/<int:pk>/", api.InstitutionDetailAPI.as_view(), name="api_institution_detail"),
    path("api/dashboard/summary/", api.DashboardSummaryAPI.as_view(), name="api_dashboard_summary"),
    path("api/ingest/csv/", api.CaseIngestAPI.as_view(), name="api_ingest_csv"),
]
