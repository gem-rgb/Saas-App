from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils import timezone

from auth.models import UserRole
from auth.permissions import has_any_role, portal_url_for_role, portal_url_for_user, require_any_role
from agents.verification_service import run_assignment_verification
from agents.rubric_utils import normalize_rubric
from marketplace.forms import (
    TaskAttachmentForm,
    TaskConversationMessageForm,
    TaskOrderForm,
    TaskPremiumSessionRequestForm,
    TaskRatingForm,
    TaskRevisionRequestForm,
    TaskSubmissionForm,
)
from marketplace.models import (
    TaskConversationMessage,
    TaskConversationReadState,
    TaskNotification,
    TaskOrder,
    TaskPayment,
    TaskPremiumSession,
    TaskSubmission,
)
from marketplace.permissions import can_receive_work, get_platform_role, has_role, role_required, tasker_has_active_work
from marketplace.services import auto_assign_task, build_task_estimate, refresh_tasker_metrics, recommend_task_rows_for_tasker, release_payment
from helpers.paystack_billing import initialize_transaction, verify_transaction
from django.urls import reverse
from django.conf import settings
from operations.models import EscalationCase
from subscriptions.utils import can_publish_task, student_active_task_count, subscription_active_task_limit, subscription_has_feature


def _task_queryset_for_user(user):
    base = TaskOrder.objects.select_related(
        "student",
        "category",
        "competency_area",
        "assigned_tasker",
        "region_preference",
    ).prefetch_related(
        "attachments",
        "match_suggestions",
        "submissions",
        "premium_sessions",
        "premium_sessions__payment",
        "status_events",
        "ratings",
    )
    if not user.is_authenticated:
        return base.none()
    role = get_platform_role(user)
    if role == "admin":
        return base
    if role == "manager_pending":
        return base.none()
    if role == "manager":
        return base.filter(Q(status__in=[TaskOrder.Status.OPEN, TaskOrder.Status.ASSIGNED, TaskOrder.Status.IN_PROGRESS, TaskOrder.Status.QUALITY_REVIEW, TaskOrder.Status.REVISION, TaskOrder.Status.ESCALATED]))
    if role == "tasker":
        tasker_profile = getattr(user, "tasker_profile", None)
        if tasker_profile and can_receive_work(tasker_profile):
            return base.filter(
                Q(status__in=[TaskOrder.Status.OPEN, TaskOrder.Status.ASSIGNED, TaskOrder.Status.IN_PROGRESS, TaskOrder.Status.QUALITY_REVIEW, TaskOrder.Status.REVISION])
                | Q(assigned_tasker=tasker_profile)
                | Q(match_suggestions__tasker=tasker_profile)
            ).distinct()
        if tasker_profile and tasker_has_active_work(tasker_profile):
            return base.filter(assigned_tasker=tasker_profile).distinct()
        return base.none()
    return base.filter(student=user)


def _task_chat_audience_choices(role):
    choices = [("shared", "Shared with student")]
    if role in {"tasker", "manager", "admin"}:
        choices.append(("team", "Task team only"))
    if role in {"manager", "admin"}:
        choices.append(("internal", "Managers only"))
    return choices


def _task_message_visibility(message):
    metadata = message.metadata if isinstance(message.metadata, dict) else {}
    return metadata.get("visibility", "shared")


def _task_chat_access(task, user):
    if not user.is_authenticated:
        return False

    role = get_platform_role(user)
    if role in {"manager", "admin"}:
        return True

    if task.status == TaskOrder.Status.DRAFT:
        return False

    if role == "student":
        return task.student_id == user.id

    if role == "tasker":
        tasker_profile = getattr(user, "tasker_profile", None)
        return bool(
            task.assigned_tasker_id
            and tasker_profile
            and task.assigned_tasker_id == tasker_profile.id
        )

    return False


def _task_detail_access_level(task, user):
    if not user.is_authenticated:
        return "none"

    role = get_platform_role(user)
    if role == "manager_pending":
        return "none"
    if role in {"manager", "admin"}:
        return "full"

    if task.status == TaskOrder.Status.DRAFT:
        if role == "student" and task.student_id == user.id:
            return "full"
        if role == "tasker":
            tasker_profile = getattr(user, "tasker_profile", None)
            if task.assigned_tasker_id and tasker_profile and task.assigned_tasker_id == tasker_profile.id:
                return "full"
        return "none"

    if role == "student":
        return "full" if task.student_id == user.id else "read_only"

    if role == "tasker":
        tasker_profile = getattr(user, "tasker_profile", None)
        if task.assigned_tasker_id and tasker_profile and task.assigned_tasker_id == tasker_profile.id:
            return "full"
        return "read_only"

    return "read_only"


