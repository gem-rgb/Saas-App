from django.urls import path

from marketplace import views, webhooks


app_name = "marketplace"

urlpatterns = [
    path("", views.board_view, name="board"),
    path("tasks/new/", views.task_create_view, name="task_create"),
    path("tasks/<int:pk>/", views.task_detail_view, name="task_detail"),
    path("tasks/<int:pk>/messages/", views.task_message_post_view, name="task_message_post"),
    path("tasks/<int:pk>/publish/", views.task_publish_view, name="task_publish"),
    path("tasks/<int:pk>/assign/", views.task_assign_view, name="task_assign"),
    path("tasks/<int:pk>/submit/", views.task_submit_view, name="task_submit"),
    path("tasks/<int:pk>/revision/", views.task_revision_view, name="task_revision"),
    path("tasks/<int:pk>/premium-sessions/request/", views.task_premium_session_request_view, name="task_premium_session_request"),
    path("tasks/<int:pk>/premium-sessions/<int:session_id>/accept/", views.task_premium_session_accept_view, name="task_premium_session_accept"),
    path("tasks/<int:pk>/premium-sessions/<int:session_id>/decline/", views.task_premium_session_decline_view, name="task_premium_session_decline"),
    path("tasks/<int:pk>/premium-sessions/<int:session_id>/pay/", views.task_premium_session_checkout_view, name="task_premium_session_checkout"),
    path("tasks/<int:pk>/premium-sessions/<int:session_id>/complete/", views.task_premium_session_complete_view, name="task_premium_session_complete"),
    path("tasks/<int:pk>/premium-sessions/<int:session_id>/finalize/", views.task_premium_session_finalize_view, name="task_premium_session_finalize"),
    path("tasks/<int:pk>/rate/", views.task_rate_view, name="task_rate"),
    path("webhooks/paystack/", webhooks.paystack_webhook_view, name="paystack_webhook"),
]
