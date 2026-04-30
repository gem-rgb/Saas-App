"""
Custom allauth adapter for role-based post-login redirects.
"""
from allauth.account.adapter import DefaultAccountAdapter
from marketplace.permissions import get_platform_role


class RoleBasedAccountAdapter(DefaultAccountAdapter):
    """
    Redirects users to role-appropriate pages after login:
    - admin/manager (staff) → /admin/ or /portal/
    - student/tasker → /portal/
    """

    def get_login_redirect_url(self, request):
        user = request.user
        role = get_platform_role(user)

        if role == "admin":
            return "/portal/"
        elif role == "manager":
            return "/portal/"
        elif role == "tasker":
            return "/portal/"
        else:
            # student (default)
            return "/portal/"

    def get_signup_redirect_url(self, request):
        """After signup, always go to the portal."""
        return "/portal/"
