from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import UserActivity
from . import ml_engine


@login_required
def analytics_dashboard_view(request):
    """ML-powered analytics dashboard."""
    user = request.user

    # Track this view as an activity
    UserActivity.objects.create(
        user=user,
        action=UserActivity.ActionChoices.PAGE_VIEW,
        path=request.path,
        metadata={"page": "analytics_dashboard"}
    )

    # Run ML analysis
    analysis = ml_engine.analyze_user(user)

    # Get recent activity for the feed
    recent_activities = UserActivity.objects.filter(
        user=user
    ).order_by('-timestamp')[:10]

    # Usage data for chart (last 7 days)
    from django.utils import timezone
    import datetime
    now = timezone.now()
    usage_chart_data = []
    for i in range(6, -1, -1):
        day = now - datetime.timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999)
        count = UserActivity.objects.filter(
            user=user,
            timestamp__gte=day_start,
            timestamp__lte=day_end,
        ).count()
        usage_chart_data.append({
            "day": day.strftime("%a"),
            "count": count,
            "height": max(4, min(count * 12, 100)),  # CSS height percentage
        })

    context = {
        **analysis,
        "recent_activities": recent_activities,
        "usage_chart_data": usage_chart_data,
    }
    return render(request, "analytics/dashboard.html", context)


def track_activity(user, action, path="", metadata=None):
    """Utility to track user activity from anywhere in the app."""
    if user.is_authenticated:
        UserActivity.objects.create(
            user=user,
            action=action,
            path=path,
            metadata=metadata or {},
        )
