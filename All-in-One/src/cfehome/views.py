"""
cfehome.views — root-level views for the SaaS platform.

Handles the home page, about page, services page, and
access-controlled views (password-protected, login-required, staff-only).
"""
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render


LOGIN_URL = settings.LOGIN_URL


# ────────────────────────────────────────────────────────────
#  Public pages
# ────────────────────────────────────────────────────────────

def home_view(request, *args, **kwargs):
    """Landing page — delegates to about_view."""
    return about_view(request, *args, **kwargs)


def about_view(request, *args, **kwargs):
    return render(request, "home.html", {"page_title": "My Page"})


def services_view(request, *args, **kwargs):
    return render(request, "services/main.html", {})


# ────────────────────────────────────────────────────────────
#  Access-controlled pages
# ────────────────────────────────────────────────────────────

VALID_CODE = "abc123"


def pw_protected_view(request, *args, **kwargs):
    """Simple code-gated page — enter the code once per session."""
    is_allowed = request.session.get("protected_page_allowed", False)
    if request.method == "POST":
        if request.POST.get("code") == VALID_CODE:
            is_allowed = True
            request.session["protected_page_allowed"] = True
    template = "protected/view.html" if is_allowed else "protected/entry.html"
    return render(request, template, {})


@login_required
def user_only_view(request, *args, **kwargs):
    return render(request, "protected/user-only.html", {})


@staff_member_required(login_url=LOGIN_URL)
def staff_only_view(request, *args, **kwargs):
    return render(request, "protected/user-only.html", {})