def _visible_task_messages(task, user):
    if not _task_chat_access(task, user):
        return []

    role = get_platform_role(user)
    messages_qs = task.messages.select_related("sender").order_by("created_at")
    visible_messages = []
    for message in messages_qs:
        visibility = _task_message_visibility(message)
        if visibility == "internal" and role not in {"manager", "admin"}:
            continue
        if visibility == "team" and role not in {"tasker", "manager", "admin"}:
            continue
        visible_messages.append(message)
    return visible_messages


def _task_chat_read_state(task, user):
    return TaskConversationReadState.objects.filter(task=task, user=user).first()


def _task_chat_unread_count(task, user):
    if not _task_chat_access(task, user):
        return 0

    role = get_platform_role(user)
    read_state = _task_chat_read_state(task, user)
    last_read_at = read_state.last_read_at if read_state else None

    unread_count = 0
    for message in task.messages.select_related("sender").order_by("created_at"):
        visibility = _task_message_visibility(message)
        if visibility == "internal" and role not in {"manager", "admin"}:
            continue
        if visibility == "team" and role not in {"tasker", "manager", "admin"}:
            continue
        if message.sender_id == user.id:
            continue
        if last_read_at and message.created_at <= last_read_at:
            continue
        unread_count += 1
    return unread_count


def _mark_task_chat_seen(task, user):
    if not _task_chat_access(task, user):
        return

    TaskConversationReadState.objects.update_or_create(
        task=task,
        user=user,
        defaults={"last_read_at": timezone.now()},
    )


def _task_verification_rubric(task):
    metadata = task.metadata if isinstance(task.metadata, dict) else {}
    return normalize_rubric(metadata.get("verification_rubric"))


def _task_submission_verification_payload(submission):
    metadata = submission.metadata if isinstance(submission.metadata, dict) else {}
    verification = metadata.get("ai_verification")
    if not isinstance(verification, dict):
        return {}

    payload = dict(verification)
    raw_checks = verification.get("checks")
    checks = []
    criteria = []
    seen_criteria = set()

    if isinstance(raw_checks, list):
        for check in raw_checks:
            if not isinstance(check, dict):
                continue
            details = check.get("details")
            if not isinstance(details, dict):
                details = {}
            raw_criteria = details.get("criteria")
            if isinstance(raw_criteria, list):
                for criterion in raw_criteria:
                    if not isinstance(criterion, dict):
                        continue
                    criterion_key = (
                        criterion.get("name"),
                        tuple(criterion.get("required_terms") or []),
                    )
                    if criterion_key in seen_criteria:
                        continue
                    seen_criteria.add(criterion_key)
                    criteria.append(criterion)
            checks.append(
                {
                    "check_type": check.get("check_type", "general"),
                    "score": check.get("score", 0.0),
                    "details": details,
                    "issues": check.get("issues", []),
                    "suggestions": check.get("suggestions", []),
                    "passed": check.get("passed", False),
                }
            )

    payload.setdefault("source", "heuristic")
    payload.setdefault("overall_score", getattr(submission, "ai_quality_score", 0.0))
    payload.setdefault("passed", False)
    payload.setdefault("summary", submission.summary)
    payload.setdefault("issues", [])
    payload.setdefault("suggestions", [])
    payload.setdefault("grading_style", "")
    payload.setdefault("minimum_score", 70)
    payload["checks"] = checks
    payload["criteria"] = criteria
    return payload


def _enrich_task_submission(submission):
    submission.ai_verification = _task_submission_verification_payload(submission)
    return submission


def _can_request_revisions(user):
    role = get_platform_role(user)
    if role in {"manager", "admin"}:
        return True
    return subscription_has_feature(user, "revision_requests") or subscription_has_feature(user, "unlimited_revisions")


def _has_plagiarism_report_access(user):
    role = get_platform_role(user)
    if role in {"manager", "admin"}:
        return True
    return subscription_has_feature(user, "plagiarism_reports") or subscription_has_feature(user, "quality_reports")


def _has_premium_session_access(user):
    role = get_platform_role(user)
    if role in {"manager", "admin"}:
        return True
    return subscription_has_feature(user, "premium_sessions")


def _can_request_premium_session(user, task):
    if not user.is_authenticated or task.assigned_tasker_id is None:
        return False

    if get_platform_role(user) != "student":
        return False

    if task.student_id != user.id:
        return False

    if task.status not in {
        TaskOrder.Status.ASSIGNED,
        TaskOrder.Status.IN_PROGRESS,
        TaskOrder.Status.QUALITY_REVIEW,
        TaskOrder.Status.REVISION,
    }:
        return False

    return _has_premium_session_access(user)


