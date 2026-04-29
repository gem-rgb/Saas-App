from __future__ import annotations

from collections import Counter
from hashlib import sha256


SUSPICIOUS_TERMS = {
    "fake",
    "sample",
    "template",
    "demo",
    "edited",
    "placeholder",
    "forged",
    "test copy",
}


def _text_tokens(text):
    normalized = (text or "").lower().replace("/", " ").replace("-", " ").replace(",", " ")
    return {token.strip() for token in normalized.split() if token.strip()}


def _document_hash(document):
    if not getattr(document, "file", None):
        return ""
    try:
        hasher = sha256()
        for chunk in document.file.chunks():
            hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return ""


def verify_document_bundle(application):
    documents = list(application.documents.all())
    if not documents:
        return {
            "authenticity_confidence": 18.0,
            "competency_confidence": 12.0,
            "document_match_score": 0.0,
            "face_match_score": 0.0,
            "liveness_score": 0.0,
            "summary": "No supporting documents were uploaded.",
            "manual_review_required": True,
            "suspicious_signals": ["missing_documents"],
        }

    signals = []
    file_types = Counter(doc.document_type for doc in documents)
    authenticity = 46.0
    competency = 32.0
    face_match = 35.0
    liveness = 33.0
    document_match = 28.0

    if file_types.get("resume"):
        authenticity += 12
        competency += 10
    else:
        signals.append("resume_missing")

    if file_types.get("government_id"):
        authenticity += 16
        face_match += 24
        document_match += 26
    else:
        signals.append("government_id_missing")

    if file_types.get("selfie"):
        authenticity += 8
        liveness += 28
    else:
        signals.append("selfie_missing")

    if file_types.get("certificate") or file_types.get("credential"):
        authenticity += 10
        competency += 16

    if file_types.get("portfolio"):
        authenticity += 6
        competency += 12

    if getattr(application, "years_experience", 0) >= 5:
        competency += 10
        authenticity += 4
    elif getattr(application, "years_experience", 0) >= 2:
        competency += 6

    applicant_name = " ".join(filter(None, [application.applicant.first_name, application.applicant.last_name, application.applicant.username])).strip().lower()
    for document in documents:
        extracted = (document.extracted_text or "").lower()
        doc_tokens = _text_tokens(extracted)
        if applicant_name and not any(part in extracted for part in applicant_name.split()):
            signals.append(f"name_mismatch_{document.document_type}")
            authenticity -= 6
        if any(term in extracted for term in SUSPICIOUS_TERMS):
            signals.append(f"suspicious_term_{document.document_type}")
            authenticity -= 10
        if len(doc_tokens) >= 40:
            authenticity += 2
        if document.sha256_hash:
            authenticity += 1
        else:
            document.sha256_hash = _document_hash(document)

    if len(documents) >= 4:
        authenticity += 6
    if len(file_types) >= 3:
        competency += 8

    authenticity = max(0.0, min(100.0, authenticity))
    competency = max(0.0, min(100.0, competency))
    face_match = max(0.0, min(100.0, face_match))
    liveness = max(0.0, min(100.0, liveness))
    document_match = max(0.0, min(100.0, document_match))

    summary = "Documents appear consistent and sufficiently complete."
    manual_review_required = False
    if authenticity < 68 or competency < 55:
        manual_review_required = True
        summary = "One or more credentials require manual review."
    if signals:
        manual_review_required = True
        summary = "Signals detected: " + ", ".join(sorted(set(signals)))

    return {
        "authenticity_confidence": round(authenticity, 2),
        "competency_confidence": round(competency, 2),
        "document_match_score": round(document_match, 2),
        "face_match_score": round(face_match, 2),
        "liveness_score": round(liveness, 2),
        "summary": summary,
        "manual_review_required": manual_review_required,
        "suspicious_signals": sorted(set(signals)),
    }

