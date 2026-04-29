from __future__ import annotations

import math
from datetime import timedelta

from django.db import transaction
from django.db.models import Avg, Count, F, Q, Sum
from django.utils import timezone

from marketplace.models import (
    TaskAuditEvent,
    TaskMatchSuggestion,
    TaskNotification,
    TaskOrder,
    TaskPayment,
)
from marketplace.permissions import can_receive_work, get_platform_role


def _tokenize(value):
    if not value:
        return set()
    normalized = value.replace("/", " ").replace("-", " ").replace(",", " ")
    return {token.strip().lower() for token in normalized.split() if token.strip()}


def build_task_estimate(task):
    complexity_hours = {
        TaskOrder.Complexity.ESSENTIAL: 4,
        TaskOrder.Complexity.STANDARD: 8,
        TaskOrder.Complexity.ADVANCED: 16,
        TaskOrder.Complexity.EXPERT: 24,
    }
    complexity_multiplier = {
        TaskOrder.Complexity.ESSENTIAL: 0.7,
        TaskOrder.Complexity.STANDARD: 1.0,
        TaskOrder.Complexity.ADVANCED: 1.4,
        TaskOrder.Complexity.EXPERT: 1.85,
    }
    hours = max(task.estimated_hours or 0, complexity_hours.get(task.complexity_level, 8))
    base_price = 6000
    estimated_price = int(base_price * complexity_multiplier.get(task.complexity_level, 1.0) + hours * 1200)

    urgency_score = 55.0
    if task.deadline:
        hours_until_deadline = max(0.0, (task.deadline - timezone.now()).total_seconds() / 3600)
        if hours_until_deadline <= 12:
            urgency_score = 18
        elif hours_until_deadline <= 24:
            urgency_score = 30
        elif hours_until_deadline <= 72:
            urgency_score = 52
        else:
            urgency_score = 78

    confidence = min(0.98, max(0.35, 0.52 + (urgency_score / 200)))
    task.estimated_hours = hours
    task.pricing_suggestion_cents = estimated_price
    task.deadline_feasibility_score = round(urgency_score, 2)
    task.assignment_confidence = round(confidence, 2)
    task.ai_estimate = {
        "estimated_hours": hours,
        "suggested_price_cents": estimated_price,
        "deadline_feasibility_score": task.deadline_feasibility_score,
        "assignment_confidence": task.assignment_confidence,
        "notes": [
            "Derived from task complexity, deadline pressure, and budget shape.",
        ],
    }
    task.save(
        update_fields=[
            "estimated_hours",
            "pricing_suggestion_cents",
            "deadline_feasibility_score",
            "assignment_confidence",
            "ai_estimate",
            "updated_at",
        ]
    )
    return task.ai_estimate


