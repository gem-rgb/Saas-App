from functools import wraps

from django.contrib.auth.decorators import user_passes_test


ROLE_GROUPS = {
    "student": "Student",
    "tasker": "Tasker",
    "manager": "Manager",
    "admin": "Admin",
}


def get_platform_role(user):
    if not user or not user.is_authenticated:
        return "anonymous"
    if user.is_superuser or user.is_staff:
        return "admin"
    if hasattr(user, "manager_profile") and getattr(user.manager_profile, "active", True):
        return "manager"
    if hasattr(user, "tasker_profile"):
        profile = user.tasker_profile
        if getattr(profile, "admin_approved", False) and getattr(profile, "kyc_status", "") == "approved":
            return "tasker"
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
            getattr(tasker, "admin_approved", False),
            getattr(tasker, "kyc_status", "") == "approved",
            getattr(tasker, "competency_status", "") in {"verified", "approved"},
            getattr(tasker, "interview_status", "") in {"passed", "approved"},
        ]
    )

