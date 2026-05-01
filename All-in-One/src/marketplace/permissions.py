from functools import wraps

from django.contrib.auth.decorators import user_passes_test

from auth.permissions import get_user_role, manager_portal_ready


ROLE_GROUPS = {
    "student": "Student",
    "tasker": "Tasker",
    "manager": "Manager",
    "admin": "Admin",
}


def get_platform_role(user):
    if not user or not user.is_authenticated:
        return "anonymous"

    user_role = get_user_role(user)
    if user_role:
        if user_role.role_type == "manager" and not manager_portal_ready(user):
            return "manager_pending"
        return user_role.role_type

    return "student"


def has_role(user, *roles):
    return get_platform_role(user) in roles


def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if has_role(request.user, *roles):
                return view_func(request, *args, **kwargs)
            raise PermissionError("You do not have access to this area.")

        return _wrapped

    return decorator


def auth_role_required(*roles):
    return user_passes_test(lambda user: has_role(user, *roles))


def can_receive_work(tasker):
    if tasker is None:
        return False
    return all(
        [
            getattr(tasker, "is_active_tasker", False),
            getattr(tasker, "approval_status", "") == "approved",
            getattr(tasker, "admin_approved", False),
            getattr(tasker, "kyc_status", "") == "approved",
            getattr(tasker, "competency_status", "") in {"verified", "approved"},
            getattr(tasker, "interview_status", "") in {"passed", "approved"},
            getattr(tasker, "competency_areas", None) is not None and tasker.competency_areas.exists(),
        ]
    )


def tasker_has_active_work(tasker):
    if tasker is None:
        return False

    from marketplace.models import TaskOrder

    active_statuses = {
        TaskOrder.Status.ASSIGNED,
        TaskOrder.Status.IN_PROGRESS,
        TaskOrder.Status.QUALITY_REVIEW,
        TaskOrder.Status.REVISION,
        TaskOrder.Status.ESCALATED,
    }
    return TaskOrder.objects.filter(assigned_tasker=tasker, status__in=active_statuses).exists()
