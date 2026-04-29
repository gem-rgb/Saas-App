from __future__ import annotations


def assess_application_risk(application, document_result=None):
    document_result = document_result or {}
    authenticity = document_result.get("authenticity_confidence", getattr(application, "document_confidence", 0.0))
    competency = document_result.get("competency_confidence", getattr(application, "competency_confidence", 0.0))
    interview = getattr(application, "interview_confidence", 0.0)
    trust = getattr(application, "trust_score", 0.0)
    years = getattr(application, "years_experience", 0)

    risk = 100.0 - ((authenticity * 0.30) + (competency * 0.25) + (interview * 0.20) + (trust * 0.25))
    if years >= 8 and authenticity < 60:
        risk += 8
    if years == 0 and competency > 70:
        risk += 7
    if document_result.get("manual_review_required"):
        risk += 10
    if len(document_result.get("suspicious_signals", [])) >= 2:
        risk += 10

    risk = max(0.0, min(100.0, risk))
    trust_score = max(0.0, min(100.0, 100.0 - risk + 8))
    manual_review_required = risk >= 42 or document_result.get("manual_review_required", False)

    summary = "Risk score within acceptable bounds."
    if risk >= 70:
        summary = "High risk signals detected."
    elif risk >= 42:
        summary = "Manual review recommended."

    return {
        "risk_score": round(risk, 2),
        "trust_score": round(trust_score, 2),
        "manual_review_required": manual_review_required,
        "summary": summary,
    }


def detect_tasker_risk(tasker):
    kyc_ok = getattr(tasker, "kyc_status", "") == "approved"
    interview_ok = getattr(tasker, "interview_status", "") in {"passed", "approved"}
    admin_ok = getattr(tasker, "admin_approved", False)
    trust_score = getattr(tasker, "trust_score", 0.0)
    fraud = getattr(tasker, "fraud_risk_score", 0.0)

    risk = 100.0 - (trust_score * 0.55)
    if not kyc_ok:
        risk += 12
    if not interview_ok:
        risk += 10
    if not admin_ok:
        risk += 8
    risk += fraud * 0.25

    return {
        "risk_score": max(0.0, min(100.0, round(risk, 2))),
        "manual_review_required": risk >= 50,
    }

