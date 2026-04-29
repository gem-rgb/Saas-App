from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from marketplace.forms import (
    TaskAttachmentForm,
    TaskOrderForm,
    TaskRatingForm,
    TaskRevisionRequestForm,
    TaskSubmissionForm,
)
from marketplace.models import TaskOrder, TaskSubmission
from marketplace.permissions import get_platform_role, has_role, role_required
from marketplace.services import auto_assign_task, build_task_estimate, refresh_tasker_metrics
from helpers.paystack_billing import initialize_transaction
from django.urls import reverse
from django.conf import settings
from marketplace.models import TaskPayment


def _task_queryset_for_user(user):
    base = TaskOrder.objects.select_related(
        "student",
        "category",
        "competency_area",
        "assigned_tasker",
        "region_preference",
    ).prefetch_related("attachments", "match_suggestions", "submissions", "status_events", "ratings")
    if not user.is_authenticated:
        return base.none()
    role = get_platform_role(user)
    if role == "admin":
        return base
    if role == "manager":
        return base.filter(Q(status__in=[TaskOrder.Status.OPEN, TaskOrder.Status.ASSIGNED, TaskOrder.Status.IN_PROGRESS, TaskOrder.Status.QUALITY_REVIEW, TaskOrder.Status.REVISION, TaskOrder.Status.ESCALATED]))
    if role == "tasker" and hasattr(user, "tasker_profile"):
        return base.filter(Q(assigned_tasker=user.tasker_profile) | Q(match_suggestions__tasker=user.tasker_profile)).distinct()
    return base.filter(student=user)


@login_required
def board_view(request):
    tasks = _task_queryset_for_user(request.user).order_by("-created_at")
    role = get_platform_role(request.user)
    summary = {
        "open_tasks": tasks.filter(status=TaskOrder.Status.OPEN).count(),
        "assigned_tasks": tasks.filter(status=TaskOrder.Status.ASSIGNED).count(),
        "in_progress_tasks": tasks.filter(status=TaskOrder.Status.IN_PROGRESS).count(),
        "review_tasks": tasks.filter(status=TaskOrder.Status.QUALITY_REVIEW).count(),
        "completed_tasks": tasks.filter(status=TaskOrder.Status.COMPLETED).count(),
    }

    context = {
        "portal_role": role,
        "summary": summary,
        "tasks": tasks[:24],
        "task_form": TaskOrderForm(),
        "attachment_form": TaskAttachmentForm(),
        "submission_form": TaskSubmissionForm(),
        "revision_form": TaskRevisionRequestForm(),
        "rating_form": TaskRatingForm(),
    }
    return render(request, "marketplace/board.html", context)


@login_required
def task_create_view(request):
    if not has_role(request.user, "student", "admin"):
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
                amount_cents=task.budget_cents,  # Assuming budget_cents is populated by the estimator
                provider="paystack"
            )
            
            # Initialize Paystack checkout
            callback_url = request.build_absolute_uri(reverse("marketplace:task_detail", args=[task.pk]))
            try:
                # We assume budget_cents is the amount in smallest currency unit (e.g. Kobo for NGN)
                paystack_response = initialize_transaction(
                    email=request.user.email,
                    amount_minor=task.budget_cents,
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
    task = get_object_or_404(_task_queryset_for_user(request.user), pk=pk)
    context = {
        "task": task,
        "attachments": task.attachments.all(),
        "suggestions": task.match_suggestions.select_related("tasker", "tasker__user").all(),
        "submissions": task.submissions.select_related("tasker", "reviewed_by").all(),
        "events": task.status_events.all()[:12],
        "ratings": task.ratings.all(),
        "tasker_profile": getattr(request.user, "tasker_profile", None),
        "task_form": TaskOrderForm(instance=task),
        "attachment_form": TaskAttachmentForm(),
        "submission_form": TaskSubmissionForm(),
        "revision_form": TaskRevisionRequestForm(),
        "rating_form": TaskRatingForm(),
    }
    return render(request, "marketplace/task_detail.html", context)


@login_required
def task_publish_view(request, pk):
    task = get_object_or_404(TaskOrder, pk=pk, student=request.user)
    task.publish()
    result = auto_assign_task(task, actor=request.user)
    messages.success(request, f"Published {task.title} and generated {len(result['matches'])} AI match suggestions.")
    return redirect("marketplace:task_detail", pk=task.pk)


@login_required
def task_assign_view(request, pk):
    task = get_object_or_404(TaskOrder, pk=pk)
    if not has_role(request.user, "student", "manager", "admin"):
        messages.error(request, "You do not have permission to assign this task.")
        return redirect("marketplace:task_detail", pk=pk)

    result = auto_assign_task(task, actor=request.user, force=True)
    if result["matches"]:
        messages.success(request, f"Assigned to {result['matches'][0]['tasker'].user.username}.")
    else:
        messages.warning(request, "No eligible taskers were found.")
    return redirect("marketplace:task_detail", pk=pk)


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
            task.set_status(
                TaskOrder.Status.QUALITY_REVIEW,
                actor=request.user,
                actor_role="tasker",
                note="Task submitted for review",
                payload={"submission_id": submission.id},
            )
            messages.success(request, "Submission received and sent to quality review.")
            return redirect("marketplace:task_detail", pk=pk)
    else:
        form = TaskSubmissionForm()
    return render(request, "marketplace/task_submit.html", {"task": task, "form": form})


@login_required
def task_revision_view(request, pk):
    task = get_object_or_404(TaskOrder, pk=pk)
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
            task.set_status(
                TaskOrder.Status.COMPLETED,
                actor=request.user,
                actor_role=get_platform_role(request.user),
                note="Task rated and completed",
                payload={"rating_id": rating.id, "score": rating.overall_rating},
            )
            if task.assigned_tasker:
                refresh_tasker_metrics(task.assigned_tasker)
            messages.success(request, "Feedback saved.")
            return redirect("marketplace:task_detail", pk=pk)
    return redirect("marketplace:task_detail", pk=pk)