def rank_taskers(task, taskers=None, top_n=5):
    from assignments.models import TaskerProfile

    if taskers is None:
        taskers = TaskerProfile.objects.filter(
            is_active_tasker=True,
            admin_approved=True,
            kyc_status="approved",
        ).select_related("home_region", "source_application").prefetch_related("competency_areas")

    task_tokens = _tokenize(task.subject) | _tokenize(task.title)
    if task.category:
        task_tokens |= _tokenize(task.category.name)
    if task.competency_area:
        task_tokens |= _tokenize(task.competency_area.name)

    matches = []
    for tasker in taskers:
        if not can_receive_work(tasker):
            continue

        tasker_tokens = _tokenize(tasker.skills) | _tokenize(tasker.bio)
        tasker_tokens |= {token for area in tasker.competency_areas.all() for token in _tokenize(area.name)}

        competency_overlap = task_tokens & tasker_tokens
        competency_score = min(1.0, len(competency_overlap) / max(len(task_tokens) or 1, 1))

        trust_score = max(0.0, min(1.0, getattr(tasker, "trust_score", 0.0) / 100.0))
        quality_score = max(0.0, min(1.0, getattr(tasker, "quality_score", 0.0) / 100.0))
        speed_score = max(0.0, min(1.0, getattr(tasker, "on_time_delivery_rate", 0.0) / 100.0))
        reliability_score = max(0.0, min(1.0, getattr(tasker, "reliability_score", 0.0) / 100.0))

        availability_hours = max(0.0, getattr(tasker, "availability_hours_per_week", 0) - getattr(tasker, "current_workload_hours", 0.0))
        workload_score = min(1.0, availability_hours / max(task.estimated_hours or 1, 1))

        region_score = 0.5
        if task.region_preference and getattr(tasker, "home_region_id", None):
            if task.region_preference_id == tasker.home_region_id:
                region_score = 1.0
            elif getattr(task.region_preference, "timezone", None) and getattr(tasker.home_region, "timezone", None):
                region_score = 0.75 if task.region_preference.timezone == tasker.home_region.timezone else 0.4

        deadline_score = 0.6
        if task.deadline:
            hours_until_deadline = max(0.0, (task.deadline - timezone.now()).total_seconds() / 3600)
            if hours_until_deadline <= max(6, task.estimated_hours * 1.2):
                deadline_score = 1.0
            elif hours_until_deadline <= max(24, task.estimated_hours * 2):
                deadline_score = 0.82
            elif hours_until_deadline <= max(72, task.estimated_hours * 3):
                deadline_score = 0.68
            else:
                deadline_score = 0.55

        fraud_penalty = max(0.0, min(1.0, getattr(tasker, "fraud_risk_score", 0.0) / 100.0))
        revision_penalty = max(0.0, min(1.0, getattr(tasker, "revision_frequency", 0.0) / 100.0))

        score = (
            competency_score * 0.30
            + trust_score * 0.18
            + quality_score * 0.15
            + speed_score * 0.10
            + reliability_score * 0.10
            + workload_score * 0.10
            + region_score * 0.04
            + deadline_score * 0.03
            - fraud_penalty * 0.06
            - revision_penalty * 0.04
        )
        score = max(0.0, min(1.0, score))

        if score < 0.35:
            continue

        confidence = max(0.0, min(1.0, score + (competency_score * 0.08)))
        matches.append(
            {
                "tasker": tasker,
                "score": round(score, 4),
                "confidence": round(confidence, 4),
                "signals": {
                    "competency_score": round(competency_score, 4),
                    "trust_score": round(trust_score, 4),
                    "quality_score": round(quality_score, 4),
                    "speed_score": round(speed_score, 4),
                    "reliability_score": round(reliability_score, 4),
                    "workload_score": round(workload_score, 4),
                    "region_score": round(region_score, 4),
                    "deadline_score": round(deadline_score, 4),
                    "fraud_penalty": round(fraud_penalty, 4),
                    "revision_penalty": round(revision_penalty, 4),
                },
                "rationale": sorted(competency_overlap)[:8],
            }
        )

    matches.sort(key=lambda item: (item["score"], item["confidence"]), reverse=True)
    for idx, match in enumerate(matches[:top_n], start=1):
        match["ranking_position"] = idx
    return matches[:top_n]


@transaction.atomic
def auto_assign_task(task, actor=None, top_n=5, force=False):
    matches = rank_taskers(task, top_n=top_n)
    created_suggestions = []

    for match in matches:
        suggestion, _ = TaskMatchSuggestion.objects.update_or_create(
            task=task,
            tasker=match["tasker"],
            defaults={
                "score": match["score"],
                "confidence": match["confidence"],
                "ranking_position": match["ranking_position"],
                "state": TaskMatchSuggestion.SuggestionState.RECOMMENDED,
                "rationale": match["signals"],
                "ai_snapshot": {
                    "signals": match["signals"],
                    "rationale": match["rationale"],
                },
                "selected_by": "ai",
                "is_primary": match["ranking_position"] == 1,
            },
        )
        created_suggestions.append(suggestion)

    if matches and (force or matches[0]["score"] >= 0.55):
        winner = matches[0]
        task.assign_tasker(
            winner["tasker"],
            actor=actor,
            score=winner["score"],
            confidence=winner["confidence"],
            rationale=winner["signals"],
            selected_by="ai",
        )
        if task.status == TaskOrder.Status.OPEN:
            task.set_status(
                TaskOrder.Status.ASSIGNED,
                actor=actor,
                actor_role=get_platform_role(actor) if actor else "ai",
                note="Auto-dispatched by matching engine",
                payload={"tasker_id": winner["tasker"].id, "score": winner["score"]},
            )
        TaskNotification.objects.create(
            recipient=task.student,
            task=task,
            channel=TaskNotification.Channel.IN_APP,
            title=f"Task routed to {winner['tasker'].user.username}",
            body=f"AI assigned {task.title} with score {winner['score']:.2f}.",
            metadata={"tasker_id": winner["tasker"].id, "confidence": winner["confidence"]},
        )
        TaskAuditEvent.objects.create(
            actor=actor,
            actor_role=get_platform_role(actor) if actor else "ai",
            task=task,
            entity_type="task",
            entity_id=str(task.id),
            event_type="auto_assignment",
            payload={"tasker_id": winner["tasker"].id, "score": winner["score"], "confidence": winner["confidence"]},
        )
    else:
        task.set_status(
            TaskOrder.Status.OPEN,
            actor=actor,
            actor_role="ai",
            note="Task published but held for manual review due to low confidence",
            payload={"top_match_count": len(matches)},
        )

    return {
        "task": task,
        "matches": matches,
        "suggestions": created_suggestions,
    }


