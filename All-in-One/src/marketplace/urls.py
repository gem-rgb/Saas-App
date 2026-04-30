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
    path("tasks/<int:pk>/rate/", views.task_rate_view, name="task_rate"),
    path("webhooks/paystack/", webhooks.paystack_webhook_view, name="paystack_webhook"),
]
