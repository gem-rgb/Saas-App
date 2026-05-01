"""Role-based access control utilities and decorators."""

from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from auth.models import Permission, RolePermissionTemplate, UserRole


PUBLIC_ROLE_TYPES = (
    UserRole.RoleType.STUDENT,
    UserRole.RoleType.TASKER,
)


def social_provider_enabled(provider_name):
    providers = getattr(settings, "SOCIALACCOUNT_PROVIDERS", {})
    provider = providers.get(provider_name, {})
    app = provider.get("APP", {})
    if app.get("client_id") and app.get("secret"):
        return True

    try:
        from allauth.socialaccount.models import SocialApp
    except Exception:
        return False

    return SocialApp.objects.filter(provider=provider_name).exists()


def manager_portal_ready(user):
    """Return True when a manager has completed admin-vetted onboarding."""
    if not user or not user.is_authenticated:
        return False

    user_role = UserRole.objects.filter(user=user).first()
    if user_role is None:
        if getattr(user, "manager_profile", None) is not None or getattr(user, "manager_application", None) is not None:
            user_role = get_user_role(user)
        else:
            return False

    if user_role.role_type != UserRole.RoleType.MANAGER:
        return False

    manager_profile = getattr(user, "manager_profile", None)
    application = getattr(user, "manager_application", None)

    if application is not None:
        try:
            approved = application.status == application.Status.APPROVED
        except Exception:
            approved = False
        if not approved:
            return False
        if manager_profile is None:
            return True
        return bool(getattr(manager_profile, "active", False))

    return bool(manager_profile is not None and getattr(manager_profile, "active", False))


def _guess_role_type(user):
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return UserRole.RoleType.ADMIN
    if hasattr(user, "manager_profile"):
        return UserRole.RoleType.MANAGER
    if hasattr(user, "manager_application"):
        return UserRole.RoleType.MANAGER
    if hasattr(user, "tasker_profile"):
        return UserRole.RoleType.TASKER
    return UserRole.RoleType.STUDENT


def get_user_role(user):
    """Get the persisted role for a user, creating a sensible default when needed."""
    if not user or not user.is_authenticated:
        return None

    role = UserRole.objects.filter(user=user).first()
    if role:
        return role

    role_type = _guess_role_type(user)
    return UserRole.objects.create(
        user=user,
        role_type=role_type,
        verified=role_type == UserRole.RoleType.STUDENT,
    )


def has_role(user, role_type):
    """Check if user has a specific role."""
    user_role = get_user_role(user)
    if not user_role or user_role.role_type != role_type:
        return False
    if role_type == UserRole.RoleType.MANAGER:
        return manager_portal_ready(user)
    return True


def has_any_role(user, role_types):
    """Check if user has any of the specified roles."""
    return any(has_role(user, role_type) for role_type in role_types)


def is_student(user):
    return has_role(user, UserRole.RoleType.STUDENT)


def is_tasker(user):
    return has_role(user, UserRole.RoleType.TASKER)


def is_manager(user):
    return has_role(user, UserRole.RoleType.MANAGER)


def is_admin(user):
    return has_role(user, UserRole.RoleType.ADMIN)


def can_view_marketplace(user):
    """Taskers, managers, and admins can browse marketplace work."""
    if has_any_role(user, [UserRole.RoleType.MANAGER, UserRole.RoleType.ADMIN]):
        return True
    if not is_tasker(user):
        return False

    tasker_profile = getattr(user, "tasker_profile", None)
    if tasker_profile is None:
        return False

    from marketplace.permissions import can_receive_work

    return can_receive_work(tasker_profile)


def can_verify_assignments(user):
    return has_any_role(user, [UserRole.RoleType.MANAGER, UserRole.RoleType.ADMIN])


def can_upload_assignments(user):
    return has_any_role(
        user,
        [UserRole.RoleType.TASKER, UserRole.RoleType.MANAGER, UserRole.RoleType.ADMIN],
    )


def can_browse_chat(user):
    return bool(user and user.is_authenticated)


def portal_route_name_for_role(role_type):
    mapping = {
        UserRole.RoleType.STUDENT: "dashboard:student-dashboard",
        UserRole.RoleType.TASKER: "dashboard:tasker-dashboard",
        UserRole.RoleType.MANAGER: "operations:dashboard",
        UserRole.RoleType.ADMIN: "dashboard:admin-dashboard",
    }
    return mapping.get(role_type, "dashboard:portal-home")


def portal_url_for_role(role_type):
    return reverse(portal_route_name_for_role(role_type))


