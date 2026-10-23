from django.urls import path

from . import views

app_name = "complaints"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("cases/", views.case_list, name="case_list"),
    path("cases/<int:pk>/", views.case_detail, name="case_detail"),
    path("institutions/<int:pk>/", views.institution_detail, name="institution_detail"),
    path("import/", views.import_cases, name="import"),
]

