from django.contrib.auth import get_user_model
from django.test import TestCase

from subscriptions.models import Subscription, SubscriptionStatus, UserSubscription
from subscriptions.utils import (
    subscription_has_feature,
    subscription_matching_mode,
    subscription_session_mode,
)


class SubscriptionTierFeatureTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.user = self.user_model.objects.create_user(
            username="tier-user",
            email="tier-user@example.com",
            password="testpass123",
        )
        self.pro_plan = Subscription.objects.create(
            name="Pro",
            subtitle="Priority matching tier",
            order=2,
            features="Priority matching\nLive chat support",
            feature_codes=["priority_matching", "live_chat_support"],
        )
        self.expert_plan = Subscription.objects.create(
            name="Expert",
            subtitle="Premium sessions tier",
            order=3,
            features="Priority matching\nPremium exam sessions",
            feature_codes=["priority_matching", "premium_sessions"],
        )

    def test_priority_matching_is_available_on_pro_and_sessions_on_expert(self):
        subscription = UserSubscription.objects.create(
            user=self.user,
            subscription=self.pro_plan,
            status=SubscriptionStatus.ACTIVE,
        )

        self.assertEqual(subscription_matching_mode(self.user), "priority")
        self.assertEqual(subscription_session_mode(self.user), "standard")
        self.assertFalse(subscription_has_feature(self.user, "premium_sessions"))

        subscription.subscription = self.expert_plan
        subscription.save(update_fields=["subscription", "updated"])

        self.assertEqual(subscription_matching_mode(self.user), "priority")
        self.assertEqual(subscription_session_mode(self.user), "premium")
        self.assertTrue(subscription_has_feature(self.user, "premium_sessions"))
        self.assertTrue(subscription_has_feature(self.user, "dedicated_manager"))