def _premium_session_queryset_for_user(task, user):
    base = task.premium_sessions.select_related("student", "tasker", "payment").order_by("-created_at")
    role = get_platform_role(user)
    if role in {"manager", "admin"}:
        return base
    if role == "student":
        return base.filter(student=user)
    if role == "tasker":
        tasker_profile = getattr(user, "tasker_profile", None)
        if tasker_profile is None:
            return base.none()
        return base.filter(tasker=tasker_profile)
    return base.none()


@login_required
def board_view(request):
    role = get_platform_role(request.user)
    if role == "manager_pending":
        messages.info(request, "Complete manager onboarding before opening the operations board.")
        return redirect("operations:manager-onboarding")
    if role == "tasker":
        tasker_profile = getattr(request.user, "tasker_profile", None)
        if not can_receive_work(tasker_profile) and not tasker_has_active_work(tasker_profile):
            messages.info(request, "Complete trust onboarding before accessing the tasker portal.")
            return redirect("trust:onboarding")

    tasks = _task_queryset_for_user(request.user).order_by("-created_at")
    summary = {
        "open_tasks": tasks.filter(status=TaskOrder.Status.OPEN).count(),
        "assigned_tasks": tasks.filter(status=TaskOrder.Status.ASSIGNED).count(),
        "in_progress_tasks": tasks.filter(status=TaskOrder.Status.IN_PROGRESS).count(),
        "review_tasks": tasks.filter(status=TaskOrder.Status.QUALITY_REVIEW).count(),
        "completed_tasks": tasks.filter(status=TaskOrder.Status.COMPLETED).count(),
    }
    tasker_profile = getattr(request.user, "tasker_profile", None)

    context = {
        "portal_role": role,
        "summary": summary,
        "tasks": tasks[:24],
        "tasker_recommendation_rows": recommend_task_rows_for_tasker(tasker_profile) if role == "tasker" and can_receive_work(tasker_profile) else [],
        "task_form": TaskOrderForm(),
        "attachment_form": TaskAttachmentForm(),
        "submission_form": TaskSubmissionForm(),
        "revision_form": TaskRevisionRequestForm(),
        "rating_form": TaskRatingForm(),
    }
    return render(request, "marketplace/board.html", context)


@login_required
def task_create_view(request):
    if not has_any_role(request.user, [UserRole.RoleType.STUDENT, UserRole.RoleType.ADMIN]):
        messages.error(request, "Only students can create tasks in the marketplace.")
        return redirect("marketplace:board")

    if request.method == "POST":
        form = TaskOrderForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.student = request.user
            task.status = TaskOrder.Status.DRAFT
            task.save()
            build_task_estimate(task)
            
            # Create a TaskPayment record
            payment = TaskPayment.objects.create(
                task=task,
                amount_cents=task.effective_budget_cents,
                provider="paystack"
            )
            
            # Initialize Paystack checkout
            callback_url = request.build_absolute_uri(reverse("marketplace:task_detail", args=[task.pk]))
            try:
                # We use the AI-derived effective budget in the smallest currency unit.
                paystack_response = initialize_transaction(
                    email=request.user.email,
                    amount_minor=task.effective_budget_cents,
                    reference=str(payment.id),
                    callback_url=callback_url,
                    metadata={"task_id": task.id}
                )
                
                checkout_url = paystack_response.get("data", {}).get("authorization_url")
                if checkout_url:
                    payment.provider_reference = paystack_response.get("data", {}).get("reference")
                    payment.save()
                    return redirect(checkout_url)
            except Exception as e:
                messages.error(request, "Error initializing payment: " + str(e))
                return redirect("marketplace:task_detail", pk=task.pk)
                
            messages.success(request, "Task saved as draft and estimated by AI.")
            return redirect("marketplace:task_detail", pk=task.pk)
    else:
        form = TaskOrderForm()
    return render(request, "marketplace/task_form.html", {"form": form, "mode": "create"})