def portal_url_for_user(user):
    user_role = get_user_role(user)
    role_type = user_role.role_type if user_role else UserRole.RoleType.STUDENT
    if role_type == UserRole.RoleType.TASKER:
        tasker_profile = getattr(user, "tasker_profile", None)
        application = getattr(user, "tasker_application", None)
        if tasker_profile is None:
            return reverse("trust:onboarding")

        from marketplace.permissions import can_receive_work, tasker_has_active_work

        has_active_work = tasker_has_active_work(tasker_profile)
        if application is None or application.status != "approved":
            return portal_url_for_role(role_type) if has_active_work else reverse("trust:onboarding")

        if not can_receive_work(tasker_profile) and not has_active_work:
            return reverse("trust:onboarding")
    if role_type == UserRole.RoleType.MANAGER and not manager_portal_ready(user):
        return reverse("operations:manager-onboarding")
    return portal_url_for_role(role_type)


def _deny(request, message, fallback=None):
    messages.error(request, message)
    if not request.user.is_authenticated:
        return redirect("account_login")
    return redirect(fallback or portal_url_for_user(request.user))


def require_role(*allowed_roles):
    """Decorator to require specific role(s) for view access."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.error(request, "Please log in first.")
                return redirect("account_login")

            user_role = get_user_role(request.user)
            if not user_role or user_role.role_type not in allowed_roles:
                return _deny(request, "You don't have permission to access this page.")

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def require_any_role(*allowed_roles):
    """Decorator - allow access if user has ANY of the roles."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.error(request, "Please log in first.")
                return redirect("account_login")

            if not has_any_role(request.user, allowed_roles):
                return _deny(request, "You don't have permission to access this page.")

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def require_student(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, "Please log in first.")
            return redirect("account_login")
        if not is_student(request.user):
            return _deny(request, "This page is for students only.")
        return view_func(request, *args, **kwargs)

    return wrapper


def require_tasker(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, "Please log in first.")
            return redirect("account_login")
        if not is_tasker(request.user):
            return _deny(request, "This page is for taskers only.")
        return view_func(request, *args, **kwargs)

    return wrapper


def require_manager(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, "Please log in first.")
            return redirect("account_login")
        if not is_manager(request.user):
            return _deny(request, "This page is for managers only.")
        return view_func(request, *args, **kwargs)

    return wrapper


def require_admin(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, "Please log in first.")
            return redirect("account_login")
        if not is_admin(request.user):
            return _deny(request, "Admin access required.")
        return view_func(request, *args, **kwargs)

    return wrapper


