from django.db.models import Q
from customers.models import Customer
from subscriptions.models import Subscription, UserSubscription, SubscriptionStatus


def _user_subscription(user):
    if not user or not user.is_authenticated:
        return None
    return UserSubscription.objects.filter(user=user).select_related("subscription").first()


def refresh_active_users_subscriptions(
        user_ids=None, 
        active_only=True,
        days_left=-1,
        days_ago=-1,
        day_start=-1,
        day_end=-1,
        verbose=False):
    qs = UserSubscription.objects.all()
    if active_only:
        qs = qs.by_active_trialing()
    if user_ids is not None:
        qs = qs.by_user_ids(user_ids=user_ids)
    if days_ago > -1:
        qs = qs.by_days_ago(days_ago=days_ago)
    if days_left > -1:
        qs = qs.by_days_left(days_left=days_left)
    if day_start > -1 and day_end > -1:
        qs = qs.by_range(days_start=day_start, days_end=day_end, verbose=verbose)
    complete_count = 0
    qs_count = qs.count()
    for obj in qs:
        if verbose:
            print("Refreshing subscription", obj.user, obj.subscription, obj.current_period_end)
        obj.save()
        complete_count += 1
    return complete_count == qs_count

def clear_dangling_subs():
    qs = Customer.objects.filter(paystack_id__isnull=False)
    cleaned_count = 0
    for customer_obj in qs:
        user = customer_obj.user
        if not UserSubscription.objects.filter(user=user).exists():
            UserSubscription.objects.create(
                user=user,
                active=False,
                status=SubscriptionStatus.CANCELED,
                user_cancelled=True,
            )
            cleaned_count += 1
    return cleaned_count

def sync_subs_group_permissions():
    qs = Subscription.objects.filter(active=True)
    for obj in qs:
        sub_perms = obj.permissions.all()
        for group in obj.groups.all():
            group.permissions.set(sub_perms)


def subscription_has_feature(user, feature_code):
    user_sub = _user_subscription(user)
    return bool(user_sub and user_sub.has_feature(feature_code))


def user_subscription_plan(user):
    return _user_subscription(user)


def subscription_feature_limit(user, limit_code):
    user_sub = _user_subscription(user)
    if not user_sub or not user_sub.subscription:
        return None
    return user_sub.subscription.get_feature_limit(limit_code)


def subscription_active_task_limit(user):
    return subscription_feature_limit(user, "active_tasks")


def subscription_turnaround_hours(user):
    return subscription_feature_limit(user, "turnaround_hours")


def subscription_analytics_access_level(user):
    user_sub = _user_subscription(user)
    if not user_sub or not user_sub.subscription:
        return 0
    return user_sub.analytics_tier


def subscription_support_channel(user):
    user_sub = _user_subscription(user)
    if not user_sub:
        return "email"
    return user_sub.support_channel


def subscription_matching_mode(user):
    if subscription_has_feature(user, "priority_matching"):
        return "priority"
    if subscription_has_feature(user, "premium_sessions"):
        return "priority"
    if subscription_has_feature(user, "standard_matching"):
        return "standard"
    return "standard"


def subscription_session_mode(user):
    if subscription_has_feature(user, "premium_sessions"):
        return "premium"
    return "standard"


def student_active_task_count(user):
    if not user or not user.is_authenticated:
        return 0

    from marketplace.models import TaskOrder

    return TaskOrder.objects.filter(
        student=user,
        status__in=[
            TaskOrder.Status.OPEN,
            TaskOrder.Status.ASSIGNED,
            TaskOrder.Status.IN_PROGRESS,
            TaskOrder.Status.QUALITY_REVIEW,
            TaskOrder.Status.REVISION,
            TaskOrder.Status.ESCALATED,
        ],
    ).count()


def can_publish_task(user):
    limit = subscription_active_task_limit(user)
    if limit is None:
        return True
    return student_active_task_count(user) < limit
