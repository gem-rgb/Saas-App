from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count
from django.shortcuts import get_object_or_404, render
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from auth.models import UserRole
from auth.permissions import require_any_role
from assignments.models import TaskerProfile
from marketplace.models import TaskAuditEvent, TaskOrder, TaskPayment
from marketplace.permissions import get_platform_role
from marketplace.services import queue_notification
from operations.models import EscalationCase, ManagerProfile, QualityAudit, Region, RegionalAssignment, TaskerPerformanceSnapshot


@require_any_role(UserRole.RoleType.MANAGER, UserRole.RoleType.ADMIN)
@login_required
def manager_dashboard_view(request):
    manager_profile = getattr(request.user, "manager_profile", None)
    regions = manager_profile.regions.filter(active=True) if manager_profile else Region.objects.filter(active=True)
    if manager_profile and not regions.exists():
        regions = Region.objects.filter(active=True)
    escalations = EscalationCase.objects.filter(region__in=regions).select_related("task", "assigned_manager", "region")[:12]
    audits = QualityAudit.objects.filter(task__region_preference__in=regions).select_related("task", "manager")[:12]
    tasker_snapshots = TaskerPerformanceSnapshot.objects.filter(region__in=regions).select_related("tasker", "region").order_by("-period_end")[:12]
    low_accuracy_taskers = (
        TaskerProfile.objects.filter(ratings__isnull=False)
        .annotate(
            avg_accuracy=Avg("ratings__accuracy_rating"),
            avg_overall=Avg("ratings__overall_rating"),
            rating_count=Count("ratings"),
        )
        .filter(avg_accuracy__lt=3.0)
        .select_related("user", "home_region")
        .order_by("avg_accuracy", "user__username")[:12]
    )

    summary = {
        "regions": regions.count(),
        "escalations": escalations.count(),
        "open_escalations": escalations.filter(status=EscalationCase.Status.OPEN).count(),
        "tasks_under_review": audits.count(),
        "flagged_taskers": low_accuracy_taskers.count(),
    }
    return render(
        request,
        "operations/dashboard.html",
        {
            "manager_profile": manager_profile,
            "regions": regions,
            "escalations": escalations,
            "audits": audits,
            "tasker_snapshots": tasker_snapshots,
            "low_accuracy_taskers": low_accuracy_taskers,
            "summary": summary,
            "portal_role": get_platform_role(request.user),
        },
    )


@require_any_role(UserRole.RoleType.MANAGER, UserRole.RoleType.ADMIN)
@login_required
def region_dashboard_view(request, code):
    region = get_object_or_404(Region, code=code)
    assignments = RegionalAssignment.objects.filter(region=region, active=True).select_related("tasker", "manager", "region")
    snapshots = TaskerPerformanceSnapshot.objects.filter(region=region).select_related("tasker").order_by("-period_end")[:12]
    escalations = EscalationCase.objects.filter(region=region).select_related("task", "assigned_manager")
    return render(
        request,
        "operations/region_dashboard.html",
        {
            "region": region,
            "assignments": assignments,
            "snapshots": snapshots,
            "escalations": escalations,
        },
    )