def require_marketplace_access(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not can_view_marketplace(request.user):
            return _deny(request, "You don't have marketplace access.")
        return view_func(request, *args, **kwargs)

    return wrapper


def require_verification_access(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not can_verify_assignments(request.user):
            return _deny(request, "You don't have permission to verify assignments.")
        return view_func(request, *args, **kwargs)

    return wrapper


def api_require_role(*allowed_roles):
    """Decorator for API views - require specific role(s)."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse({"error": "Not authenticated"}, status=401)

            user_role = get_user_role(request.user)
            if not user_role or user_role.role_type not in allowed_roles:
                return JsonResponse({"error": "Insufficient permissions"}, status=403)

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def api_require_any_role(*allowed_roles):
    """Decorator for API views - allow if user has ANY of the roles."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse({"error": "Not authenticated"}, status=401)

            if not has_any_role(request.user, allowed_roles):
                return JsonResponse({"error": "Insufficient permissions"}, status=403)

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def get_role_context(user):
    """Get user role context for templates."""
    user_role = get_user_role(user)
    if not user_role:
        return {
            "portal_role": None,
            "role_display": None,
            "portal_dashboard_url": reverse("dashboard:portal-home"),
            "tasker_onboarding_url": reverse("trust:onboarding"),
            "manager_onboarding_url": reverse("operations:manager-onboarding"),
            "staff_login_url": reverse("staff_login"),
            "tasker_portal_ready": False,
            "manager_portal_ready": False,
            "is_student": False,
            "is_tasker": False,
            "is_manager": False,
            "is_admin": False,
            "can_view_marketplace": False,
            "can_verify_assignments": False,
            "can_browse_chat": False,
            "can_upload_assignments": False,
        }

    role_type = user_role.role_type
    tasker_profile = getattr(user, "tasker_profile", None)
    tasker_application = getattr(user, "tasker_application", None)
    tasker_portal_ready = False
    if role_type == UserRole.RoleType.TASKER and tasker_profile is not None and tasker_application is not None:
        from marketplace.permissions import can_receive_work

        tasker_portal_ready = tasker_application.status == "approved" and can_receive_work(tasker_profile)

    manager_portal_ready_value = manager_portal_ready(user)

    return {
        "portal_role": role_type,
        "role_display": user_role.get_role_type_display(),
        "portal_dashboard_url": portal_url_for_user(user),
        "tasker_onboarding_url": reverse("trust:onboarding"),
        "manager_onboarding_url": reverse("operations:manager-onboarding"),
        "staff_login_url": reverse("staff_login"),
        "tasker_portal_ready": tasker_portal_ready,
        "manager_portal_ready": manager_portal_ready_value,
        "is_student": role_type == UserRole.RoleType.STUDENT,
        "is_tasker": role_type == UserRole.RoleType.TASKER,
        "is_manager": manager_portal_ready_value,
        "is_admin": role_type == UserRole.RoleType.ADMIN,
        "can_view_marketplace": can_view_marketplace(user),
        "can_verify_assignments": can_verify_assignments(user),
        "can_browse_chat": True,
        "can_upload_assignments": can_upload_assignments(user),
    }


def _get_or_update_permission(code, name, category):
    permission, created = Permission.objects.get_or_create(
        code=code,
        defaults={"name": name, "category": category},
    )
    if not created and (permission.name != name or permission.category != category):
        permission.name = name
        permission.category = category
        permission.save(update_fields=["name", "category"])
    return permission


def setup_default_permissions():
    """Initialize default permissions for each role."""
    from django.db import transaction

    permissions_data = {
        UserRole.RoleType.STUDENT: [
            ("view_student_dashboard", "View Student Dashboard", Permission.PermissionCategory.DASHBOARD),
            ("submit_assignments", "Submit Assignments", Permission.PermissionCategory.ASSIGNMENTS),
            ("view_own_submissions", "View Own Submissions", Permission.PermissionCategory.ASSIGNMENTS),
            ("browse_chat", "Access Chat", Permission.PermissionCategory.CHAT),
        ],
        UserRole.RoleType.TASKER: [
            ("view_tasker_dashboard", "View Tasker Dashboard", Permission.PermissionCategory.DASHBOARD),
            ("browse_marketplace", "Browse Assignment Marketplace", Permission.PermissionCategory.MARKETPLACE),
            ("upload_assignments", "Upload Assignment Solutions", Permission.PermissionCategory.ASSIGNMENTS),
            ("chat_with_students", "Chat with Students", Permission.PermissionCategory.CHAT),
            ("view_tasker_profile", "View Tasker Profile", Permission.PermissionCategory.DASHBOARD),
            ("view_own_submissions", "View Own Submissions", Permission.PermissionCategory.ASSIGNMENTS),
            ("accept_tasks", "Accept Tasks", Permission.PermissionCategory.MARKETPLACE),
        ],
        UserRole.RoleType.MANAGER: [
            ("view_manager_dashboard", "View Manager Dashboard", Permission.PermissionCategory.DASHBOARD),
            ("verify_assignments", "Verify Assignments", Permission.PermissionCategory.VERIFICATION),
            ("browse_marketplace", "Browse All Assignments", Permission.PermissionCategory.MARKETPLACE),
            ("moderate_content", "Moderate Platform Content", Permission.PermissionCategory.MODERATION),
            ("view_user_profiles", "View User Profiles", Permission.PermissionCategory.DASHBOARD),
            ("manage_taskers", "Manage Taskers", Permission.PermissionCategory.MODERATION),
            ("view_reports", "View Analytics/Reports", Permission.PermissionCategory.DASHBOARD),
        ],
        UserRole.RoleType.ADMIN: [
            ("view_admin_panel", "Access Admin Panel", Permission.PermissionCategory.ADMIN),
            ("manage_all_users", "Manage All Users", Permission.PermissionCategory.ADMIN),
            ("manage_permissions", "Manage Permissions", Permission.PermissionCategory.ADMIN),
            ("verify_assignments", "Verify Assignments", Permission.PermissionCategory.VERIFICATION),
            ("moderate_content", "Moderate Content", Permission.PermissionCategory.MODERATION),
            ("view_system_reports", "View System Reports", Permission.PermissionCategory.ADMIN),
            ("manage_roles", "Manage Roles", Permission.PermissionCategory.ADMIN),
        ],
    }

    with transaction.atomic():
        for role_type, perms in permissions_data.items():
            template, _ = RolePermissionTemplate.objects.get_or_create(role_type=role_type)
            permission_objects = []
            for perm_code, perm_name, category in perms:
                permission_objects.append(
                    _get_or_update_permission(perm_code, perm_name, category)
                )
            template.permissions.set(permission_objects)
