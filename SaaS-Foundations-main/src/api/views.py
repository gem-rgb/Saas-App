from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from marketplace.models import TaskOrder
from marketplace.permissions import get_platform_role
from marketplace.serializers import TaskOrderSerializer
from operations.models import EscalationCase, Region, TaskerPerformanceSnapshot
from subscriptions.models import UserSubscription
from analytics.models import MLPrediction, UserActivity
from analytics import ml_engine
from profiles.models import UserProfile
from trust.models import AIInterviewSession, IdentityVerification, TaskerApplication

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


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def portal_summary_view(request):
    """Role-aware portal summary for dashboards and integrations."""
    role = get_platform_role(request.user)
    summary = {
        "role": role,
        "task_count": 0,
        "open_count": 0,
        "assigned_count": 0,
        "completed_count": 0,
    }
    if role == "student":
        tasks = TaskOrder.objects.filter(student=request.user)
    elif role == "tasker" and hasattr(request.user, "tasker_profile"):
        tasks = TaskOrder.objects.filter(assigned_tasker=request.user.tasker_profile)
    elif role == "manager":
        tasks = TaskOrder.objects.filter(status__in=["open", "assigned", "in_progress", "quality_review", "revision", "escalated"])
    else:
        tasks = TaskOrder.objects.all()

    summary["task_count"] = tasks.count()
    summary["open_count"] = tasks.filter(status="open").count()
    summary["assigned_count"] = tasks.filter(status="assigned").count()
    summary["completed_count"] = tasks.filter(status="completed").count()

    return Response({
        "summary": summary,
        "analytics": ml_engine.analyze_user(request.user),
        "subscription": UserSubscription.objects.filter(user=request.user).first().serialize() if UserSubscription.objects.filter(user=request.user).exists() else None,
    })


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def marketplace_tasks_view(request):
    """
    Marketplace Tasks API
    GET: List user's tasks
    POST: Create a new task
    """
    from api.serializers.marketplace import TaskOrderSerializer
    from rest_framework import status
    
    if request.method == 'GET':
        role = get_platform_role(request.user)
        if role == "student":
            tasks = TaskOrder.objects.filter(student=request.user).order_by("-created_at")
        elif role == "tasker" and hasattr(request.user, "tasker_profile"):
            tasks = TaskOrder.objects.filter(assigned_tasker=request.user.tasker_profile).order_by("-created_at")
        elif role == "manager":
            tasks = TaskOrder.objects.filter(status__in=["open", "assigned", "in_progress", "quality_review", "revision", "escalated"]).order_by("-created_at")
        else:
            tasks = TaskOrder.objects.all().order_by("-created_at")
            
        serializer = TaskOrderSerializer(tasks[:50], many=True)
        return Response({"role": role, "tasks": serializer.data})
        
    elif request.method == 'POST':
        serializer = TaskOrderSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(student=request.user, status=TaskOrder.Status.DRAFT)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def trust_application_view(request):
    """Current tasker recruitment, KYC, and interview state."""
    application, _ = TaskerApplication.objects.get_or_create(applicant=request.user)
    identity, _ = IdentityVerification.objects.get_or_create(application=application)
    interviews = AIInterviewSession.objects.filter(application=application).order_by("-started_at")
    return Response({
        "application": {
            "status": application.status,
            "headline": application.headline,
            "trust_score": application.trust_score,
            "document_confidence": application.document_confidence,
            "competency_confidence": application.competency_confidence,
            "interview_confidence": application.interview_confidence,
            "fraud_risk_score": application.fraud_risk_score,
            "manual_review_required": application.manual_review_required,
            "reviewed_at": application.reviewed_at,
        },
        "identity": {
            "status": identity.status,
            "face_match_score": identity.face_match_score,
            "liveness_score": identity.liveness_score,
            "document_match_score": identity.document_match_score,
            "authenticity_score": identity.authenticity_score,
        },
        "interviews": [
            {
                "id": session.id,
                "mode": session.mode,
                "overall_score": session.overall_score,
                "recommendation": session.recommendation,
                "started_at": session.started_at,
            }
            for session in interviews[:10]
        ],
        "is_ready": application.status == TaskerApplication.Status.APPROVED,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def operations_overview_view(request):
    """Regional operations overview for managers and admins."""
    role = get_platform_role(request.user)
    if role not in {"manager", "admin"}:
        return Response({"detail": "Forbidden."}, status=403)

    regions = Region.objects.filter(active=True).order_by("name")
    escalations = EscalationCase.objects.select_related("task", "region").order_by("-opened_at")[:25]
    snapshots = TaskerPerformanceSnapshot.objects.select_related("tasker", "region").order_by("-period_end")[:25]
    return Response({
        "role": role,
        "regions": [
            {"id": region.id, "name": region.name, "code": region.code, "timezone": region.timezone}
            for region in regions
        ],
        "escalations": [
            {
                "id": escalation.id,
                "task_title": escalation.task.title,
                "status": escalation.status,
                "priority": escalation.priority,
                "region": escalation.region.name if escalation.region else None,
            }
            for escalation in escalations
        ],
        "snapshots": [
            {
                "id": snapshot.id,
                "tasker": snapshot.tasker.user.username,
                "region": snapshot.region.name if snapshot.region else None,
                "ranking_score": snapshot.ranking_score,
                "quality_rating": snapshot.quality_rating,
                "on_time_rate": snapshot.on_time_rate,
            }
            for snapshot in snapshots
        ],
    })
