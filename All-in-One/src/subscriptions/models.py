import datetime
import re
import helpers.paystack_billing
from django.db import models
from django.db.models import Q
from django.contrib.auth.models import Group, Permission
from django.db.models.signals import post_save
from django.conf import settings 
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

User = settings.AUTH_USER_MODEL # "auth.User"

ALLOW_CUSTOM_GROUPS = True
SUBSCRIPTION_PERMISSIONS = [
    ("advanced", "Advanced Perm"), # subscriptions.advanced
    ("pro", "Pro Perm"),  # subscriptions.pro
    ("basic", "Basic Perm"),  # subscriptions.basic,
    ("basic_ai", "Basic AI Perm")
]

FEATURE_CODE_ALIASES = {
    "task_creation": {"task_creation", "task-creation", "assignment_creation", "assignment-creation"},
    "standard_matching": {"standard_matching", "subject_recommendations", "subject-recommendations", "subject_based_recommendations", "subject-based-writer-recommendations", "subject-based-writer-suggestions", "assignment_recommendations"},
    "subject_recommendations": {
        "subject_recommendations",
        "subject-recommendations",
        "subject_based_recommendations",
        "subject-based-writer-recommendations",
        "subject-based-writer-suggestions",
        "assignment_recommendations",
        "standard_matching",
    },
    "task_tracking": {"task_tracking", "task-tracking", "assignment_tracking", "assignment-tracking"},
    "basic_support": {"basic_support", "basic-support", "email-support", "email_support"},
    "email_support": {"email_support", "email-support", "basic_support", "basic-support"},
    "live_marketplace": {"live_marketplace", "live-marketplace", "marketplace", "marketplace-access"},
    "priority_matching": {"priority_matching", "priority-matching"},
    "task_chat": {"task_chat", "task-chat", "chat", "in-app-chat", "live_chat_support"},
    "live_chat_support": {"live_chat_support", "live-chat-support", "task_chat", "task-chat", "chat"},
    "revision_requests": {"revision_requests", "revision-requests", "revision", "revision_guarantee", "unlimited_revisions"},
    "revision_guarantee": {"revision_guarantee", "revision-guarantee", "revision_requests", "revision-requests", "unlimited_revisions"},
    "unlimited_revisions": {"unlimited_revisions", "unlimited-revisions", "revision_requests", "revision-requests", "revision_guarantee"},
    "analytics_dashboard": {
        "analytics_dashboard",
        "analytics-dashboard",
        "assignment_analytics",
        "assignment-analytics",
        "assignment_insights",
        "assignment-insights",
        "analytics",
        "basic_analytics",
        "advanced_analytics",
        "full_analytics_dashboard",
    },
    "basic_analytics": {"basic_analytics", "basic-analytics", "analytics_dashboard", "analytics-dashboard", "advanced_analytics", "full_analytics_dashboard"},
    "advanced_analytics": {"advanced_analytics", "advanced-analytics", "analytics_dashboard", "analytics-dashboard", "basic_analytics", "full_analytics_dashboard"},
    "full_analytics_dashboard": {"full_analytics_dashboard", "full-analytics-dashboard", "analytics_dashboard", "analytics-dashboard", "basic_analytics", "advanced_analytics"},
    "manager_console": {"manager_console", "manager-console", "operations", "operations-console", "dedicated_manager"},
    "dedicated_manager": {"dedicated_manager", "dedicated-manager", "manager_console", "manager-console"},
    "premium_sessions": {
        "premium_sessions",
        "premium_session",
        "premium-session",
        "dedicated_sessions",
        "dedicated_session",
        "dedicated-session",
        "dedicated_manager",
        "dedicated-manager",
        "exam_sessions",
        "exam_session",
        "exam-session",
        "revision_sessions",
        "revision_session",
        "revision-session",
        "teaching_sessions",
        "teaching_session",
        "teaching-session",
    },
    "dispute_resolution": {"dispute_resolution", "dispute-resolution", "escalation_resolution", "escalation-resolution"},
    "refund_management": {"refund_management", "refund-management", "refunds", "refund-processing"},
    "quality_reports": {"quality_reports", "quality-reports", "quality_analysis", "quality-analysis", "plagiarism_reports"},
    "plagiarism_reports": {"plagiarism_reports", "plagiarism-reports", "quality_reports", "quality-reports"},
    "priority_phone_support": {"priority_phone_support", "priority-phone-support"},
}


