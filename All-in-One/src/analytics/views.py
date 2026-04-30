from django.contrib.auth.decorators import login_required
from django.db.models import Avg
from django.shortcuts import render

from marketplace.models import TaskOrder
from marketplace.permissions import can_receive_work, get_platform_role
from marketplace.services import recommend_taskers_for_subject
from operations.models import EscalationCase
from subscriptions.utils import subscription_has_feature

from .models import UserActivity


def _has_analytics_access(user):
    role = get_platform_role(user)
    return role in {"manager", "admin"} or subscription_has_feature(user, "analytics_dashboard")


def _tasks_for_role(user):
    role = get_platform_role(user)
    if role == "student":
        return TaskOrder.objects.filter(student=user)
    if role == "tasker":
        tasker = getattr(user, "tasker_profile", None)
        if tasker is None or not can_receive_work(tasker):
            return TaskOrder.objects.none()
        return TaskOrder.objects.filter(assigned_tasker=tasker)
    if role == "manager":
        return TaskOrder.objects.filter(
            status__in=[
                TaskOrder.Status.OPEN,
                TaskOrder.Status.ASSIGNED,
                TaskOrder.Status.IN_PROGRESS,
                TaskOrder.Status.QUALITY_REVIEW,
                TaskOrder.Status.REVISION,
                TaskOrder.Status.ESCALATED,
            ]
        )
    return TaskOrder.objects.all()


@login_required
def analytics_dashboard_view(request):
    """Assignment insights dashboard with subscription gating."""
    if not _has_analytics_access(request.user):
        return render(
            request,
            "analytics/dashboard.html",
            {
                "locked": True,
                "upgrade_url": "/pricing/",
            },
        )

    tasks = _tasks_for_role(request.user).select_related("student", "assigned_tasker", "category")
    summary = {
        "total_assignments": tasks.count(),
        "open_assignments": tasks.filter(status__in=[TaskOrder.Status.DRAFT, TaskOrder.Status.OPEN]).count(),
        "active_assignments": tasks.filter(status__in=[TaskOrder.Status.ASSIGNED, TaskOrder.Status.IN_PROGRESS, TaskOrder.Status.QUALITY_REVIEW, TaskOrder.Status.REVISION]).count(),
        "completed_assignments": tasks.filter(status=TaskOrder.Status.COMPLETED).count(),
        "disputes": EscalationCase.objects.filter(task__in=tasks).count(),
    }
    average_rating = tasks.aggregate(avg=Avg("ratings__overall_rating"))["avg"] or 0.0
    average_accuracy = tasks.aggregate(avg=Avg("ratings__accuracy_rating"))["avg"] or 0.0
    assignment_health = max(
        0,
        min(
            100,
            round((summary["completed_assignments"] * 12) + (average_rating * 12) + (average_accuracy * 8) - (summary["disputes"] * 6)),
        ),
    )

    focus_task = tasks.first()
    recommended_taskers = []
    if focus_task is not None:
        recommended_taskers = recommend_taskers_for_subject(focus_task.subject)[:5]

    context = {
        "locked": False,
        "summary": summary,
        "assignment_health": assignment_health,
        "average_rating": average_rating,
        "average_accuracy": average_accuracy,
        "recent_tasks": tasks.order_by("-updated_at")[:8],
        "recent_disputes": EscalationCase.objects.filter(task__in=tasks).select_related("task", "region").order_by("-opened_at")[:6],
        "recommended_taskers": recommended_taskers,
        "portal_role": get_platform_role(request.user),
        "focus_subject": focus_task.subject if focus_task else "Academic writing",
    }
    return render(request, "analytics/dashboard.html", context)


def track_activity(user, action, path="", metadata=None):
    """Utility to track user activity from anywhere in the app."""
    if user.is_authenticated:
        UserActivity.objects.create(
            user=user,
            action=action,
            path=path,
            metadata=metadata or {},
        )