def refresh_tasker_metrics(tasker):
    from assignments.models import TaskerProfile

    if not isinstance(tasker, TaskerProfile):
        return {}

    completed_submissions = tasker.submissions.filter(status="approved")
    total_completed = completed_submissions.count()
    avg_quality = completed_submissions.aggregate(avg_quality=Avg("quality_score"))["avg_quality"] or 0.0
    avg_ai_quality = completed_submissions.aggregate(avg_ai=Avg("ai_quality_score"))["avg_ai"] or 0.0
    avg_rating = tasker.ratings.aggregate(avg_rating=Avg("overall_rating"))["avg_rating"] or 0.0
    revisions = tasker.submissions.filter(status="needs_revision").count()
    revisions_per_task = revisions / total_completed if total_completed else 0.0

    on_time_count = 0
    for submission in completed_submissions.select_related("task"):
        if submission.task.deadline and submission.reviewed_at and submission.reviewed_at <= submission.task.deadline:
            on_time_count += 1
    on_time_rate = (on_time_count / total_completed * 100.0) if total_completed else 0.0

    earnings = tasker.primary_tasks.filter(status=TaskOrder.Status.COMPLETED).aggregate(total=Sum("budget_cents"))["total"] or 0
    current_workload = tasker.primary_tasks.filter(
        status__in=[TaskOrder.Status.ASSIGNED, TaskOrder.Status.IN_PROGRESS, TaskOrder.Status.QUALITY_REVIEW, TaskOrder.Status.REVISION]
    ).aggregate(total=Sum("estimated_hours"))["total"] or 0

    reliability_score = min(100.0, (avg_quality * 0.4) + (avg_rating * 16) + (on_time_rate * 0.25))
    trust_score = min(
        100.0,
        max(
            0.0,
            (avg_quality * 0.35)
            + (avg_ai_quality * 0.20)
            + (avg_rating * 16)
            + (on_time_rate * 0.20)
            - (revisions_per_task * 18)
        ),
    )

    tasker.quality_score = round(avg_quality, 2)
    tasker.on_time_delivery_rate = round(on_time_rate, 2)
    tasker.revision_frequency = round(revisions_per_task * 100.0, 2)
    tasker.trust_score = round(trust_score, 2)
    tasker.reliability_score = round(reliability_score, 2)
    tasker.current_workload_hours = float(current_workload or 0)
    tasker.last_ai_score = round((trust_score + reliability_score) / 2, 2)
    tasker.save(
        update_fields=[
            "quality_score",
            "on_time_delivery_rate",
            "revision_frequency",
            "trust_score",
            "reliability_score",
            "current_workload_hours",
            "last_ai_score",
            "updated_at",
        ]
    )
    return {
        "quality_score": tasker.quality_score,
        "on_time_delivery_rate": tasker.on_time_delivery_rate,
        "revision_frequency": tasker.revision_frequency,
        "trust_score": tasker.trust_score,
        "reliability_score": tasker.reliability_score,
        "current_workload_hours": tasker.current_workload_hours,
        "last_ai_score": tasker.last_ai_score,
        "earnings_cents": earnings,
    }


def queue_notification(recipient, title, body, task=None, channel="in_app", metadata=None):
    return TaskNotification.objects.create(
        recipient=recipient,
        task=task,
        channel=channel,
        title=title,
        body=body,
        metadata=metadata or {},
    )


def log_audit(actor, event_type, task=None, entity_type="task", entity_id="", payload=None):
    return TaskAuditEvent.objects.create(
        actor=actor,
        actor_role=get_platform_role(actor) if actor else "system",
        task=task,
        entity_type=entity_type,
        entity_id=entity_id or (str(task.id) if task else ""),
        event_type=event_type,
        payload=payload or {},
    )


def release_payment(task, provider_reference="", amount_cents=None):
    payment = task.payments.order_by("-created_at").first()
    if payment is None:
        payment = TaskPayment.objects.create(
            task=task,
            amount_cents=amount_cents or task.budget_cents or 0,
            provider_reference=provider_reference,
            status=TaskPayment.Status.RELEASED,
            escrow_status="released",
            paid_at=timezone.now(),
            released_at=timezone.now(),
        )
    else:
        payment.status = TaskPayment.Status.RELEASED
        payment.escrow_status = "released"
        payment.provider_reference = provider_reference or payment.provider_reference
        payment.released_at = timezone.now()
        payment.save(update_fields=["status", "escrow_status", "provider_reference", "released_at", "updated_at"])
    task.payment_status = TaskOrder.PaymentStatus.RELEASED
    task.save(update_fields=["payment_status", "updated_at"])
    return payment

