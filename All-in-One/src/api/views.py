from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Avg, Count, Q

from marketplace.models import TaskNotification, TaskOrder
from marketplace.permissions import can_receive_work, get_platform_role
from marketplace.serializers import TaskOrderSerializer
from marketplace.services import recommend_taskers_for_subject
from operations.models import EscalationCase, Region, TaskerPerformanceSnapshot
from subscriptions.models import UserSubscription
from subscriptions.utils import (
    subscription_active_task_limit,
    subscription_analytics_access_level,
    subscription_has_feature,
    subscription_matching_mode,
    subscription_session_mode,
    subscription_support_channel,
    subscription_turnaround_hours,
    user_subscription_plan,
)
from analytics.models import UserActivity
from agents.interview_agent import infer_interview_focus
from trust.models import (
    AIInterviewSession,
    IdentityVerification,
    TaskerApplication,
    InteractiveInterviewSession,
    InterviewQuestion,
)
from trust.services import (
    create_interactive_interview_session,
    start_interactive_interview,
    submit_interview_answer,
    get_next_interview_question,
    complete_interview,
    get_interview_progress,
)

from .serializers import (
    UserSerializer,
    UserSubscriptionSerializer,
    UserActivitySerializer,
)


def _has_assignment_insights_access(user):
    role = get_platform_role(user)
    return role in {"manager", "admin"} or subscription_has_feature(user, "analytics_dashboard")


def _assignment_insights_locked_response():
    return Response(
        {
            "detail": "Assignment insights are available on paid plans.",
            "upgrade_url": "/pricing/",
        },
        status=status.HTTP_403_FORBIDDEN,
    )


def _marketplace_tasks_for_user(user):
    role = get_platform_role(user)
    if role == "student":
        return TaskOrder.objects.filter(student=user)
    if role == "tasker":
        tasker_profile = getattr(user, "tasker_profile", None)
        if tasker_profile is None or not can_receive_work(tasker_profile):
            return TaskOrder.objects.none()
        base_filter = Q(status__in=["open", "assigned", "in_progress", "quality_review", "revision"])
        return TaskOrder.objects.filter(
            base_filter | Q(assigned_tasker=tasker_profile) | Q(match_suggestions__tasker=tasker_profile)
        ).distinct()
    if role == "manager":
        return TaskOrder.objects.filter(status__in=["open", "assigned", "in_progress", "quality_review", "revision", "escalated"])
    return TaskOrder.objects.all()


