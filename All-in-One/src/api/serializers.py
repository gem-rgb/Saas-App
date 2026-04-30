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
    feature_codes = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = ['id', 'name', 'subtitle', 'features', 'feature_codes']

    def get_features(self, obj):
        return obj.get_features_as_list()

    def get_feature_codes(self, obj):
        return obj.get_feature_codes()


class UserSubscriptionSerializer(serializers.ModelSerializer):
    plan_name = serializers.ReadOnlyField()
    is_active_status = serializers.ReadOnlyField()
    feature_codes = serializers.SerializerMethodField()

    class Meta:
        model = UserSubscription
        fields = [
            'plan_name', 'status', 'is_active_status',
            'current_period_start', 'current_period_end',
            'cancel_at_period_end', 'original_period_start',
            'feature_codes',
        ]

    def get_feature_codes(self, obj):
        return obj.serialize().get("feature_codes", [])


class MLPredictionSerializer(serializers.ModelSerializer):
    health_color = serializers.ReadOnlyField()

    class Meta:
        model = MLPrediction
        fields = [
            'health_score',
            'engagement_level', 'predicted_usage_next_month',
            'recommendations', 'health_color', 'last_calculated',
        ]


class UserActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = UserActivity
        fields = ['action', 'path', 'metadata', 'timestamp']
