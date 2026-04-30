from __future__ import annotations

import copy
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


def _task_domain_premium(task):
    task_tokens = _tokenize(task.title) | _tokenize(task.subject) | _tokenize(task.description) | _tokenize(task.instructions)
    if task.category:
        task_tokens |= _tokenize(task.category.name)
    if task.competency_area:
        task_tokens |= _tokenize(task.competency_area.name)

    premium_rules = [
        ({"code", "coding", "programming", "software", "python", "javascript", "java", "algorithm", "api", "devops", "database", "machine", "learning", "web", "mobile"}, 1.45, "coding and software"),
        ({"engineering", "mechanical", "electrical", "civil", "chemical", "industrial", "robotics", "systems"}, 1.32, "engineering"),
        ({"architecture", "architectural", "design", "revit", "autocad", "blueprint", "construction", "3d"}, 1.30, "architecture"),
        ({"medicine", "medical", "health", "nursing", "pharmacy", "clinical", "anatomy", "biology"}, 1.34, "medicine and healthcare"),
        ({"law", "legal", "contract", "compliance", "policy", "litigation", "jurisprudence"}, 1.28, "law"),
        ({"research", "dissertation", "thesis", "essay", "writing", "editing", "proofreading", "literature"}, 1.16, "research and writing"),
        ({"business", "finance", "accounting", "economics", "analysis", "statistics", "spreadsheet"}, 1.20, "business and analytics"),
        ({"mathematics", "math", "calculus", "algebra", "geometry", "probability"}, 1.22, "mathematics"),
    ]

    best_factor = 1.0
    best_label = "general"
    for keywords, factor, label in premium_rules:
        if task_tokens & keywords and factor > best_factor:
            best_factor = factor
            best_label = label

    return best_factor, best_label


