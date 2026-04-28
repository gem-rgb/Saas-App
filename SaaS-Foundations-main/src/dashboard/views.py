import datetime
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from visits.models import PageVisit
from subscriptions.models import UserSubscription
from analytics.models import UserActivity
from analytics import ml_engine


@login_required
def dashboard_view(request):
    user = request.user
    now = timezone.now()

    # Track activity
    UserActivity.objects.create(
        user=user,
        action=UserActivity.ActionChoices.PAGE_VIEW,
        path=request.path,
        metadata={"page": "dashboard"}
    )

    # Subscription info
    sub_info = {
        "plan_name": "Free",
        "status": "No Plan",
        "is_active": False,
        "days_remaining": 0,
        "period_end": None,
        "period_start": None,
        "membership_age": None,
    }
    try:
        user_sub = UserSubscription.objects.get(user=user)
        sub_info['plan_name'] = user_sub.plan_name or "Free"
        sub_info['status'] = user_sub.status or "No Plan"
        sub_info['is_active'] = user_sub.is_active_status
        sub_info['period_end'] = user_sub.current_period_end
        sub_info['period_start'] = user_sub.current_period_start
        if user_sub.current_period_end:
            sub_info['days_remaining'] = max(0, (user_sub.current_period_end - now).days)
        if user_sub.original_period_start:
            sub_info['membership_age'] = (now - user_sub.original_period_start).days
    except UserSubscription.DoesNotExist:
        pass

    # Page visit stats
    total_visits = PageVisit.objects.count()
    recent_visits = PageVisit.objects.filter(
        timestamp__gte=now - datetime.timedelta(days=7)
    ).count()

    # Recent user activity
    recent_activities = UserActivity.objects.filter(user=user).order_by('-timestamp')[:8]

    # ML analysis
    try:
        analysis = ml_engine.analyze_user(user)
        health_score = analysis['health_score']
        health_color = analysis['health_color']
        churn_probability = analysis['churn_probability']
        churn_risk_level = analysis['churn_risk_level']
        recommendations = analysis['recommendations'][:3]
    except Exception:
        health_score = 50
        health_color = "yellow"
        churn_probability = 30
        churn_risk_level = "low"
        recommendations = []

    # Usage chart (last 7 days)
    usage_chart = []
    for i in range(6, -1, -1):
        day = now - datetime.timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999)
        count = UserActivity.objects.filter(
            user=user,
            timestamp__gte=day_start,
            timestamp__lte=day_end,
        ).count()
        usage_chart.append({
            "day": day.strftime("%a"),
            "count": count,
            "height": max(8, min(count * 15, 100)),
        })

    context = {
        "sub_info": sub_info,
        "total_visits": total_visits,
        "recent_visits": recent_visits,
        "recent_activities": recent_activities,
        "health_score": health_score,
        "health_color": health_color,
        "churn_probability": churn_probability,
        "churn_risk_level": churn_risk_level,
        "recommendations": recommendations,
        "usage_chart": usage_chart,
    }
    return render(request, "dashboard/main.html", context)