@login_required
def task_detail_view(request, pk):
    task = get_object_or_404(TaskOrder, pk=pk)
    portal_role = get_platform_role(request.user)
    tasker_profile = getattr(request.user, "tasker_profile", None)
    detail_access = _task_detail_access_level(task, request.user)
    if detail_access == "none":
        raise Http404
    full_access = detail_access == "full"
    tasker_ready = can_receive_work(tasker_profile) if portal_role == "tasker" else True
    tasker_has_work = tasker_has_active_work(tasker_profile) if portal_role == "tasker" else False
    chat_access = full_access and _task_chat_access(task, request.user)
    unread_count = _task_chat_unread_count(task, request.user) if chat_access else 0
    task_verification_rubric = _task_verification_rubric(task)
    revision_access = full_access and _can_request_revisions(request.user)
    plagiarism_report_access = full_access and _has_plagiarism_report_access(request.user)
    premium_session_access = full_access and _has_premium_session_access(request.user)
    premium_session_request_allowed = full_access and _can_request_premium_session(request.user, task)
    premium_session_form = TaskPremiumSessionRequestForm() if premium_session_request_allowed else None
    premium_sessions = _premium_session_queryset_for_user(task, request.user) if full_access else []
    dashboard_url = portal_url_for_user(request.user) if portal_role in {"student", "tasker", "manager", "admin"} else portal_url_for_role("student")
    conversation_form = None
    if chat_access:
        conversation_form = TaskConversationMessageForm(initial={"audience": "shared"})
        conversation_form.fields["audience"].choices = _task_chat_audience_choices(portal_role)
        if request.method == "GET":
            _mark_task_chat_seen(task, request.user)

    context = {
        "task": task,
        "portal_role": portal_role,
        "conversation_dashboard_url": dashboard_url,
        "conversation_dashboard_label": {
            "student": "Student Dashboard",
            "tasker": "Tasker Dashboard" if (tasker_ready or tasker_has_work) else "Trust Onboarding",
            "manager": "Manager Dashboard",
            "admin": "Admin Dashboard",
        }.get(portal_role, "Dashboard"),
        "conversation_unread_count": unread_count,
        "task_verification_rubric": task_verification_rubric,
        "attachments": task.attachments.all(),
        "suggestions": task.match_suggestions.select_related("tasker", "tasker__user").all() if full_access else [],
        "submissions": [_enrich_task_submission(submission) for submission in task.submissions.select_related("tasker", "reviewed_by").all()] if full_access else [],
        "events": task.status_events.all()[:12] if full_access else [],
        "ratings": task.ratings.all() if full_access else [],
        "tasker_profile": getattr(request.user, "tasker_profile", None),
        "task_form": TaskOrderForm(instance=task),
        "attachment_form": TaskAttachmentForm(),
        "submission_form": TaskSubmissionForm(),
        "revision_form": TaskRevisionRequestForm(),
        "premium_session_form": premium_session_form,
        "premium_session_access": premium_session_access,
        "premium_session_request_allowed": premium_session_request_allowed,
        "premium_sessions": premium_sessions,
        "rating_form": TaskRatingForm(),
        "chat_access": chat_access,
        "conversation_messages": _visible_task_messages(task, request.user) if chat_access else [],
        "conversation_form": conversation_form,
        "tasker_portal_ready": tasker_ready,
        "can_request_revision": revision_access,
        "plagiarism_report_access": plagiarism_report_access,
    }
    return render(request, "marketplace/task_detail.html", context)


@login_required
@require_POST
def task_publish_view(request, pk):
    task = get_object_or_404(TaskOrder, pk=pk, student=request.user)
    if not can_publish_task(request.user):
        limit = subscription_active_task_limit(request.user)
        active_count = student_active_task_count(request.user)
        remaining = max(0, (limit or 0) - active_count)
        messages.error(request, f"Your plan allows {limit} active tasks. You have {remaining} slots left.")
        return redirect("marketplace:task_detail", pk=task.pk)
    task.publish()
    result = auto_assign_task(task, actor=request.user)
    messages.success(request, f"Published {task.title} and generated {len(result['matches'])} AI match suggestions.")
    return redirect("marketplace:task_detail", pk=task.pk)


@login_required
@require_POST
def task_message_post_view(request, pk):
    task = get_object_or_404(TaskOrder, pk=pk)
    if not _task_chat_access(task, request.user):
        raise Http404

    portal_role = get_platform_role(request.user)
    form = TaskConversationMessageForm(request.POST)
    form.fields["audience"].choices = _task_chat_audience_choices(portal_role)

    if form.is_valid():
        audience = form.cleaned_data["audience"]
        TaskConversationMessage.objects.create(
            task=task,
            sender=request.user,
            channel=TaskConversationMessage.Channel.IN_APP,
            message=form.cleaned_data["message"],
            metadata={
                "visibility": audience,
                "sender_role": portal_role,
            },
        )
        if audience == "shared":
            messages.success(request, "Message shared with the student.")
        elif audience == "team":
            messages.success(request, "Task team note saved.")
        else:
            messages.success(request, "Manager note saved.")
        _mark_task_chat_seen(task, request.user)
    else:
        messages.error(request, "Please fix the message and try again.")

    return redirect("marketplace:task_detail", pk=pk)


@require_any_role(UserRole.RoleType.MANAGER, UserRole.RoleType.ADMIN)
@require_POST
@login_required
def task_assign_view(request, pk):
    task = get_object_or_404(TaskOrder, pk=pk)

    result = auto_assign_task(task, actor=request.user, force=True)
    if result["matches"]:
        messages.success(request, f"Assigned to {result['matches'][0]['tasker'].user.username}.")
    else:
        messages.warning(request, "No eligible taskers were found.")
    return redirect("marketplace:task_detail", pk=pk)


