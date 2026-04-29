from rest_framework import serializers
from django.contrib.auth import get_user_model
from subscriptions.models import Subscription, UserSubscription, SubscriptionPrice
from analytics.models import UserActivity, MLPrediction
from profiles.models import UserProfile

User = get_user_model()


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['bio', 'phone', 'company', 'website', 'avatar_url', 'initials']


class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'date_joined', 'profile']
        read_only_fields = ['id', 'username', 'date_joined']


class SubscriptionSerializer(serializers.ModelSerializer):
    features = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = ['id', 'name', 'subtitle', 'features']

    def get_features(self, obj):
        return obj.get_features_as_list()


class UserSubscriptionSerializer(serializers.ModelSerializer):
    plan_name = serializers.ReadOnlyField()
    is_active_status = serializers.ReadOnlyField()

    class Meta:
        model = UserSubscription
        fields = [
            'plan_name', 'status', 'is_active_status',
            'current_period_start', 'current_period_end',
            'cancel_at_period_end', 'original_period_start',
        ]


class MLPredictionSerializer(serializers.ModelSerializer):
    churn_risk_level = serializers.ReadOnlyField()
    health_color = serializers.ReadOnlyField()

    class Meta:
        model = MLPrediction
        fields = [
            'health_score', 'churn_probability', 'churn_risk_level',
            'engagement_level', 'predicted_usage_next_month',
            'recommendations', 'health_color', 'last_calculated',
        ]


class UserActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = UserActivity
        fields = ['action', 'path', 'metadata', 'timestamp']
