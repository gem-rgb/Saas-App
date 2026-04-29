from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from agents.document_verification import verify_document_bundle
from agents.fraud_detection import assess_application_risk
from agents.interview_agent import run_interview_session
from trust.models import AIInterviewScore, AIInterviewSession, IdentityVerification, TaskerApplication


def evaluate_application(application):
    document_result = verify_document_bundle(application)
    risk_result = assess_application_risk(application, document_result=document_result)

    application.document_confidence = document_result["authenticity_confidence"]
    application.competency_confidence = document_result["competency_confidence"]
    application.fraud_risk_score = risk_result["risk_score"]
    application.manual_review_required = risk_result["manual_review_required"]
    application.trust_score = risk_result["trust_score"]
    application.decision_reason = risk_result["summary"]
    application.save(
        update_fields=[
            "document_confidence",
            "competency_confidence",
            "fraud_risk_score",
            "manual_review_required",
            "trust_score",
            "decision_reason",
            "updated_at",
        ]
    )

    identity, _ = IdentityVerification.objects.get_or_create(application=application)
    identity.authenticity_score = document_result["authenticity_confidence"]
    identity.document_match_score = document_result["document_match_score"]
    identity.face_match_score = document_result["face_match_score"]
    identity.liveness_score = document_result["liveness_score"]
    identity.review_notes = document_result["summary"]
    identity.status = IdentityVerification.Status.UNDER_REVIEW if risk_result["manual_review_required"] else IdentityVerification.Status.APPROVED
    if not risk_result["manual_review_required"]:
        identity.verified_at = timezone.now()
    identity.save()

    return {
        "document_result": document_result,
        "risk_result": risk_result,
        "identity": identity,
    }


@transaction.atomic
def run_ai_interview(application):
    interview_payload = run_interview_session(application)
    session = AIInterviewSession.objects.create(
        application=application,
        mode=interview_payload["mode"],
        transcript=interview_payload["transcript"],
        transcript_text=interview_payload["transcript_text"],
        technical_score=interview_payload["technical_score"],
        writing_score=interview_payload["writing_score"],
        behavioral_score=interview_payload["behavioral_score"],
        overall_score=interview_payload["overall_score"],
        recommendation=interview_payload["recommendation"],
        ranking_percentile=interview_payload["ranking_percentile"],
        interviewer_version=interview_payload["interviewer_version"],
        ended_at=timezone.now(),
        metadata=interview_payload.get("metadata", {}),
    )

    for item in interview_payload.get("scores", []):
        if item.get("competency_area") is None:
            continue
        AIInterviewScore.objects.create(
            session=session,
            competency_area=item["competency_area"],
            score=item["score"],
            evidence=item.get("evidence", ""),
            notes=item.get("notes", ""),
        )

    application.interview_confidence = session.overall_score
    application.save(update_fields=["interview_confidence", "updated_at"])
    return session


def score_application(application):
    base = 40.0
    base += application.document_confidence * 0.25
    base += application.competency_confidence * 0.25
    base += application.interview_confidence * 0.30
    base += application.trust_score * 0.20
    base -= application.fraud_risk_score * 0.18
    return max(0.0, min(100.0, round(base, 2)))


def is_tasker_ready(application):
    if application.status == TaskerApplication.Status.APPROVED:
        return True
    ready_states = {
        TaskerApplication.Status.SUBMITTED,
        TaskerApplication.Status.UNDER_REVIEW,
        TaskerApplication.Status.DOCUMENT_REVIEW,
        TaskerApplication.Status.INTERVIEW_PENDING,
    }
    return application.status in ready_states and score_application(application) >= 70

