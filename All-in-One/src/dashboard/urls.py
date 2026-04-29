from django.urls import path

from dashboard import views


app_name = "dashboard"

urlpatterns = [
    path("", views.dashboard_view, name="portal-home"),
    path("student/", views.student_dashboard_view, name="student-dashboard"),
    path("tasker/", views.tasker_dashboard_view, name="tasker-dashboard"),
    path("manager/", views.manager_dashboard_view, name="manager-dashboard"),
    path("admin/", views.admin_dashboard_view, name="admin-dashboard"),
]

