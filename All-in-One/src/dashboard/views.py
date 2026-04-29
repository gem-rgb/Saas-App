import datetime

from django.contrib.auth.decorators import login_required
from django.db import models
from django.shortcuts import render
from django.utils import timezone

from analytics import ml_engine
from analytics.models import UserActivity
from marketplace.models import TaskMatchSuggestion, TaskNotification, TaskOrder
from marketplace.permissions import can_receive_work, get_platform_role
from operations.models import EscalationCase, Region, TaskerPerformanceSnapshot
from subscriptions.models import UserSubscription
from trust.models import AIInterviewSession, IdentityVerification, TaskerApplication
from visits.models import PageVisit


def _tasker_profile(user):
    return getattr(user, "tasker_profile", None)


def _manager_profile(user):
    return getattr(user, "manager_profile", None)


def _tasker_gate(application):
    if application is None:
        return False
    return {
        "application_status": application.status,
        "trust_score": application.trust_score,
        "manual_review_required": application.manual_review_required,
        "is_ready": application.status == TaskerApplication.Status.APPROVED,
    }


def _collect_common_context(request):
    user = request.user
    now = timezone.now()
    portal_role = get_platform_role(user)

    UserActivity.objects.create(
        user=user,
        action=UserActivity.ActionChoices.PAGE_VIEW,
        path=request.path,
        metadata={"page": "portal", "role": portal_role},
    )

    sub_info = {
        "plan_name": "Free",
        "status": "No Plan",
        "is_active": False,
        "days_remaining": 0,
        "period_end": None,
        "period_start": None,
        "membership_age": None,
    }
    try:
        user_sub = UserSubscription.objects.get(user=user)
        sub_info["plan_name"] = user_sub.plan_name or "Free"
        sub_info["status"] = user_sub.status or "No Plan"
        sub_info["is_active"] = user_sub.is_active_status
        sub_info["period_end"] = user_sub.current_period_end
        sub_info["period_start"] = user_sub.current_period_start
        if user_sub.current_period_end:
            sub_info["days_remaining"] = max(0, (user_sub.current_period_end - now).days)
        if user_sub.original_period_start:
            sub_info["membership_age"] = (now - user_sub.original_period_start).days
    except UserSubscription.DoesNotExist:
        pass

    analytics = {}
    try:
        analytics = ml_engine.analyze_user(user)
    except Exception:
        analytics = {
            "health_score": 50,
            "health_color": "yellow",
            "churn_probability": 30,
            "churn_risk_level": "low",
            "usage_forecast": 0,
            "recommendations": [],
        }

    recent_activities = UserActivity.objects.filter(user=user).order_by("-timestamp")[:8]
    total_visits = PageVisit.objects.count()
    recent_visits = PageVisit.objects.filter(timestamp__gte=now - datetime.timedelta(days=7)).count()

    usage_chart = []
    for i in range(6, -1, -1):
        day = now - datetime.timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999)
        count = UserActivity.objects.filter(user=user, timestamp__gte=day_start, timestamp__lte=day_end).count()
        usage_chart.append(
            {
                "day": day.strftime("%a"),
                "count": count,
                "height": max(8, min(count * 15, 100)),
            }
        )

    return {
        "portal_role": portal_role,
        "sub_info": sub_info,
        "analytics": analytics,
        "recent_activities": recent_activities,
        "total_visits": total_visits,
        "recent_visits": recent_visits,
        "usage_chart": usage_chart,
        "is_tasker_gate_open": can_receive_work(_tasker_profile(user)),
        "tasker_gate": _tasker_gate(getattr(user, "tasker_application", None)),
        "tasker_profile": _tasker_profile(user),
        "manager_profile": _manager_profile(user),
        "notifications": TaskNotification.objects.filter(recipient=user).select_related("task")[:6],
    }


def _student_context(request):
    tasks = TaskOrder.objects.filter(student=request.user).select_related(
        "category",
        "competency_area",
        "assigned_tasker",
    ).prefetch_related("match_suggestions", "submissions")
    open_count = tasks.filter(status__in=[TaskOrder.Status.DRAFT, TaskOrder.Status.OPEN]).count()
    active_count = tasks.filter(status__in=[TaskOrder.Status.ASSIGNED, TaskOrder.Status.IN_PROGRESS, TaskOrder.Status.QUALITY_REVIEW, TaskOrder.Status.REVISION]).count()
    completed_count = tasks.filter(status=TaskOrder.Status.COMPLETED).count()
    spend_total = tasks.filter(status=TaskOrder.Status.COMPLETED).aggregate(total=models.Sum("budget_cents"))["total"] or 0
    match_suggestions = TaskMatchSuggestion.objects.filter(task__student=request.user).select_related("task", "tasker__user").order_by("-score")[:6]
    return {
        "student_tasks": tasks.order_by("-created_at")[:8],
        "student_summary": {
            "open": open_count,
            "active": active_count,
            "completed": completed_count,
            "spend_total": spend_total,
        },
        "student_suggestions": match_suggestions,
    }


