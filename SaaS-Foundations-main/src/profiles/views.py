from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import HttpResponse

from django.contrib.auth import get_user_model
from .models import UserProfile
from .forms import UserBasicForm, UserProfileForm

User = get_user_model()

@login_required
def profile_list_view(request):
    context = {
        "object_list": User.objects.filter(is_active=True)
    }
    return render(request, "profiles/list.html", context)


@login_required
def profile_detail_view(request, username=None, *args, **kwargs):
    user = request.user
    profile_user_obj = get_object_or_404(User, username=username)
    profile_obj, _ = UserProfile.objects.get_or_create(user=profile_user_obj)
    is_me = profile_user_obj == user
    
    # Get subscription info
    sub_info = None
    try:
        user_sub = profile_user_obj.usersubscription
        sub_info = {
            "plan_name": user_sub.plan_name,
            "status": user_sub.status,
            "is_active": user_sub.is_active_status,
        }
    except Exception:
        pass
    
    context = {
        "object": profile_user_obj,
        "instance": profile_user_obj,
        "profile": profile_obj,
        "owner": is_me,
        "sub_info": sub_info,
    }
    return render(request, "profiles/detail.html", context)


@login_required
def profile_edit_view(request):
    user = request.user
    profile_obj, _ = UserProfile.objects.get_or_create(user=user)
    user_form = UserBasicForm(instance=user)
    profile_form = UserProfileForm(instance=profile_obj)
    
    if request.method == "POST":
        user_form = UserBasicForm(request.POST, instance=user)
        profile_form = UserProfileForm(request.POST, request.FILES, instance=profile_obj)
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, "Your profile has been updated.")
            return redirect("profile_edit")
    
    context = {
        "user_form": user_form,
        "profile_form": profile_form,
        "profile": profile_obj,
    }
    return render(request, "profiles/edit.html", context)