@require_any_role(UserRole.RoleType.TASKER, UserRole.RoleType.ADMIN)
@login_required
def task_submit_view(request, pk):
    task = get_object_or_404(TaskOrder, pk=pk)
    tasker_profile = getattr(request.user, "tasker_profile", None)
    if tasker_profile is None or task.assigned_tasker != tasker_profile:
        messages.error(request, "This task is not assigned to you.")
        return redirect("marketplace:task_detail", pk=pk)

    if request.method == "POST":
        form = TaskSubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.task = task
            submission.tasker = tasker_profile
            submission.version = task.submissions.filter(tasker=tasker_profile).count() + 1
            submission.status = TaskSubmission.Status.SUBMITTED
            submission.save()

            verification = run_assignment_verification(
                content=submission.submission_text or task.instructions or task.description,
                title=task.title,
                description=task.description,
                required_skills=task.subject,
                instructions=task.instructions,
                rubric=task.metadata.get("verification_rubric") if isinstance(task.metadata, dict) else None,
                author_id=request.user.id,
                submission_source="marketplace",
                source_object_id=task.id,
                submission_id=submission.id,
                metadata=submission.metadata if isinstance(submission.metadata, dict) else {},
            )
            submission.ai_quality_score = verification.get("overall_score", 0.0)
            submission.quality_score = verification.get("overall_score", 0.0)
            submission.summary = verification.get(
                "summary",
                "AI verification completed for the submitted work.",
            )
            submission.metadata = {
                **(submission.metadata or {}),
                "ai_verification": verification,
            }
            submission.save(
                update_fields=[
                    "ai_quality_score",
                    "quality_score",
                    "summary",
                    "metadata",
                ]
            )

            task.set_status(
                TaskOrder.Status.QUALITY_REVIEW,
                actor=request.user,
                actor_role="tasker",
                note="Task submitted for review",
                payload={"submission_id": submission.id},
            )
            if verification.get("passed", False):
                messages.success(
                    request,
                    f"Submission received, verified at {verification.get('overall_score', 0.0):.1f}/100, and sent to quality review.",
                )
            else:
                messages.warning(
                    request,
                    f"Submission received. AI verification scored {verification.get('overall_score', 0.0):.1f}/100 and flagged it for review.",
                )
            return redirect("marketplace:task_detail", pk=pk)
    else:
        form = TaskSubmissionForm()
    return render(
        request,
        "marketplace/task_submit.html",
        {
            "task": task,
            "form": form,
            "task_verification_rubric": _task_verification_rubric(task),
        },
    )


@login_required
def task_revision_view(request, pk):
    task = get_object_or_404(TaskOrder, pk=pk)
    role = get_platform_role(request.user)
    if task.student_id != request.user.id and role not in {"manager", "admin"}:
        messages.error(request, "You do not have permission to request a revision for this task.")
        return redirect("marketplace:task_detail", pk=pk)
    if role not in {"manager", "admin"} and not _can_request_revisions(request.user):
        messages.error(request, "Revision requests are available on Pro and Expert plans.")
        return redirect("marketplace:task_detail", pk=pk)

    if request.method == "POST":
        form = TaskRevisionRequestForm(request.POST)
        if form.is_valid():
            latest_submission = task.submissions.order_by("-submitted_at").first()
            if latest_submission is None:
                messages.error(request, "No submission exists yet.")
                return redirect("marketplace:task_detail", pk=pk)
            revision = form.save(commit=False)
            revision.submission = latest_submission
            revision.requested_by = request.user
            revision.save()
            task.revision_count += 1
            task.set_status(
                TaskOrder.Status.REVISION,
                actor=request.user,
                actor_role=get_platform_role(request.user),
                note="Revision requested",
                payload={"revision_request_id": revision.id},
            )
            messages.success(request, "Revision requested.")
            return redirect("marketplace:task_detail", pk=pk)
    return redirect("marketplace:task_detail", pk=pk)


