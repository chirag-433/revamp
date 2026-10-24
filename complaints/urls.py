from django.urls import path

from . import views

app_name = "complaints"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("cases/", views.case_list, name="case_list"),
    path("cases/<int:pk>/", views.case_detail, name="case_detail"),
    path("institutions/<int:pk>/", views.institution_detail, name="institution_detail"),
    path("matches/", views.match_review_queue, name="match_review_queue"),
    path("matches/<int:pk>/action/", views.match_review_action, name="match_review_action"),
    path("overlaps/", views.overlap_list, name="overlap_list"),
    path("overlaps/<int:pk>/", views.overlap_detail, name="overlap_detail"),
    path("import/", views.import_cases, name="import"),
]

