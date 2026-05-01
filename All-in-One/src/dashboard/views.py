from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Sum
from django.shortcuts import redirect, render
from django.utils import timezone

from auth.permissions import portal_url_for_user, require_admin, require_student, require_tasker
from marketplace.models import TaskNotification, TaskOrder
from marketplace.permissions import can_receive_work, get_platform_role, tasker_has_active_work
from marketplace.services import recommend_task_rows_for_tasker, recommend_taskers_for_subject
from assignments.models import TaskerProfile
from operations.models import EscalationCase, ManagerApplication, Region
from subscriptions.models import UserSubscription
from subscriptions import utils as subs_utils
from trust.models import TaskerApplication


def _tasker_profile(user):
    return getattr(user, "tasker_profile", None)


def _manager_profile(user):
    return getattr(user, "manager_profile", None)


def _subscription_snapshot(user):
    snapshot = {
        "plan_name": "Free",
        "status": "inactive",
        "is_active": False,
        "days_remaining": 0,
        "period_start": None,
        "period_end": None,
        "feature_codes": [],
        "active_task_limit": None,
        "turnaround_hours": None,
        "support_channel": "email",
        "analytics_tier": 0,
        "matching_mode": "standard",
        "matching_mode_label": "Standard matching",
        "session_mode": "standard",
        "session_mode_label": "Standard access",
    }
    user_sub = UserSubscription.objects.select_related("subscription").filter(user=user).first()
    if not user_sub:
        return snapshot

    snapshot["plan_name"] = user_sub.plan_name or "Free"
    snapshot["status"] = user_sub.status or "inactive"
    snapshot["is_active"] = user_sub.is_active_status
    snapshot["period_start"] = user_sub.current_period_start
    snapshot["period_end"] = user_sub.current_period_end
    if user_sub.current_period_end:
        snapshot["days_remaining"] = max(0, (user_sub.current_period_end - timezone.now()).days)
    if user_sub.subscription:
        snapshot["feature_codes"] = user_sub.subscription.get_feature_codes()
        snapshot["active_task_limit"] = subs_utils.subscription_active_task_limit(user)
        snapshot["turnaround_hours"] = subs_utils.subscription_turnaround_hours(user)
        snapshot["support_channel"] = subs_utils.subscription_support_channel(user)
        snapshot["analytics_tier"] = subs_utils.subscription_analytics_access_level(user)
        snapshot["matching_mode"] = subs_utils.subscription_matching_mode(user)
        snapshot["matching_mode_label"] = {
            "priority": "Priority matching",
            "standard": "Standard matching",
        }.get(snapshot["matching_mode"], snapshot["matching_mode"].replace("_", " ").title())
        snapshot["session_mode"] = subs_utils.subscription_session_mode(user)
        snapshot["session_mode_label"] = {
            "premium": "Premium sessions",
            "standard": "Standard access",
        }.get(snapshot["session_mode"], snapshot["session_mode"].replace("_", " ").title())
    return snapshot


def _common_context(request):
    user = request.user
    portal_role = get_platform_role(user)
    tasker_profile = _tasker_profile(user)
    tasker_application = getattr(user, "tasker_application", None)
    manager_profile = _manager_profile(user)

    return {
        "portal_role": portal_role,
        "sub_info": _subscription_snapshot(user),
        "notifications": TaskNotification.objects.filter(recipient=user).select_related("task")[:6],
        "tasker_profile": tasker_profile,
        "manager_profile": manager_profile,
        "tasker_gate": {
            "application_status": tasker_application.status,
            "trust_score": tasker_application.trust_score,
            "manual_review_required": tasker_application.manual_review_required,
            "is_ready": tasker_application.status == TaskerApplication.Status.APPROVED,
        }
        if tasker_application
        else None,
        "tasker_portal_ready": bool(tasker_profile and can_receive_work(tasker_profile)),
    }


def _student_context(request):
    tasks = (
        TaskOrder.objects.filter(student=request.user)
        .select_related("category", "competency_area", "assigned_tasker", "region_preference")
        .prefetch_related("submissions", "match_suggestions")
        .order_by("-created_at")
    )
    focus_task = tasks.first()
    focus_subject = request.GET.get("subject", "").strip() or (focus_task.subject if focus_task else "")
    if not focus_subject:
        focus_subject = "Academic writing"

    active_statuses = [
        TaskOrder.Status.DRAFT,
        TaskOrder.Status.OPEN,
        TaskOrder.Status.ASSIGNED,
        TaskOrder.Status.IN_PROGRESS,
        TaskOrder.Status.QUALITY_REVIEW,
        TaskOrder.Status.REVISION,
        TaskOrder.Status.ESCALATED,
    ]
    summary = {
        "total_tasks": tasks.count(),
        "open_tasks": tasks.filter(status__in=[TaskOrder.Status.DRAFT, TaskOrder.Status.OPEN]).count(),
        "active_tasks": tasks.filter(status__in=active_statuses[2:]).count(),
        "completed_tasks": tasks.filter(status=TaskOrder.Status.COMPLETED).count(),
        "flagged_tasks": tasks.filter(status=TaskOrder.Status.ESCALATED).count(),
    }

    return {
        "student_tasks": tasks[:8],
        "student_summary": summary,
        "student_subject_focus": focus_subject,
        "student_recommended_taskers": recommend_taskers_for_subject(
            focus_subject,
            matching_mode=subs_utils.subscription_matching_mode(request.user),
        ),
    }