@require_any_role(UserRole.RoleType.MANAGER, UserRole.RoleType.ADMIN)
@login_required
def tasker_performance_view(request, tasker_id):
    from assignments.models import TaskerProfile

    tasker = get_object_or_404(TaskerProfile, pk=tasker_id)
    if request.method == "POST":
        action = request.POST.get("action", "").strip()
        reason = request.POST.get("reason", "").strip()
        avg_accuracy = tasker.ratings.aggregate(avg_accuracy=Avg("accuracy_rating"))["avg_accuracy"] or 0.0
        audit_payload = {
            "tasker_id": tasker.id,
            "reason": reason,
            "avg_accuracy": round(avg_accuracy, 2),
        }
        if action == "warn":
            TaskAuditEvent.objects.create(
                actor=request.user,
                actor_role=get_platform_role(request.user),
                entity_type="tasker",
                entity_id=str(tasker.id),
                event_type="tasker_warning",
                payload=audit_payload,
            )
            queue_notification(
                tasker.user,
                "Performance warning",
                reason or "A manager issued a warning for recent task quality concerns.",
                metadata=audit_payload,
            )
            messages.success(request, "Warning recorded for the tasker.")
        elif action == "suspend":
            tasker.approval_status = TaskerProfile.ApprovalStatus.SUSPENDED
            tasker.is_active_tasker = False
            tasker.is_accepting_work = False
            tasker.save(update_fields=["approval_status", "is_active_tasker", "is_accepting_work", "updated_at"])
            TaskAuditEvent.objects.create(
                actor=request.user,
                actor_role=get_platform_role(request.user),
                entity_type="tasker",
                entity_id=str(tasker.id),
                event_type="tasker_suspended",
                payload=audit_payload,
            )
            queue_notification(
                tasker.user,
                "Account suspended",
                reason or "Your account has been suspended due to quality concerns.",
                metadata=audit_payload,
            )
            messages.warning(request, "Tasker account suspended.")
        elif action == "reinstate":
            tasker.approval_status = TaskerProfile.ApprovalStatus.APPROVED
            tasker.is_active_tasker = True
            tasker.is_accepting_work = True
            tasker.save(update_fields=["approval_status", "is_active_tasker", "is_accepting_work", "updated_at"])
            TaskAuditEvent.objects.create(
                actor=request.user,
                actor_role=get_platform_role(request.user),
                entity_type="tasker",
                entity_id=str(tasker.id),
                event_type="tasker_reinstated",
                payload=audit_payload,
            )
            queue_notification(
                tasker.user,
                "Account reinstated",
                reason or "Your account has been reinstated by a manager.",
                metadata=audit_payload,
            )
            messages.success(request, "Tasker account reinstated.")
        else:
            messages.error(request, "Select a valid moderation action.")
        return redirect("operations:tasker_performance", tasker_id=tasker_id)

    snapshots = TaskerPerformanceSnapshot.objects.filter(tasker=tasker).select_related("region").order_by("-period_end")[:12]
    audits = QualityAudit.objects.filter(task__assigned_tasker=tasker).select_related("manager").order_by("-created_at")[:12]
    return render(
        request,
        "operations/tasker_performance.html",
        {
            "tasker": tasker,
            "snapshots": snapshots,
            "audits": audits,
        },
    )


@require_any_role(UserRole.RoleType.MANAGER, UserRole.RoleType.ADMIN)
@login_required
@require_POST
def resolve_escalation_view(request, case_id):
    case = get_object_or_404(EscalationCase, pk=case_id)
    action = request.POST.get("action", "resolve").strip()
    resolution = request.POST.get("resolution", "").strip()
    refund_cents = request.POST.get("refund_cents", "").strip()

    task = case.task
    latest_payment = task.payments.order_by("-created_at").first()
    refund_amount = 0
    if refund_cents.isdigit():
        refund_amount = int(refund_cents)
    elif latest_payment is not None:
        refund_amount = latest_payment.amount_cents

    if action == "dismiss":
        case.status = EscalationCase.Status.DISMISSED
        case.resolution = resolution or "Dismissed by manager."
        case.resolved_at = timezone.now()
        case.save(update_fields=["status", "resolution", "resolved_at", "updated_at"])
        TaskAuditEvent.objects.create(
            actor=request.user,
            actor_role=get_platform_role(request.user),
            task=task,
            entity_type="escalation",
            entity_id=str(case.id),
            event_type="escalation_dismissed",
            payload={"resolution": case.resolution},
        )
        messages.success(request, "Escalation dismissed.")
        return redirect("operations:dashboard")

    case.status = EscalationCase.Status.RESOLVED
    case.resolution = resolution or "Resolved by manager."
    case.resolved_at = timezone.now()
    case.save(update_fields=["status", "resolution", "resolved_at", "updated_at"])

    if action == "refund" and latest_payment is not None:
        latest_payment.status = TaskPayment.Status.REFUNDED
        latest_payment.escrow_status = "refunded"
        latest_payment.refunded_at = timezone.now()
        latest_payment.save(update_fields=["status", "escrow_status", "refunded_at", "updated_at"])
        task.payment_status = TaskOrder.PaymentStatus.REFUNDED
        task.save(update_fields=["payment_status", "updated_at"])
        queue_notification(
            task.student,
            "Assignment refunded",
            resolution or "Your assignment was refunded after review.",
            task=task,
            metadata={"refund_amount_cents": refund_amount, "escalation_id": case.id},
        )
        if task.assigned_tasker:
            queue_notification(
                task.assigned_tasker.user,
                "Assignment refunded",
                resolution or "A manager refunded an assignment you worked on.",
                task=task,
                metadata={"refund_amount_cents": refund_amount, "escalation_id": case.id},
            )
        event_type = "escalation_refunded"
        payload = {"resolution": case.resolution, "refund_amount_cents": refund_amount}
        messages.warning(request, "Escalation resolved with a refund.")
    else:
        event_type = "escalation_resolved"
        payload = {"resolution": case.resolution}
        messages.success(request, "Escalation resolved.")

    TaskAuditEvent.objects.create(
        actor=request.user,
        actor_role=get_platform_role(request.user),
        task=task,
        entity_type="escalation",
        entity_id=str(case.id),
        event_type=event_type,
        payload=payload,
    )
    return redirect("operations:dashboard")