def _normalize_feature_code(value):
    if value is None:
        return ""
    return slugify(str(value).strip()).replace("-", "_")


def _feature_code_variants(feature_code):
    requested_code = _normalize_feature_code(feature_code)
    if not requested_code:
        return set()

    variants = {requested_code}
    for canonical_code, aliases in FEATURE_CODE_ALIASES.items():
        family_codes = {_normalize_feature_code(canonical_code)}
        family_codes.update(_normalize_feature_code(alias) for alias in aliases)
        if requested_code in family_codes:
            variants.update(family_codes)

    return {code for code in variants if code}


# Create your models here.
class Subscription(models.Model):
    """
    Subscription Plan = Stripe Product
    """
    name = models.CharField(max_length=120)
    subtitle = models.TextField(blank=True, null=True)
    active = models.BooleanField(default=True)
    groups = models.ManyToManyField(Group) # one-to-one
    feature_codes = models.JSONField(default=list, blank=True)
    permissions =  models.ManyToManyField(Permission, limit_choices_to={
        "content_type__app_label": "subscriptions", "codename__in": [x[0]for x in SUBSCRIPTION_PERMISSIONS]
        }
    )
    paystack_id = models.CharField(max_length=120, null=True, blank=True)

    order = models.IntegerField(default=-1, help_text='Ordering on Django pricing page')
    featured = models.BooleanField(default=True, help_text='Featured on Django pricing page')
    updated = models.DateTimeField(auto_now=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    features = models.TextField(help_text="Features for pricing, seperated by new line", blank=True, null=True)

    def __str__(self):
        return f"{self.name}"

    class Meta:
        ordering = ['order', 'featured', '-updated']
        permissions = SUBSCRIPTION_PERMISSIONS

    def get_features_as_list(self):
        if not self.features:
            return []
        return [x.strip() for x in self.features.split("\n")]

    def get_feature_codes(self):
        if isinstance(self.feature_codes, list) and self.feature_codes:
            return [str(code).strip() for code in self.feature_codes if str(code).strip()]
        if not self.features:
            return []
        return [slugify(feature) for feature in self.get_features_as_list()]

    def get_feature_limit(self, limit_code):
        normalized_limit = _normalize_feature_code(limit_code)
        if normalized_limit not in {"active_tasks", "turnaround_hours"}:
            return None

        for code in self.get_feature_codes():
            normalized_code = _normalize_feature_code(code)
            if normalized_limit == "active_tasks" and normalized_code.startswith("active_tasks_"):
                value = normalized_code.removeprefix("active_tasks_")
                if value == "unlimited":
                    return None
                if value.isdigit():
                    return int(value)
            if normalized_limit == "turnaround_hours" and normalized_code.startswith("turnaround_") and normalized_code.endswith("h"):
                value = normalized_code.removeprefix("turnaround_").removesuffix("h")
                if value.isdigit():
                    return int(value)

        return None

    def has_feature(self, feature_code):
        requested_code = _normalize_feature_code(feature_code)
        if not requested_code:
            return False

        available_codes = {
            _normalize_feature_code(code)
            for code in self.get_feature_codes()
            if _normalize_feature_code(code)
        }
        return bool(available_codes.intersection(_feature_code_variants(requested_code)))

    @property
    def active_task_limit(self):
        return self.get_feature_limit("active_tasks")

    @property
    def turnaround_hours(self):
        return self.get_feature_limit("turnaround_hours")

    def save(self, *args, **kwargs):
        # Paystack doesn't require a 'Product' wrapper like Stripe does.
        # We can just leave paystack_id blank or generate a local reference.
        if not self.paystack_id:
            self.paystack_id = f"prod_local_{self.name.lower().replace(' ', '_')}"
        super().save(*args, **kwargs)


# Create your models here.
class SubscriptionPrice(models.Model):
    """
    Subscription Price = Stripe Price
    """
    class IntervalChoices(models.TextChoices):
        MONTHLY = "month", "Monthly"
        YEARLY = "year", "Yearly"

    subscription = models.ForeignKey(Subscription, on_delete=models.SET_NULL, null=True)
    paystack_id = models.CharField(max_length=120, null=True, blank=True)
    interval = models.CharField(max_length=120, 
                                default=IntervalChoices.MONTHLY, 
                                choices=IntervalChoices.choices
                            )
    price = models.DecimalField(max_digits=10, decimal_places=2, default=99.99)
    order = models.IntegerField(default=-1, help_text='Ordering on Django pricing page')
    featured = models.BooleanField(default=True, help_text='Featured on Django pricing page')
    updated = models.DateTimeField(auto_now=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['subscription__order', 'order', 'featured', '-updated']

    def get_checkout_url(self):
        return reverse("sub-price-checkout", 
            kwargs = {"price_id": self.id}  
            )

    @property
    def display_features_list(self):
        if not self.subscription:
            return []
        return self.subscription.get_features_as_list()
    
    @property
    def display_sub_name(self):
        if not self.subscription:
            return "Plan"
        return self.subscription.name

    @property
    def display_sub_subtitle(self):
        if not self.subscription:
            return "Plan"
        return self.subscription.subtitle
    
    @property
    def product_paystack_id(self):
        if not self.subscription:
            return None
        return self.subscription.paystack_id
    
    def save(self, *args, **kwargs):
        if not self.paystack_id:
            try:
                # Paystack intervals are "monthly", "annually", etc.
                paystack_interval = "monthly" if self.interval == "month" else "annually"
                paystack_id = helpers.paystack_billing.create_plan(
                    name=f"{self.subscription.name} - {self.interval}",
                    amount_minor=int(self.price * 100),
                    interval=paystack_interval,
                )
                self.paystack_id = paystack_id
            except Exception as e:
                print(f"Error creating Paystack plan: {e}")
        super().save(*args, **kwargs)
        if self.featured and self.subscription:
            qs = SubscriptionPrice.objects.filter(
                subscription=self.subscription,
                interval=self.interval
            ).exclude(id=self.id)
            qs.update(featured=False)

class SubscriptionStatus(models.TextChoices):
    ACTIVE = 'active', 'Active'
    TRIALING = 'trialing', 'Trialing'
    INCOMPLETE = 'incomplete', 'Incomplete'
    INCOMPLETE_EXPIRED = 'incomplete_expired', 'Incomplete Expired'
    PAST_DUE = 'past_due', 'Past Due'
    CANCELED = 'canceled', 'Canceled'
    UNPAID = 'unpaid', 'Unpaid'
    PAUSED = 'paused', 'Paused'

class UserSubscriptionQuerySet(models.QuerySet):
    def by_range(self, days_start=7, days_end=120, verbose=True):
        now = timezone.now()
        days_start_from_now = now + datetime.timedelta(days=days_start)
        days_end_from_now = now + datetime.timedelta(days=days_end)
        range_start = days_start_from_now.replace(hour=0, minute=0, second=0, microsecond=0)
        range_end = days_end_from_now.replace(hour=23, minute=59, second=59, microsecond=59)
        if verbose:
            print(f"Range is {range_start} to {range_end}")
        return self.filter(
            current_period_end__gte=range_start,
            current_period_end__lte=range_end
        )
    
    def by_days_left(self, days_left=7):
        now = timezone.now()
        in_n_days = now + datetime.timedelta(days=days_left)
        day_start = in_n_days.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = in_n_days.replace(hour=23, minute=59, second=59, microsecond=59)
        return self.filter(
            current_period_end__gte=day_start,
            current_period_end__lte=day_end
        )
    
    def by_days_ago(self, days_ago=3):
        now = timezone.now()
        in_n_days = now - datetime.timedelta(days=days_ago)
        day_start = in_n_days.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = in_n_days.replace(hour=23, minute=59, second=59, microsecond=59)
        return self.filter(
            current_period_end__gte=day_start,
            current_period_end__lte=day_end
        )

    def by_active_trialing(self):
        active_qs_lookup = (
            Q(status = SubscriptionStatus.ACTIVE) |
            Q(status = SubscriptionStatus.TRIALING)
        )
        return self.filter(active_qs_lookup)
    
    def by_user_ids(self, user_ids=None):
        qs = self
        if isinstance(user_ids, list):
            qs = self.filter(user_id__in=user_ids)
        elif isinstance(user_ids, int):
            qs = self.filter(user_id__in=[user_ids])
        elif isinstance(user_ids, str):
            qs = self.filter(user_id__in=[user_ids])
        return qs


class UserSubscriptionManager(models.Manager):
    def get_queryset(self):
        return UserSubscriptionQuerySet(self.model, using=self._db)

    # def by_user_ids(self, user_ids=None):
    #     return self.get_queryset().by_user_ids(user_ids=user_ids)
        

class UserSubscription(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    subscription = models.ForeignKey(Subscription, on_delete=models.SET_NULL, null=True, blank=True)
    paystack_id = models.CharField(max_length=120, null=True, blank=True)
    active = models.BooleanField(default=True)
    user_cancelled = models.BooleanField(default=False)
    original_period_start = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    current_period_start = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    current_period_end = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    cancel_at_period_end = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=SubscriptionStatus.choices, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    objects = UserSubscriptionManager()

    def get_absolute_url(self):
        return reverse("user_subscription")
    
    def get_cancel_url(self):
        return reverse("user_subscription_cancel")
    
    @property
    def is_active_status(self):
        return self.status in [
            SubscriptionStatus.ACTIVE, 
            SubscriptionStatus.TRIALING
        ]
    
    @property
    def plan_name(self):
        if not self.subscription:
            return None
        return self.subscription.name

    @property
    def active_task_limit(self):
        if not self.subscription:
            return None
        return self.subscription.active_task_limit

    @property
    def turnaround_hours(self):
        if not self.subscription:
            return None
        return self.subscription.turnaround_hours

    @property
    def analytics_tier(self):
        if not self.subscription:
            return 0
        if self.subscription.has_feature("full_analytics_dashboard"):
            return 3
        if self.subscription.has_feature("advanced_analytics"):
            return 2
        if self.subscription.has_feature("basic_analytics") or self.subscription.has_feature("analytics_dashboard"):
            return 1
        return 0

    @property
    def support_channel(self):
        if not self.subscription:
            return "email"
        if self.subscription.has_feature("priority_phone_support"):
            return "phone"
        if self.subscription.has_feature("live_chat_support") or self.subscription.has_feature("task_chat"):
            return "chat"
        return "email"

    def has_feature(self, feature_code):
        if not self.is_active_status or not self.subscription:
            return False
        return self.subscription.has_feature(feature_code)

    def serialize(self):
        return {
            "plan_name": self.plan_name,
            "status": self.status,
            "current_period_start": self.current_period_start,
            "current_period_end": self.current_period_end,
            "feature_codes": self.subscription.get_feature_codes() if self.subscription else [],
            "active_task_limit": self.active_task_limit,
            "turnaround_hours": self.turnaround_hours,
            "analytics_tier": self.analytics_tier,
            "support_channel": self.support_channel,
        }

    @property
    def billing_cycle_anchor(self):
        """
        https://docs.stripe.com/payments/checkout/billing-cycle
        Optional delay to start new subscription in
        Stripe checkout
        """
        if not self.current_period_end:
            return None
        return int(self.current_period_end.timestamp())

    def save(self, *args, **kwargs):
        if (self.original_period_start is None and
            self.current_period_start is not None
            ):
            self.original_period_start = self.current_period_start
        super().save(*args, **kwargs)



def user_sub_post_save(sender, instance, *args, **kwargs):
    user_sub_instance = instance
    user = user_sub_instance.user
    subscription_obj = user_sub_instance.subscription
    groups_ids = []
    if subscription_obj is not None:
        groups = subscription_obj.groups.all()
        groups_ids = groups.values_list('id', flat=True)
    if not ALLOW_CUSTOM_GROUPS:
        user.groups.set(groups_ids)
    else:
        subs_qs = Subscription.objects.filter(active=True)
        if subscription_obj is not None:
            subs_qs = subs_qs.exclude(id=subscription_obj.id)
        subs_groups = subs_qs.values_list("groups__id", flat=True)
        subs_groups_set = set(subs_groups)
        # groups_ids = groups.values_list('id', flat=True) # [1, 2, 3] 
        current_groups = user.groups.all().values_list('id', flat=True)
        groups_ids_set = set(groups_ids)
        current_groups_set = set(current_groups) - subs_groups_set
        final_group_ids = list(groups_ids_set | current_groups_set)
        user.groups.set(final_group_ids)


post_save.connect(user_sub_post_save, sender=UserSubscription)
