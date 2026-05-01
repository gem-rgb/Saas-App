from django.contrib.auth import authenticate, login
from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib import messages

from auth.forms import PUBLIC_ROLE_CHOICES
from auth.models import UserRole
from auth.permissions import get_user_role, portal_url_for_user

User = get_user_model()

# Create your views here.
def social_login_guard_view(request, provider):
    messages.error(
        request,
        f"{provider.title()} sign-in is unavailable until OAuth client IDs are configured.",
    )
    return redirect(reverse("account_login"))


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username") or None
        password = request.POST.get("password") or None
        # eval("print('hello')")
        if all([username, password]):
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect(portal_url_for_user(user))
    return render(request, "auth/login.html", {})


def staff_login_view(request):
    if request.user.is_authenticated:
        return redirect(portal_url_for_user(request.user))

    if request.method == "POST":
        identifier = (request.POST.get("login") or request.POST.get("username") or "").strip()
        password = request.POST.get("password") or None
        if identifier and password:
            user = authenticate(request, username=identifier, password=password)
            if user is None and "@" in identifier:
                staff_username = User.objects.filter(email__iexact=identifier).values_list("username", flat=True).first()
                if staff_username:
                    user = authenticate(request, username=staff_username, password=password)

            if user is not None:
                user_role = UserRole.objects.filter(user=user).first()
                if user_role is None and (
                    getattr(user, "manager_profile", None) is not None
                    or getattr(user, "manager_application", None) is not None
                    or getattr(user, "is_staff", False)
                    or getattr(user, "is_superuser", False)
                ):
                    user_role = get_user_role(user)
                role_type = user_role.role_type if user_role else None
                if role_type not in {UserRole.RoleType.MANAGER, UserRole.RoleType.ADMIN}:
                    messages.error(request, "Use the public login for student and tasker accounts.")
                else:
                    login(request, user)
                    return redirect(portal_url_for_user(user))
            else:
                messages.error(request, "Invalid staff credentials.")
        else:
            messages.error(request, "Enter your staff username or email and password.")

    return render(request, "auth/staff_login.html", {})


def register_view(request):
    """Register a new user with role selection"""
    if request.method == "POST":
        username = request.POST.get("username") or None
        email = request.POST.get("email") or None
        password = request.POST.get("password") or None
        role = request.POST.get("role") or UserRole.RoleType.STUDENT

        # Validate role
        valid_roles = [choice[0] for choice in PUBLIC_ROLE_CHOICES]
        if role not in valid_roles:
            messages.error(request, "Manager accounts are created by the admin team.")
            return render(request, "auth/register.html", {"roles": PUBLIC_ROLE_CHOICES})

        # Check if user already exists
        if User.objects.filter(username__iexact=username).exists():
            messages.error(request, "Username already exists.")
            return render(request, "auth/register.html", {"roles": PUBLIC_ROLE_CHOICES, "role": role})
        
        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, "Email already registered.")
            return render(request, "auth/register.html", {"roles": PUBLIC_ROLE_CHOICES, "role": role})
        
        try:
            # Create user
            user = User.objects.create_user(username, email=email, password=password)
            
            # Create user role
            UserRole.objects.create(
                user=user,
                role_type=role,
                verified=(role == UserRole.RoleType.STUDENT)  # Students verified by default
            )
            
            messages.success(request, f"Account created successfully as {dict(UserRole.RoleType.choices)[role]}!")
            
            # Auto-login
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect(portal_url_for_user(user))
        
        except Exception as e:
            messages.error(request, f"Registration failed: {str(e)}")
    
    context = {
        "roles": PUBLIC_ROLE_CHOICES
    }
    return render(request, "auth/register.html", context)