def _assignment_context_for_user(user):
    tasks = _marketplace_tasks_for_user(user).select_related("student", "assigned_tasker", "category")
    counts = tasks.aggregate(
        total_count=Count("id"),
        draft_count=Count("id", filter=Q(status=TaskOrder.Status.DRAFT)),
        open_count=Count("id", filter=Q(status=TaskOrder.Status.OPEN)),
        assigned_count=Count("id", filter=Q(status=TaskOrder.Status.ASSIGNED)),
        in_progress_count=Count("id", filter=Q(status=TaskOrder.Status.IN_PROGRESS)),
        review_count=Count("id", filter=Q(status=TaskOrder.Status.QUALITY_REVIEW)),
        revision_count=Count("id", filter=Q(status=TaskOrder.Status.REVISION)),
        completed_count=Count("id", filter=Q(status=TaskOrder.Status.COMPLETED)),
        escalated_count=Count("id", filter=Q(status=TaskOrder.Status.ESCALATED)),
    )
    total_count = counts["total_count"] or 0
    dispute_count = EscalationCase.objects.filter(task__in=tasks).count()
    average_rating = tasks.aggregate(avg=Avg("ratings__overall_rating"))["avg"] or 0.0
    average_accuracy = tasks.aggregate(avg=Avg("ratings__accuracy_rating"))["avg"] or 0.0
    active_count = (
        counts["assigned_count"]
        + counts["in_progress_count"]
        + counts["review_count"]
        + counts["revision_count"]
    )

    if total_count == 0:
        health_score = 50
        engagement_level = "idle"
    else:
        completion_ratio = counts["completed_count"] / total_count
        quality_ratio = ((average_rating / 5.0) + (average_accuracy / 5.0)) / 2 if (average_rating or average_accuracy) else 0
        workload_ratio = active_count / total_count
        health_score = round(
            max(
                0,
                min(
                    100,
                    40
                    + (completion_ratio * 30)
                    + (quality_ratio * 25)
                    + (workload_ratio * 10)
                    - (dispute_count * 6)
                    - (counts["open_count"] * 1.5),
                ),
            )
        )
        if active_count >= max(3, total_count // 2):
            engagement_level = "busy"
        elif counts["completed_count"] >= active_count:
            engagement_level = "steady"
        else:
            engagement_level = "active"

    health_color = "green" if health_score >= 75 else "yellow" if health_score >= 45 else "red"
    subject_breakdown = list(
        tasks.values("subject")
        .annotate(task_count=Count("id"))
        .order_by("-task_count", "subject")[:6]
    )
    focus_subject = (
        tasks.exclude(subject__isnull=True)
        .exclude(subject__exact="")
        .order_by("-updated_at")
        .values_list("subject", flat=True)
        .first()
    ) or "Academic writing"

    summary = {
        "task_count": total_count,
        "open_count": counts["open_count"],
        "draft_count": counts["draft_count"],
        "assigned_count": counts["assigned_count"],
        "in_progress_count": counts["in_progress_count"],
        "review_count": counts["review_count"],
        "revision_count": counts["revision_count"],
        "completed_count": counts["completed_count"],
        "active_count": active_count,
        "escalated_count": counts["escalated_count"],
        "dispute_count": dispute_count,
        "average_rating": round(average_rating, 1),
        "average_accuracy": round(average_accuracy, 1),
        "health_score": health_score,
        "health_color": health_color,
        "engagement_level": engagement_level,
    }
    return {
        "tasks": tasks,
        "summary": summary,
        "subject_breakdown": subject_breakdown,
        "focus_subject": focus_subject,
    }


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
    """Assignment health score for the current user."""
    if not _has_assignment_insights_access(request.user):
        return _assignment_insights_locked_response()

    metrics = _assignment_context_for_user(request.user)
    summary = metrics["summary"]
    return Response({
        "health_score": summary["health_score"],
        "health_color": summary["health_color"],
        "engagement_level": summary["engagement_level"],
        "summary": summary,
        "average_rating": summary["average_rating"],
        "average_accuracy": summary["average_accuracy"],
        "dispute_count": summary["dispute_count"],
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def usage_view(request):
    """Assignment usage data for the current user."""
    if not _has_assignment_insights_access(request.user):
        return _assignment_insights_locked_response()

    metrics = _assignment_context_for_user(request.user)
    summary = metrics["summary"]
    status_breakdown = [
        {"status": TaskOrder.Status.DRAFT, "label": "Draft", "count": summary["draft_count"]},
        {"status": TaskOrder.Status.OPEN, "label": "Open", "count": summary["open_count"]},
        {"status": TaskOrder.Status.ASSIGNED, "label": "Assigned", "count": summary["assigned_count"]},
        {"status": TaskOrder.Status.IN_PROGRESS, "label": "In progress", "count": summary["in_progress_count"]},
        {"status": TaskOrder.Status.QUALITY_REVIEW, "label": "Quality review", "count": summary["review_count"]},
        {"status": TaskOrder.Status.REVISION, "label": "Revision", "count": summary["revision_count"]},
        {"status": TaskOrder.Status.COMPLETED, "label": "Completed", "count": summary["completed_count"]},
        {"status": TaskOrder.Status.ESCALATED, "label": "Escalated", "count": summary["escalated_count"]},
    ]
    subject_breakdown = metrics["subject_breakdown"]
    return Response({
        "summary": summary,
        "status_breakdown": status_breakdown,
        "subject_breakdown": subject_breakdown,
        "features": [
            {"name": "open_assignments", "count": summary["open_count"]},
            {"name": "active_assignments", "count": summary["active_count"]},
            {"name": "completed_assignments", "count": summary["completed_count"]},
        ],
        "usage_forecast": {
            "assignment_load": summary["active_count"] + summary["open_count"],
            "focus_subject": metrics["focus_subject"],
        },
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def recommendations_view(request):
    """Assignment recommendations for the current user."""
    if not _has_assignment_insights_access(request.user):
        return _assignment_insights_locked_response()

    role = get_platform_role(request.user)
    metrics = _assignment_context_for_user(request.user)
    subject = request.GET.get("subject", "").strip() or metrics["focus_subject"]

    if role == "student":
        recommendations = [
            {
                "tasker_id": item["tasker"].id,
                "username": item["tasker"].user.username,
                "display_name": item["tasker"].user.get_full_name() or item["tasker"].user.username,
                "region_name": item["region_name"],
                "score": item["score"],
                "reason": item["reason"],
                "specialties": item["specialties"],
                "trust_score": item["trust_score"],
                "quality_score": item["quality_score"],
                "availability_hours": item["availability_hours"],
            }
            for item in recommend_taskers_for_subject(
                subject,
                matching_mode=subscription_matching_mode(request.user),
            )
        ]
    elif role == "tasker":
        recommendations = TaskOrderSerializer(
            metrics["tasks"].filter(status=TaskOrder.Status.OPEN).order_by("-created_at")[:10],
            many=True,
        ).data
    else:
        open_escalations = EscalationCase.objects.filter(status=EscalationCase.Status.OPEN).select_related("task", "region").order_by("-opened_at")[:10]
        recommendations = [
            {
                "id": escalation.id,
                "task_title": escalation.task.title,
                "reason": escalation.reason,
                "priority": escalation.priority,
                "region": escalation.region.name if escalation.region else None,
                "opened_at": escalation.opened_at,
            }
            for escalation in open_escalations
        ]

    return Response({
        "role": role,
        "subject": subject,
        "recommendations": recommendations,
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
    metrics = _assignment_context_for_user(request.user)
    summary = metrics["summary"]
    subscription = user_subscription_plan(request.user)
    return Response({
        "summary": {
            "role": role,
            "task_count": summary["task_count"],
            "open_count": summary["open_count"],
            "assigned_count": summary["assigned_count"],
            "completed_count": summary["completed_count"],
            "active_count": summary["active_count"],
            "dispute_count": summary["dispute_count"],
        },
        "analytics": {
            "assignment_health": summary["health_score"],
            "health_color": summary["health_color"],
            "engagement_level": summary["engagement_level"],
            "average_rating": summary["average_rating"],
            "average_accuracy": summary["average_accuracy"],
        },
        "feature_access": {
            "assignment_insights": _has_assignment_insights_access(request.user),
            "writer_recommendations": bool(subscription and subscription.has_feature("subject_recommendations")),
            "manager_console": bool(role in {"manager", "admin"} or (subscription and subscription.has_feature("manager_console"))),
            "analytics_level": subscription_analytics_access_level(request.user),
            "active_task_limit": subscription_active_task_limit(request.user),
            "turnaround_hours": subscription_turnaround_hours(request.user),
            "matching_mode": subscription_matching_mode(request.user),
            "session_mode": subscription_session_mode(request.user),
            "premium_session_access": subscription_session_mode(request.user) == "premium",
            "support_channel": subscription_support_channel(request.user),
        },
        "subscription": subscription.serialize() if subscription else None,
    })


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def marketplace_tasks_view(request):
    """
    Assignment tasks API.
    GET - list tasks filtered by role, with optional ?q= search.
    POST - create a new draft task.
    """
    TaskSerializer = TaskOrderSerializer

    if request.method == 'GET':
        role = get_platform_role(request.user)
        tasks = _marketplace_tasks_for_user(request.user).order_by("-created_at")

        # Assignment search filtering
        query = request.GET.get('q', '').strip()
        if query:
            tasks = tasks.filter(
                Q(title__icontains=query) |
                Q(subject__icontains=query) |
                Q(description__icontains=query)
            )
            
        serializer = TaskSerializer(tasks[:50], many=True)
        return Response({"role": role, "tasks": serializer.data})

    # POST — create
    if get_platform_role(request.user) not in {"student", "admin"}:
        return Response({"detail": "Only students can create tasks."}, status=status.HTTP_403_FORBIDDEN)

    serializer = TaskSerializer(data=request.data)
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
    focus = infer_interview_focus(application)
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
        "interview_focus": {
            "field": focus["field"],
            "topic": focus["topic"],
            "competency_names": focus["competency_names"],
        },
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


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def notification_mark_read_view(request):
    """Mark a single notification as read."""
    notif_id = request.data.get('id')
    if not notif_id:
        return Response({"detail": "Notification ID is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        notif = TaskNotification.objects.get(pk=notif_id, recipient=request.user)
    except TaskNotification.DoesNotExist:
        return Response({"detail": "Notification not found."}, status=status.HTTP_404_NOT_FOUND)

    notif.is_read = True
    notif.save(update_fields=['is_read'])
    return Response({"status": "ok", "message": "Notification dismissed."})


# Interactive Interview APIs

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_interview_session_view(request):
    """Create a new interactive interview session."""
    try:
        application, _ = TaskerApplication.objects.get_or_create(applicant=request.user)
        
        field = request.data.get('field') or None
        difficulty = request.data.get('difficulty')
        language = request.data.get('language', '')
        
        if not difficulty:
            return Response(
                {"detail": "difficulty is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        session = create_interactive_interview_session(
            application=application,
            field=field,
            difficulty=difficulty,
            language=language
        )
        
        return Response({
            "session_id": session.id,
            "field": session.get_field_display(),
            "focus_topic": (session.metadata or {}).get("focus_topic"),
            "difficulty": session.difficulty,
            "language": session.language,
            "status": session.status,
            "total_questions": session.total_questions,
            "message": "Interview session created. Call /api/interview/start/ to begin."
        }, status=status.HTTP_201_CREATED)
    
    except ValueError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_interview_view(request):
    """Start interview and generate first question."""
    try:
        session_id = request.data.get('session_id')
        if not session_id:
            return Response(
                {"detail": "session_id is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = start_interactive_interview(session_id)
        
        return Response({
            "session_id": result["session"].id,
            "status": result["session"].status,
            "question_number": result["question"].question_number,
            "question": result["question"].question_text,
            "expected_concepts": result["question"].expected_concepts,
            "time_limit_minutes": result["question"].time_limit_minutes,
            "message": "Interview started. Submit your answer to /api/interview/submit-answer/"
        })
    
    except InteractiveInterviewSession.DoesNotExist:
        return Response({"detail": "Interview session not found."}, status=status.HTTP_404_NOT_FOUND)
    except ValueError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_answer_view(request):
    """Submit answer and get verification."""
    try:
        session_id = request.data.get('session_id')
        question_number = request.data.get('question_number')
        user_answer = request.data.get('answer')
        
        if not all([session_id, question_number, user_answer]):
            return Response(
                {"detail": "session_id, question_number, and answer are required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = submit_interview_answer(session_id, question_number, user_answer)
        
        response_data = {
            "question_number": result["question"].question_number,
            "your_answer": result["question"].user_answer,
            "is_correct": result["question"].is_correct,
            "correctness_score": result["question"].correctness_score,
            "explanation": result["question"].explanation,
            "strengths": result["question"].strengths,
            "weaknesses": result["question"].weaknesses,
            "feedback": result["question"].feedback,
            "progress": result["session_progress"],
        }
        
        if result["session_progress"]["should_proceed"]:
            response_data["message"] = "Answer verified. Call /api/interview/next-question/ for the next question."
        else:
            response_data["message"] = "Interview complete. Call /api/interview/complete/ to see results."
        
        return Response(response_data)
    
    except InteractiveInterviewSession.DoesNotExist:
        return Response({"detail": "Interview session not found."}, status=status.HTTP_404_NOT_FOUND)
    except InterviewQuestion.DoesNotExist:
        return Response({"detail": "Question not found."}, status=status.HTTP_404_NOT_FOUND)
    except ValueError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def next_question_view(request):
    """Get the next interview question."""
    try:
        session_id = request.data.get('session_id')
        if not session_id:
            return Response(
                {"detail": "session_id is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = get_next_interview_question(session_id)
        
        # If interview is complete
        if isinstance(result, dict) and "session" in result:
            return Response({
                "status": "completed",
                "final_score": result["final_score"],
                "recommendation": result["recommendation"],
                "percentile": result["percentile"],
                "total_questions": result["total_questions"],
            })
        
        return Response({
            "question_number": result["question"].question_number,
            "question": result["question"].question_text,
            "expected_concepts": result["question"].expected_concepts,
            "time_limit_minutes": result["question"].time_limit_minutes,
            "progress": result["progress"],
        })
    
    except InteractiveInterviewSession.DoesNotExist:
        return Response({"detail": "Interview session not found."}, status=status.HTTP_404_NOT_FOUND)
    except ValueError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def complete_interview_view(request):
    """Complete interview and get final results."""
    try:
        session_id = request.data.get('session_id')
        if not session_id:
            return Response(
                {"detail": "session_id is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = complete_interview(session_id)
        
        return Response({
            "session_id": result["session"].id,
            "status": result["session"].status,
            "field": result["session"].get_field_display(),
            "difficulty": result["session"].difficulty,
            "final_score": result["final_score"],
            "recommendation": result["recommendation"],
            "percentile": result["percentile"],
            "total_questions": result["total_questions"],
            "message": "Interview completed successfully!"
        })
    
    except InteractiveInterviewSession.DoesNotExist:
        return Response({"detail": "Interview session not found."}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def interview_progress_view(request):
    """Get current interview progress."""
    try:
        session_id = request.query_params.get('session_id')
        if not session_id:
            return Response(
                {"detail": "session_id is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        progress = get_interview_progress(session_id)
        return Response(progress)
    
    except InteractiveInterviewSession.DoesNotExist:
        return Response({"detail": "Interview session not found."}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
