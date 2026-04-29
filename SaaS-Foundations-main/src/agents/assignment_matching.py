from __future__ import annotations

from django.utils import timezone


def rank_taskers(task, taskers, top_n=5):
    task_tokens = _tokenize(task.title) | _tokenize(task.subject)
    if getattr(task, "category", None):
        task_tokens |= _tokenize(task.category.name)
    if getattr(task, "competency_area", None):
        task_tokens |= _tokenize(task.competency_area.name)

    ranked = []
    for tasker in taskers:
        competency_tokens = _tokenize(getattr(tasker, "skills", "")) | _tokenize(getattr(tasker, "bio", ""))
        competency_tokens |= {token for area in tasker.competency_areas.all() for token in _tokenize(area.name)}
        overlap = task_tokens & competency_tokens
        competency_score = len(overlap) / max(len(task_tokens) or 1, 1)
        trust_score = getattr(tasker, "trust_score", 0.0) / 100.0
        quality_score = getattr(tasker, "quality_score", 0.0) / 100.0
        speed_score = getattr(tasker, "on_time_delivery_rate", 0.0) / 100.0
        workload = max(0.0, getattr(tasker, "availability_hours_per_week", 0) - getattr(tasker, "current_workload_hours", 0.0))
        workload_score = min(1.0, workload / max(getattr(task, "estimated_hours", 1) or 1, 1))
        region_score = 0.5
        if getattr(task, "region_preference_id", None) and getattr(tasker, "home_region_id", None):
            region_score = 1.0 if task.region_preference_id == tasker.home_region_id else 0.5
        deadline_score = 0.5
        if getattr(task, "deadline", None):
            hours_left = max(0.0, (task.deadline - timezone.now()).total_seconds() / 3600)
            deadline_score = 1.0 if hours_left > getattr(task, "estimated_hours", 8) else 0.7

        final_score = (
            competency_score * 0.34
            + trust_score * 0.18
            + quality_score * 0.14
            + speed_score * 0.10
            + workload_score * 0.12
            + region_score * 0.06
            + deadline_score * 0.06
        )
        ranked.append(
            {
                "tasker": tasker,
                "score": round(final_score, 4),
                "confidence": round(min(1.0, final_score + competency_score * 0.08), 4),
                "signals": {
                    "competency_score": round(competency_score, 4),
                    "trust_score": round(trust_score, 4),
                    "quality_score": round(quality_score, 4),
                    "speed_score": round(speed_score, 4),
                    "workload_score": round(workload_score, 4),
                    "region_score": round(region_score, 4),
                    "deadline_score": round(deadline_score, 4),
                },
                "rationale": sorted(overlap),
            }
        )

    ranked.sort(key=lambda item: item["score"], reverse=True)
    for index, item in enumerate(ranked[:top_n], start=1):
        item["ranking_position"] = index
    return ranked[:top_n]


def _tokenize(text):
    normalized = (text or "").lower().replace("/", " ").replace("-", " ").replace(",", " ")
    return {token.strip() for token in normalized.split() if token.strip()}