def _annotate_task_recommendation(task, score, reason, badge=None):
    annotated_task = copy.copy(task)
    annotated_task.recommendation_score = round(score * 100, 1)
    annotated_task.recommendation_reason = reason
    annotated_task.recommendation_badge = badge or task.price_source_label
    return annotated_task


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
    domain_multiplier, domain_label = _task_domain_premium(task)
    raw_estimated_price = (base_price * complexity_multiplier.get(task.complexity_level, 1.0) + hours * 1200) * domain_multiplier
    estimated_price = max(2500, int(round(raw_estimated_price / 500.0) * 500))
    if not task.budget_cents:
        task.budget_cents = estimated_price

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
        "domain_multiplier": round(domain_multiplier, 2),
        "domain_label": domain_label,
        "deadline_feasibility_score": task.deadline_feasibility_score,
        "assignment_confidence": task.assignment_confidence,
        "price_label": task.display_price_label,
        "price_source": task.price_source_label,
        "notes": [
            "Derived from task complexity, subject/domain premiums, deadline pressure, and budget shape.",
        ],
    }
    task.save(
        update_fields=[
            "estimated_hours",
            "budget_cents",
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


def _task_recommendation_score(task, tasker, focus_area=None, tasker_tokens=None):
    task_tokens = _tokenize(task.title) | _tokenize(task.subject) | _tokenize(task.description) | _tokenize(task.instructions)
    if task.category:
        task_tokens |= _tokenize(task.category.name)
    if task.competency_area:
        task_tokens |= _tokenize(task.competency_area.name)

    if tasker_tokens is None:
        tasker_tokens = _tokenize(getattr(tasker, "skills", "")) | _tokenize(getattr(tasker, "bio", ""))
        tasker_tokens |= {
            token
            for area in tasker.competency_areas.all()
            for token in (_tokenize(area.name) | _tokenize(area.description))
        }

    focus_tokens = set()
    if focus_area is not None:
        focus_tokens = _tokenize(focus_area.name) | _tokenize(focus_area.description)

    competency_overlap = task_tokens & tasker_tokens
    focus_overlap = task_tokens & focus_tokens

    competency_score = min(1.0, len(competency_overlap) / max(len(task_tokens) or 1, 1))
    focus_score = min(1.0, len(focus_overlap) / max(len(task_tokens) or 1, 1)) if focus_tokens else competency_score

    skill_rank = {
        "beginner": 0,
        "intermediate": 1,
        "advanced": 2,
        "expert": 3,
    }.get(getattr(tasker, "skill_level", "intermediate"), 1)
    complexity_rank = {
        TaskOrder.Complexity.ESSENTIAL: 0,
        TaskOrder.Complexity.STANDARD: 1,
        TaskOrder.Complexity.ADVANCED: 2,
        TaskOrder.Complexity.EXPERT: 3,
    }.get(task.complexity_level, 1)
    complexity_fit = 1.0 - (abs(skill_rank - complexity_rank) / 3.0)

    trust_score = max(0.0, min(1.0, getattr(tasker, "trust_score", 0.0) / 100.0))
    trust_fit = min(1.0, trust_score / max(task.required_trust_score / 100.0, 0.35))

    budget_score = min(1.0, (task.effective_budget_cents or 0) / 60000.0)
    hours_since_publish = None
    if task.published_at:
        hours_since_publish = max(0.0, (timezone.now() - task.published_at).total_seconds() / 3600.0)
    elif task.created_at:
        hours_since_publish = max(0.0, (timezone.now() - task.created_at).total_seconds() / 3600.0)
    recency_score = 0.75
    if hours_since_publish is not None:
        if hours_since_publish <= 6:
            recency_score = 1.0
        elif hours_since_publish <= 24:
            recency_score = 0.92
        elif hours_since_publish <= 72:
            recency_score = 0.80
        else:
            recency_score = 0.62

    score = (
        competency_score * 0.42
        + focus_score * 0.18
        + complexity_fit * 0.14
        + trust_fit * 0.10
        + budget_score * 0.10
        + recency_score * 0.06
    )
    score = max(0.0, min(1.0, score))

    reasons = []
    if focus_area is not None and focus_area.name not in reasons:
        reasons.append(focus_area.name)
    if task.competency_area and task.competency_area.name not in reasons:
        reasons.append(task.competency_area.name)
    if task.category and task.category.name not in reasons:
        reasons.append(task.category.name)
    if task.effective_budget_cents:
        reasons.append(task.display_price_label)
    return score, reasons


def recommend_task_rows_for_tasker(tasker, task_queryset=None, max_rows=3, row_size=8):
    from assignments.models import TaskerProfile

    if tasker is None or not isinstance(tasker, TaskerProfile):
        return []
    if task_queryset is None:
        task_queryset = TaskOrder.objects.filter(status=TaskOrder.Status.OPEN)
    task_queryset = (
        task_queryset.select_related("student", "category", "competency_area", "assigned_tasker", "region_preference")
        .prefetch_related("match_suggestions", "submissions")
    )
    task_pool = list(task_queryset)
    if not task_pool:
        return []

    tasker_areas = list(tasker.competency_areas.all())
    tasker_tokens = _tokenize(getattr(tasker, "skills", "")) | _tokenize(getattr(tasker, "bio", ""))
    tasker_tokens |= {
        token
        for area in tasker_areas
        for token in (_tokenize(area.name) | _tokenize(area.description))
    }
    rows = []

    def _top_scored(tasks, focus_area=None, title="", subtitle="", badge=None):
        scored = []
        for task in tasks:
            score, reasons = _task_recommendation_score(task, tasker, focus_area=focus_area, tasker_tokens=tasker_tokens)
            scored.append((score, reasons, task))
        scored.sort(key=lambda item: (item[0], item[2].effective_budget_cents), reverse=True)
        annotated_tasks = []
        for score, reasons, task in scored[:row_size]:
            annotated = _annotate_task_recommendation(
                task,
                score,
                ", ".join([reason for reason in reasons[:3] if reason]),
                badge=badge,
            )
            annotated_tasks.append(annotated)
        if annotated_tasks:
            rows.append(
                {
                    "title": title,
                    "subtitle": subtitle,
                    "tasks": annotated_tasks,
                }
            )

    _top_scored(
        task_pool,
        title="Top picks for you",
        subtitle="Ranked by your competency profile, trust readiness, and current payout.",
        badge="For you",
    )

    for area in tasker_areas[:2]:
        area_tokens = _tokenize(area.name) | _tokenize(area.description)
        area_tasks = [
            task
            for task in task_pool
            if task.competency_area_id == area.id
            or bool(
                (
                    _tokenize(task.title)
                    | _tokenize(task.subject)
                    | _tokenize(task.description)
                    | _tokenize(task.instructions)
                    | ( _tokenize(task.category.name) if task.category else set())
                    | ( _tokenize(task.competency_area.name) if task.competency_area else set())
                )
                & area_tokens
            )
        ]
        if not area_tasks:
            area_tasks = task_pool
        _top_scored(
            area_tasks,
            focus_area=area,
            title=f"Because you picked {area.name}",
            subtitle=area.description or "Tasks aligned to this competency area.",
            badge=area.name,
        )

    premium_tasks = sorted(
        task_pool,
        key=lambda task: (task.effective_budget_cents, task.complexity_level == TaskOrder.Complexity.EXPERT, task.complexity_level == TaskOrder.Complexity.ADVANCED),
        reverse=True,
    )
    if premium_tasks:
        _top_scored(
            premium_tasks,
            title="High-value work",
            subtitle="Higher payout tasks that fit your readiness level.",
            badge="Premium",
        )

    return rows[:max_rows]


def recommend_taskers_for_subject(subject, taskers=None, top_n=6):
    from assignments.models import TaskerProfile

    if not subject:
        return []

    if taskers is None:
        taskers = (
            TaskerProfile.objects.filter(
                is_active_tasker=True,
                admin_approved=True,
                kyc_status="approved",
                competency_status__in=["verified", "approved"],
                interview_status__in=["passed", "approved"],
            )
            .select_related("user", "home_region")
            .prefetch_related("competency_areas")
        )

    subject_tokens = _tokenize(subject)
    recommendations = []

    for tasker in taskers:
        if not can_receive_work(tasker):
            continue

        tasker_tokens = _tokenize(getattr(tasker, "skills", "")) | _tokenize(getattr(tasker, "bio", ""))
        tasker_tokens |= {
            token
            for area in tasker.competency_areas.all()
            for token in (_tokenize(area.name) | _tokenize(area.description))
        }

        overlap = subject_tokens & tasker_tokens
        overlap_score = len(overlap) / max(len(subject_tokens) or 1, 1)
        trust_score = max(0.0, min(1.0, getattr(tasker, "trust_score", 0.0) / 100.0))
        quality_score = max(0.0, min(1.0, getattr(tasker, "quality_score", 0.0) / 100.0))
        reliability_score = max(0.0, min(1.0, getattr(tasker, "reliability_score", 0.0) / 100.0))
        workload_headroom = max(0.0, getattr(tasker, "availability_hours_per_week", 0) - getattr(tasker, "current_workload_hours", 0.0))
        workload_score = min(1.0, workload_headroom / 20.0)

        score = (
            overlap_score * 0.45
            + trust_score * 0.20
            + quality_score * 0.15
            + reliability_score * 0.10
            + workload_score * 0.10
        )

        if score < 0.25:
            continue

        specialty_names = [area.name for area in tasker.competency_areas.all()[:4]]
        recommendations.append(
            {
                "tasker": tasker,
                "score": round(score * 100, 1),
                "reason": ", ".join(sorted(overlap)[:4]) if overlap else "Strong subject, trust, and workload fit",
                "specialties": specialty_names,
                "trust_score": round(getattr(tasker, "trust_score", 0.0), 1),
                "quality_score": round(getattr(tasker, "quality_score", 0.0), 1),
                "availability_hours": round(getattr(tasker, "availability_hours_per_week", 0) - getattr(tasker, "current_workload_hours", 0.0), 1),
                "region_name": tasker.home_region.name if getattr(tasker, "home_region", None) else "Global",
            }
        )

    recommendations.sort(key=lambda item: (item["score"], item["quality_score"], item["trust_score"]), reverse=True)
    return recommendations[:top_n]


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
            amount_cents=amount_cents or task.effective_budget_cents or 0,
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
