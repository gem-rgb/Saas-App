from django.urls import path

from trust import views


app_name = "trust"

urlpatterns = [
    path("", views.application_dashboard_view, name="dashboard"),
    path("apply/", views.application_submit_view, name="apply"),
    path("kyc/", views.kyc_dashboard_view, name="kyc_dashboard"),
    path("onboarding/", views.onboarding_view, name="onboarding"),
    path("interview/", views.interview_dashboard_view, name="interview_dashboard"),
    path("review/<int:pk>/", views.application_review_view, name="application_review"),
]