def _tasker_context(request):
    tasker = _tasker_profile(request.user)
    if not tasker:
        return {
            "tasker_tasks": [],
            "tasker_suggestions": [],
            "tasker_snapshots": [],
            "tasker_readiness": 0,
        }
    tasks = TaskOrder.objects.filter(assigned_tasker=tasker).select_related("student", "category", "region_preference").order_by("-created_at")
    suggestions = TaskMatchSuggestion.objects.filter(tasker=tasker).select_related("task", "task__student").order_by("-score")[:6]
    snapshots = TaskerPerformanceSnapshot.objects.filter(tasker=tasker).select_related("region").order_by("-period_end")[:6]
    readiness = tasker.trust_score
    return {
        "tasker_tasks": tasks[:8],
        "tasker_suggestions": suggestions,
        "tasker_snapshots": snapshots,
        "tasker_readiness": readiness,
    }


def _manager_context(request):
    manager = _manager_profile(request.user)
    if not manager:
        regions = Region.objects.none()
        escalations = EscalationCase.objects.none()
        snapshots = TaskerPerformanceSnapshot.objects.none()
        tasks = TaskOrder.objects.none()
    else:
        regions = manager.regions.filter(active=True)
        escalations = EscalationCase.objects.filter(region__in=regions).select_related("task", "assigned_manager", "region").order_by("-opened_at")[:8]
        snapshots = TaskerPerformanceSnapshot.objects.filter(region__in=regions).select_related("tasker", "region").order_by("-period_end")[:8]
        tasks = TaskOrder.objects.filter(region_preference__in=regions).select_related("student", "assigned_tasker", "category", "region_preference").order_by("-created_at")[:8]
    return {
        "manager_regions": regions,
        "manager_escalations": escalations,
        "manager_snapshots": snapshots,
        "manager_tasks": tasks,
    }


def _admin_context():
    pending_applications = TaskerApplication.objects.filter(
        status__in=[
            TaskerApplication.Status.SUBMITTED,
            TaskerApplication.Status.DOCUMENT_REVIEW,
            TaskerApplication.Status.INTERVIEW_PENDING,
            TaskerApplication.Status.UNDER_REVIEW,
        ]
    ).select_related("applicant", "region_preference")
    open_tasks = TaskOrder.objects.filter(status__in=[TaskOrder.Status.OPEN, TaskOrder.Status.ASSIGNED, TaskOrder.Status.IN_PROGRESS, TaskOrder.Status.QUALITY_REVIEW, TaskOrder.Status.REVISION])
    escalations = EscalationCase.objects.select_related("task", "region", "assigned_manager").order_by("-opened_at")[:8]
    snapshots = TaskerPerformanceSnapshot.objects.select_related("tasker", "region").order_by("-period_end")[:8]
    return {
        "admin_applications": pending_applications[:8],
        "admin_open_tasks": open_tasks[:8],
        "admin_open_count": open_tasks.count(),
        "admin_escalations": escalations,
        "admin_snapshots": snapshots,
        "admin_completion_count": TaskOrder.objects.filter(status=TaskOrder.Status.COMPLETED).count(),
        "admin_revenue_total": TaskOrder.objects.filter(status=TaskOrder.Status.COMPLETED).aggregate(total=models.Sum("budget_cents"))["total"] or 0,
    }


def _dashboard_context(request, forced_role=None):
    context = _collect_common_context(request)
    role = forced_role or context["portal_role"]
    context["portal_role"] = role
    context["portal_label"] = {
        "student": "Student Portal",
        "tasker": "Tasker Portal",
        "manager": "Manager Portal",
        "admin": "Admin Command Center",
    }.get(role, "Marketplace Portal")
    context["portal_tagline"] = {
        "student": "Create, track, and manage academic tasks.",
        "tasker": "Track your trust gate, queues, and performance.",
        "manager": "Oversee regional operations and escalations.",
        "admin": "Monitor the entire marketplace from one control surface.",
    }.get(role, "Marketplace overview.")

    if role == "student":
        context.update(_student_context(request))
    elif role == "tasker":
        context.update(_tasker_context(request))
    elif role == "manager":
        context.update(_manager_context(request))
    else:
        context.update(_admin_context())

    return context


@login_required
def dashboard_view(request):
    return render(request, "dashboard/main.html", _dashboard_context(request))


@login_required
def student_dashboard_view(request):
    return render(request, "dashboard/main.html", _dashboard_context(request, "student"))


@login_required
def tasker_dashboard_view(request):
    return render(request, "dashboard/main.html", _dashboard_context(request, "tasker"))


@login_required
def manager_dashboard_view(request):
    return render(request, "dashboard/main.html", _dashboard_context(request, "manager"))


@login_required
def admin_dashboard_view(request):
    return render(request, "dashboard/main.html", _dashboard_context(request, "admin"))
