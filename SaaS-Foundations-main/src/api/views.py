from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from subscriptions.models import UserSubscription
from analytics.models import MLPrediction, UserActivity
from analytics import ml_engine
from profiles.models import UserProfile

from .serializers import (
    UserSerializer,
    UserSubscriptionSerializer,
    MLPredictionSerializer,
    UserActivitySerializer,
)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me_view(request):
    """Current user details + subscription + profile."""
    serializer = UserSerializer(request.user)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def subscription_view(request):
    """Current user's subscription status."""
    try:
        user_sub = UserSubscription.objects.get(user=request.user)
        serializer = UserSubscriptionSerializer(user_sub)
        return Response(serializer.data)
    except UserSubscription.DoesNotExist:
        return Response({"detail": "No active subscription."}, status=404)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def health_score_view(request):
    """ML health score for current user."""
    analysis = ml_engine.analyze_user(request.user)
    return Response({
        "health_score": analysis['health_score'],
        "health_color": analysis['health_color'],
        "engagement_level": analysis['engagement_level'],
        "churn_probability": analysis['churn_probability'],
        "churn_risk_level": analysis['churn_risk_level'],
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def usage_view(request):
    """Usage data for current user."""
    analysis = ml_engine.analyze_user(request.user)
    return Response({
        "features": analysis['features'],
        "usage_forecast": analysis['usage_forecast'],
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def recommendations_view(request):
    """ML-powered recommendations for current user."""
    analysis = ml_engine.analyze_user(request.user)
    return Response({
        "recommendations": analysis['recommendations'],
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def activity_view(request):
    """Recent activity for current user."""
    activities = UserActivity.objects.filter(user=request.user)[:20]
    serializer = UserActivitySerializer(activities, many=True)
    return Response(serializer.data)
