from django.urls import path

from . import views

app_name = "complaints"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("cases/", views.case_list, name="case_list"),
    path("cases/<int:pk>/", views.case_detail, name="case_detail"),
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
]
