from django.urls import path
from . import views

app_name = 'api'

urlpatterns = [
    path('v1/me/', views.me_view, name='me'),
    path('v1/subscription/', views.subscription_view, name='subscription'),
    path('v1/analytics/health-score/', views.health_score_view, name='health-score'),
    path('v1/analytics/usage/', views.usage_view, name='usage'),
    path('v1/analytics/recommendations/', views.recommendations_view, name='recommendations'),
    path('v1/analytics/activity/', views.activity_view, name='activity'),
    path('v1/portal/summary/', views.portal_summary_view, name='portal-summary'),
    path('v1/marketplace/tasks/', views.marketplace_tasks_view, name='marketplace-tasks'),
    path('v1/trust/application/', views.trust_application_view, name='trust-application'),
    path('v1/operations/overview/', views.operations_overview_view, name='operations-overview'),
    path('v1/notifications/mark-read/', views.notification_mark_read_view, name='notification-mark-read'),
    
    # Interactive Interview APIs
    path('v1/interview/create/', views.create_interview_session_view, name='interview-create'),
    path('v1/interview/start/', views.start_interview_view, name='interview-start'),
    path('v1/interview/submit-answer/', views.submit_answer_view, name='interview-submit-answer'),
    path('v1/interview/next-question/', views.next_question_view, name='interview-next-question'),
    path('v1/interview/complete/', views.complete_interview_view, name='interview-complete'),
    path('v1/interview/progress/', views.interview_progress_view, name='interview-progress'),
]