def _tasker_context(request):
    tasker = _tasker_profile(request.user)
    if not tasker:
        return {
            "tasker_tasks": [],
            "tasker_recommendation_rows": [],
            "tasker_competencies": [],
            "tasker_summary": {},
            "tasker_portal_ready": False,
        }

    tasks = (
        TaskOrder.objects.filter(assigned_tasker=tasker)
        .select_related("student", "category", "region_preference")
        .order_by("-created_at")
    )
    metrics = {
        "trust_score": tasker.trust_score,
        "quality_score": tasker.quality_score,
        "completed_assignments": tasker.completed_assignments,
        "on_time_delivery_rate": tasker.on_time_delivery_rate,
        "current_workload_hours": tasker.current_workload_hours,
    }
    return {
        "tasker_tasks": tasks[:8],
        "tasker_recommendation_rows": recommend_task_rows_for_tasker(tasker) if can_receive_work(tasker) else [],
        "tasker_competencies": tasker.competency_areas.all(),
        "tasker_summary": metrics,
        "tasker_portal_ready": can_receive_work(tasker),
    }


def _manager_context(request):
    manager = _manager_profile(request.user)
    regions = manager.regions.filter(active=True) if manager else Region.objects.filter(active=True)
    if manager and not regions.exists():
        regions = Region.objects.filter(active=True)

    escalation_qs = EscalationCase.objects.filter(region__in=regions)
    escalations = (
        escalation_qs
        .select_related("task", "assigned_manager", "region", "opened_by")
        .order_by("-opened_at")[:8]
    )

    low_accuracy_qs = TaskerProfile.objects.filter(ratings__isnull=False)
    low_accuracy_taskers = (
        low_accuracy_qs
        .annotate(
            avg_accuracy=Avg("ratings__accuracy_rating"),
            avg_overall=Avg("ratings__overall_rating"),
            rating_count=Count("ratings"),
        )
        .filter(avg_accuracy__lt=3.0)
        .select_related("user", "home_region")
        .prefetch_related("competency_areas")
        .order_by("avg_accuracy", "user__username")[:8]
    )

    summary = {
        "regions": regions.count(),
        "escalations": escalation_qs.count(),
        "open_escalations": escalation_qs.filter(status=EscalationCase.Status.OPEN).count(),
        "flagged_taskers": low_accuracy_qs.annotate(avg_accuracy=Avg("ratings__accuracy_rating")).filter(avg_accuracy__lt=3.0).count(),
    }

    return {
        "manager_regions": regions,
        "manager_escalations": escalations,
        "manager_low_accuracy_taskers": low_accuracy_taskers,
        "manager_summary": summary,
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
    pending_manager_applications = ManagerApplication.objects.filter(
        status__in=[
            ManagerApplication.Status.SUBMITTED,
            ManagerApplication.Status.UNDER_REVIEW,
            ManagerApplication.Status.NEEDS_INFO,
        ]
    ).select_related("user", "reviewed_by").prefetch_related("regions")

    open_tasks = TaskOrder.objects.filter(
        status__in=[
            TaskOrder.Status.OPEN,
            TaskOrder.Status.ASSIGNED,
            TaskOrder.Status.IN_PROGRESS,
            TaskOrder.Status.QUALITY_REVIEW,
            TaskOrder.Status.REVISION,
            TaskOrder.Status.ESCALATED,
        ]
    )

    return {
        "admin_applications": pending_applications[:8],
        "admin_application_count": pending_applications.count(),
        "admin_manager_applications": pending_manager_applications[:8],
        "admin_manager_application_count": pending_manager_applications.count(),
        "admin_open_tasks": open_tasks[:8],
        "admin_open_count": open_tasks.count(),
        "admin_completion_count": TaskOrder.objects.filter(status=TaskOrder.Status.COMPLETED).count(),
        "admin_low_accuracy_taskers": (
            TaskerProfile.objects.filter(ratings__isnull=False)
            .annotate(avg_accuracy=Avg("ratings__accuracy_rating"), avg_overall=Avg("ratings__overall_rating"), rating_count=Count("ratings"))
            .filter(avg_accuracy__lt=3.0)
            .select_related("user")
            .order_by("avg_accuracy")[:8]
        ),
    }


def _dashboard_context(request, forced_role=None):
    context = _common_context(request)
    role = forced_role or context["portal_role"]
    context["portal_role"] = role
    context["portal_label"] = {
        "student": "Student Portal",
        "tasker": "Tasker Portal",
        "manager": "Manager Portal",
        "admin": "Admin Command Center",
    }.get(role, "Assignment Portal")
    context["portal_tagline"] = {
        "student": "Create assignments and view the best writers for each subject.",
        "tasker": "Track your queue, quality, and assigned assignments.",
        "manager": "Resolve disputes, review taskers, and manage quality issues.",
        "admin": "Review taskers and manager applications from one control surface.",
    }.get(role, "Assignment workflow")

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
    return redirect(portal_url_for_user(request.user))


@require_student
@login_required
def student_dashboard_view(request):
    return render(request, "dashboard/main.html", _dashboard_context(request, "student"))


@require_tasker
@login_required
def tasker_dashboard_view(request):
    tasker = _tasker_profile(request.user)
    if not can_receive_work(tasker) and not tasker_has_active_work(tasker):
        return redirect("trust:onboarding")
    return render(request, "dashboard/main.html", _dashboard_context(request, "tasker"))


@login_required
def manager_dashboard_view(request):
    return redirect(portal_url_for_user(request.user))


@require_admin
@login_required
def admin_dashboard_view(request):
    return render(request, "dashboard/main.html", _dashboard_context(request, "admin"))
