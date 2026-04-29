from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.shortcuts import redirect

from marketplace.permissions import get_platform_role, has_role
from operations.models import EscalationCase, ManagerProfile, QualityAudit, Region, RegionalAssignment, TaskerPerformanceSnapshot


@login_required
def manager_dashboard_view(request):
    if not has_role(request.user, "manager", "admin"):
        messages.error(request, "You do not have access to the operations command center.")
        return redirect("dashboard:portal-home")

    manager_profile = getattr(request.user, "manager_profile", None)
    regions = manager_profile.regions.all() if manager_profile else Region.objects.filter(active=True)
    escalations = EscalationCase.objects.filter(region__in=regions).select_related("task", "assigned_manager", "region")[:12]
    audits = QualityAudit.objects.filter(task__region_preference__in=regions).select_related("task", "manager")[:12]
    tasker_snapshots = TaskerPerformanceSnapshot.objects.filter(region__in=regions).select_related("tasker", "region").order_by("-period_end")[:12]

    summary = {
        "regions": regions.count(),
        "escalations": escalations.count(),
        "open_escalations": escalations.filter(status=EscalationCase.Status.OPEN).count(),
        "tasks_under_review": audits.count(),
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
            "summary": summary,
            "portal_role": get_platform_role(request.user),
        },
    )


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


@login_required
def tasker_performance_view(request, tasker_id):
    from assignments.models import TaskerProfile

    tasker = get_object_or_404(TaskerProfile, pk=tasker_id)
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
