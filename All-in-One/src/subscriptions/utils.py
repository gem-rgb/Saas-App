from django.db.models import Q
from customers.models import Customer
from subscriptions.models import Subscription, UserSubscription, SubscriptionStatus


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
    if not user or not user.is_authenticated:
        return False
    user_sub = UserSubscription.objects.filter(user=user).select_related("subscription").first()
    return bool(user_sub and user_sub.has_feature(feature_code))


def user_subscription_plan(user):
    if not user or not user.is_authenticated:
        return None
    return UserSubscription.objects.filter(user=user).select_related("subscription").first()