@login_required
def task_rate_view(request, pk):
    task = get_object_or_404(TaskOrder, pk=pk)
    role = get_platform_role(request.user)
    if task.student_id != request.user.id and role not in {"manager", "admin"}:
        messages.error(request, "You do not have permission to rate this task.")
        return redirect("marketplace:task_detail", pk=pk)

    if task.assigned_tasker is None:
        messages.error(request, "This task has not been assigned yet.")
        return redirect("marketplace:task_detail", pk=pk)
    if request.method == "POST":
        form = TaskRatingForm(request.POST)
        if form.is_valid():
            rating = form.save(commit=False)
            rating.task = task
            rating.tasker = task.assigned_tasker
            rating.client = request.user
            rating.save()
            task.quality_score = rating.overall_rating * 20
            task.save(update_fields=["quality_score", "updated_at"])

            actor_role = get_platform_role(request.user)
            if rating.overall_rating <= 2 or rating.accuracy_rating <= 2:
                task.set_status(
                    TaskOrder.Status.ESCALATED,
                    actor=request.user,
                    actor_role=actor_role,
                    note="Low quality rating triggered a dispute review",
                    payload={"rating_id": rating.id, "score": rating.overall_rating},
                )
                EscalationCase.objects.create(
                    task=task,
                    region=task.region_preference,
                    opened_by=request.user,
                    status=EscalationCase.Status.OPEN,
                    priority=EscalationCase.Priority.HIGH,
                    reason=(
                        f"Poor assignment quality reported after rating {rating.overall_rating}/5 "
                        f"(accuracy {rating.accuracy_rating}/5)."
                    ),
                    metadata={
                        "rating_id": rating.id,
                        "accuracy_rating": rating.accuracy_rating,
                        "overall_rating": rating.overall_rating,
                    },
                )
                messages.warning(request, "The assignment was flagged for manager review and refund consideration.")
            else:
                task.set_status(
                    TaskOrder.Status.COMPLETED,
                    actor=request.user,
                    actor_role=actor_role,
                    note="Task rated and completed",
                    payload={"rating_id": rating.id, "score": rating.overall_rating},
                )
                release_payment(task)
                messages.success(request, "Feedback saved and payment released.")
            if task.assigned_tasker:
                refresh_tasker_metrics(task.assigned_tasker)
            return redirect("marketplace:task_detail", pk=pk)
    return redirect("marketplace:task_detail", pk=pk)


@login_required
@require_POST
def task_premium_session_request_view(request, pk):
    task = get_object_or_404(TaskOrder, pk=pk)
    if task.student_id != request.user.id:
        messages.error(request, "You can only request premium sessions for your own tasks.")
        return redirect("marketplace:task_detail", pk=pk)

    if not _can_request_premium_session(request.user, task):
        messages.error(request, "Premium sessions are included on the Expert plan and require an assigned tasker.")
        return redirect("marketplace:task_detail", pk=pk)

    if task.assigned_tasker is None:
        messages.error(request, "A tasker must be assigned before you can request a premium session.")
        return redirect("marketplace:task_detail", pk=pk)

    form = TaskPremiumSessionRequestForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please correct the premium session request details.")
        return redirect("marketplace:task_detail", pk=pk)

    session = form.save(commit=False)
    session.task = task
    session.student = request.user
    session.tasker = task.assigned_tasker
    session.status = TaskPremiumSession.Status.REQUESTED
    session.save()

    TaskNotification.objects.create(
        recipient=task.assigned_tasker.user,
        task=task,
        channel=TaskNotification.Channel.IN_APP,
        title="New premium session request",
        body=f"{request.user.get_full_name() or request.user.username} requested a {session.get_session_type_display().lower()} session for {task.title}.",
        metadata={
            "premium_session_id": session.id,
            "task_id": task.id,
            "session_type": session.session_type,
        },
    )
    TaskNotification.objects.create(
        recipient=request.user,
        task=task,
        channel=TaskNotification.Channel.IN_APP,
        title="Premium session requested",
        body="Your tasker has been notified and can accept the session request.",
        metadata={
            "premium_session_id": session.id,
            "task_id": task.id,
            "session_type": session.session_type,
        },
    )
    messages.success(request, "Premium session request sent to your tasker.")
    return redirect("marketplace:task_detail", pk=pk)


