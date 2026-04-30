from django.contrib.auth import authenticate, login
from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib import messages

from auth.forms import PUBLIC_ROLE_CHOICES
from auth.models import UserRole
from auth.permissions import portal_url_for_user

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
            role = UserRole.RoleType.STUDENT
        
        # Check if user already exists
        if User.objects.filter(username__iexact=username).exists():
            messages.error(request, "Username already exists.")
            return render(request, "auth/register.html", {"role": role})
        
        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, "Email already registered.")
            return render(request, "auth/register.html", {"role": role})
        
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
        "roles": UserRole.RoleType.choices
    }
    return render(request, "auth/register.html", context)
