from django.urls import path

from operations import views


app_name = "operations"

urlpatterns = [
    path("", views.manager_dashboard_view, name="dashboard"),
    path("plagiarism/<slug:source>/<int:submission_id>/", views.plagiarism_review_view, name="plagiarism_review"),
    path("regions/<slug:code>/", views.region_dashboard_view, name="region_dashboard"),
    path("taskers/<int:tasker_id>/", views.tasker_performance_view, name="tasker_performance"),
    path("escalations/<int:case_id>/resolve/", views.resolve_escalation_view, name="resolve_escalation"),
]