@login_required
@require_POST
def task_premium_session_accept_view(request, pk, session_id):
    task = get_object_or_404(TaskOrder, pk=pk)
    session = get_object_or_404(TaskPremiumSession, pk=session_id, task=task)
    role = get_platform_role(request.user)
    tasker_profile = getattr(request.user, "tasker_profile", None)

    if role not in {"tasker", "manager", "admin"}:
        messages.error(request, "Only the assigned tasker or a manager can accept this session.")
        return redirect("marketplace:task_detail", pk=pk)

    if role == "tasker" and (tasker_profile is None or session.tasker_id != tasker_profile.id):
        messages.error(request, "You are not assigned to this premium session.")
        return redirect("marketplace:task_detail", pk=pk)

    if session.status != TaskPremiumSession.Status.REQUESTED:
        messages.info(request, "This premium session has already been processed.")
        return redirect("marketplace:task_detail", pk=pk)

    payment = TaskPayment.objects.create(
        task=task,
        payment_kind=TaskPayment.PaymentKind.PREMIUM_SESSION,
        amount_cents=session.extra_fee_cents,
        currency=session.currency,
        provider="paystack",
        metadata={
            "premium_session_id": session.id,
            "task_id": task.id,
            "student_id": session.student_id,
            "tasker_id": session.tasker_id,
            "session_type": session.session_type,
            "topic": session.topic,
        },
    )

    try:
        callback_url = request.build_absolute_uri(
            reverse("marketplace:task_premium_session_finalize", args=[task.pk, session.pk])
        )
        paystack_response = initialize_transaction(
            email=session.student.email,
            amount_minor=session.extra_fee_cents,
            reference=str(payment.id),
            callback_url=callback_url,
            metadata={
                "task_id": task.id,
                "premium_session_id": session.id,
                "payment_kind": TaskPayment.PaymentKind.PREMIUM_SESSION,
                "payment_id": payment.id,
            },
        )
        authorization_url = paystack_response.get("data", {}).get("authorization_url")
        provider_reference = paystack_response.get("data", {}).get("reference") or str(payment.id)
        if not authorization_url:
            raise ValueError("Paystack did not return an authorization URL.")
    except Exception:
        payment.status = TaskPayment.Status.FAILED
        payment.metadata = {**(payment.metadata or {}), "error": "Failed to initialize premium session payment."}
        payment.save(update_fields=["status", "metadata"])
        messages.error(request, "Unable to start payment for this premium session. Please try again.")
        return redirect("marketplace:task_detail", pk=pk)

    payment.provider_reference = provider_reference
    payment.metadata = {
        **(payment.metadata or {}),
        "authorization_url": authorization_url,
        "payment_reference": provider_reference,
        "callback_url": callback_url,
    }
    payment.save(update_fields=["provider_reference", "metadata"])

    session.payment = payment
    session.provider_reference = provider_reference
    session.status = TaskPremiumSession.Status.AWAITING_PAYMENT
    session.accepted_at = timezone.now()
    session.metadata = {
        **(session.metadata or {}),
        "authorization_url": authorization_url,
        "payment_reference": provider_reference,
        "payment_id": payment.id,
    }
    session.save(update_fields=["payment", "provider_reference", "status", "accepted_at", "metadata", "updated_at"])

    TaskNotification.objects.create(
        recipient=session.student,
        task=task,
        channel=TaskNotification.Channel.IN_APP,
        title="Premium session accepted",
        body=f"Your {session.get_session_type_display().lower()} session request has been accepted. Complete payment to confirm the booking.",
        metadata={
            "premium_session_id": session.id,
            "task_id": task.id,
            "checkout_url": authorization_url,
            "payment_id": payment.id,
        },
    )
    messages.success(request, "Premium session accepted. The student can now complete payment.")
    return redirect("marketplace:task_detail", pk=pk)


@login_required
@require_POST
def task_premium_session_decline_view(request, pk, session_id):
    task = get_object_or_404(TaskOrder, pk=pk)
    session = get_object_or_404(TaskPremiumSession, pk=session_id, task=task)
    role = get_platform_role(request.user)
    tasker_profile = getattr(request.user, "tasker_profile", None)

    if role not in {"tasker", "manager", "admin"}:
        messages.error(request, "Only the assigned tasker or a manager can decline this session.")
        return redirect("marketplace:task_detail", pk=pk)

    if role == "tasker" and (tasker_profile is None or session.tasker_id != tasker_profile.id):
        messages.error(request, "You are not assigned to this premium session.")
        return redirect("marketplace:task_detail", pk=pk)

    if session.status != TaskPremiumSession.Status.REQUESTED:
        messages.info(request, "This premium session has already been processed.")
        return redirect("marketplace:task_detail", pk=pk)

    session.status = TaskPremiumSession.Status.DECLINED
    session.declined_at = timezone.now()
    session.save(update_fields=["status", "declined_at", "updated_at"])

    TaskNotification.objects.create(
        recipient=session.student,
        task=task,
        channel=TaskNotification.Channel.IN_APP,
        title="Premium session declined",
        body=f"Your {session.get_session_type_display().lower()} session request was declined by the tasker.",
        metadata={
            "premium_session_id": session.id,
            "task_id": task.id,
            "session_type": session.session_type,
        },
    )
    messages.success(request, "Premium session declined.")
    return redirect("marketplace:task_detail", pk=pk)


@login_required
def task_premium_session_checkout_view(request, pk, session_id):
    task = get_object_or_404(TaskOrder, pk=pk)
    session = get_object_or_404(TaskPremiumSession, pk=session_id, task=task)
    role = get_platform_role(request.user)

    if role != "student" or session.student_id != request.user.id:
        messages.error(request, "You can only pay for your own premium session requests.")
        return redirect("marketplace:task_detail", pk=pk)

    checkout_url = session.checkout_url
    if not checkout_url:
        messages.error(request, "The payment link is not ready yet.")
        return redirect("marketplace:task_detail", pk=pk)

    return redirect(checkout_url)


