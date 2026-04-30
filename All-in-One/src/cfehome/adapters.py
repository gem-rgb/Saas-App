"""
Custom allauth adapter for role-based post-login redirects.
"""
from allauth.account.adapter import DefaultAccountAdapter
from auth.permissions import portal_url_for_user


class RoleBasedAccountAdapter(DefaultAccountAdapter):
    """
    Redirects users to role-appropriate pages after login and signup.
    """

    def get_login_redirect_url(self, request):
        return portal_url_for_user(request.user)

    def get_signup_redirect_url(self, request):
        return portal_url_for_user(request.user)
