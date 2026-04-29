from __future__ import annotations


def score_tasker_profile(tasker):
    quality = getattr(tasker, "quality_score", 0.0)
    on_time = getattr(tasker, "on_time_delivery_rate", 0.0)
    reliability = getattr(tasker, "reliability_score", 0.0)
    trust = getattr(tasker, "trust_score", 0.0)
    fraud = getattr(tasker, "fraud_risk_score", 0.0)
    revisions = getattr(tasker, "revision_frequency", 0.0)

    ranking_score = (
        quality * 0.30
        + on_time * 0.22
        + reliability * 0.20
        + trust * 0.22
        - fraud * 0.10
        - revisions * 0.06
    )
    return {
        "ranking_score": max(0.0, min(100.0, round(ranking_score, 2))),
        "quality": round(quality, 2),
        "on_time": round(on_time, 2),
        "reliability": round(reliability, 2),
        "trust": round(trust, 2),
        "fraud": round(fraud, 2),
        "revisions": round(revisions, 2),
    }