def task_premium_session_finalize_view(request, pk, session_id):
    task = get_object_or_404(TaskOrder, pk=pk)
    session = get_object_or_404(TaskPremiumSession, pk=session_id, task=task)
    reference = request.GET.get("reference") or request.GET.get("trxref")

    if not reference:
        messages.error(request, "Missing payment reference.")
        return redirect("marketplace:task_detail", pk=pk)

    try:
        verification = verify_transaction(reference)
        data = verification.get("data", {})
        if data.get("status") != "success":
            raise ValueError("Payment was not successful.")
    except Exception:
        messages.error(request, "Unable to verify premium session payment.")
        return redirect("marketplace:task_detail", pk=pk)

    if session.payment and session.payment.provider_reference and session.payment.provider_reference != reference:
        messages.error(request, "This payment reference does not match the selected premium session.")
        return redirect("marketplace:task_detail", pk=pk)

    payment = session.payment
    if payment is None:
        payment = task.payments.filter(provider_reference=reference, payment_kind=TaskPayment.PaymentKind.PREMIUM_SESSION).first()
    if payment is None:
        payment = task.payments.filter(provider_reference=reference).first()

    if payment is None or payment.payment_kind != TaskPayment.PaymentKind.PREMIUM_SESSION:
        messages.error(request, "No matching premium session payment was found.")
        return redirect("marketplace:task_detail", pk=pk)

    if session.payment_id and session.payment_id != payment.id:
        messages.error(request, "This payment does not belong to the selected premium session.")
        return redirect("marketplace:task_detail", pk=pk)

    session.payment = payment
    payment.status = TaskPayment.Status.AUTHORIZED
    payment.escrow_status = "held"
    payment.provider_reference = payment.provider_reference or reference
    payment.paid_at = payment.paid_at or timezone.now()
    payment.metadata = {
        **(payment.metadata or {}),
        "verified": True,
        "verified_at": timezone.now().isoformat(),
    }
    payment.save(update_fields=["status", "escrow_status", "provider_reference", "paid_at", "metadata"])

    session.status = TaskPremiumSession.Status.PAID
    session.paid_at = timezone.now()
    session.provider_reference = payment.provider_reference
    session.save(update_fields=["payment", "status", "paid_at", "provider_reference", "updated_at"])

    TaskNotification.objects.create(
        recipient=session.tasker.user,
        task=task,
        channel=TaskNotification.Channel.IN_APP,
        title="Premium session paid",
        body=f"{session.student.get_full_name() or session.student.username} completed payment for the premium session.",
        metadata={
            "premium_session_id": session.id,
            "task_id": task.id,
            "payment_id": payment.id,
        },
    )
    messages.success(request, "Premium session payment confirmed.")
    return redirect("marketplace:task_detail", pk=pk)


@login_required
@require_POST
def task_premium_session_complete_view(request, pk, session_id):
    task = get_object_or_404(TaskOrder, pk=pk)
    session = get_object_or_404(TaskPremiumSession, pk=session_id, task=task)
    role = get_platform_role(request.user)
    tasker_profile = getattr(request.user, "tasker_profile", None)

    if role not in {"student", "tasker", "manager", "admin"}:
        messages.error(request, "You do not have permission to complete this session.")
        return redirect("marketplace:task_detail", pk=pk)

    if role == "tasker" and (tasker_profile is None or session.tasker_id != tasker_profile.id):
        messages.error(request, "You are not assigned to this premium session.")
        return redirect("marketplace:task_detail", pk=pk)

    if role == "student" and session.student_id != request.user.id:
        messages.error(request, "You can only complete your own premium sessions.")
        return redirect("marketplace:task_detail", pk=pk)

    if session.status != TaskPremiumSession.Status.PAID:
        messages.error(request, "Premium sessions can only be completed after payment is confirmed.")
        return redirect("marketplace:task_detail", pk=pk)

    with transaction.atomic():
        session.status = TaskPremiumSession.Status.COMPLETED
        session.completed_at = timezone.now()
        session.save(update_fields=["status", "completed_at", "updated_at"])
        if session.payment_id:
            release_payment(
                task,
                amount_cents=session.extra_fee_cents,
                payment_id=session.payment_id,
                payment_kind=TaskPayment.PaymentKind.PREMIUM_SESSION,
            )

    TaskNotification.objects.create(
        recipient=session.student,
        task=task,
        channel=TaskNotification.Channel.IN_APP,
        title="Premium session completed",
        body=f"Your {session.get_session_type_display().lower()} session has been marked complete.",
        metadata={
            "premium_session_id": session.id,
            "task_id": task.id,
        },
    )
    messages.success(request, "Premium session marked complete and payment released.")
    return redirect("marketplace:task_detail", pk=pk)
