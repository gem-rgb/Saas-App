from __future__ import annotations


def _competency_questions(application):
    competencies = list(application.competency_areas.all())[:5]
    questions = [
        {
            "speaker": "agent",
            "message": "Walk me through your process for delivering a high-stakes academic task under deadline pressure.",
        }
    ]
    for competency in competencies:
        questions.append(
            {
                "speaker": "agent",
                "message": f"Show us how you would approach a task in {competency.name} while protecting quality and originality.",
            }
        )
    questions.append(
        {
            "speaker": "agent",
            "message": "What would make you request a revision instead of shipping immediately?",
        }
    )
    return questions


def run_interview_session(application):
    competency_count = application.competency_areas.count()
    years = getattr(application, "years_experience", 0)
    document_confidence = getattr(application, "document_confidence", 0.0)
    competency_confidence = getattr(application, "competency_confidence", 0.0)
    trust_score = getattr(application, "trust_score", 0.0)

    technical_score = min(100.0, 30 + years * 9 + competency_count * 6 + competency_confidence * 0.35)
    writing_score = min(100.0, 38 + competency_count * 8 + document_confidence * 0.20)
    behavioral_score = min(100.0, 45 + trust_score * 0.30 + years * 4)
    overall_score = round((technical_score * 0.4) + (writing_score * 0.35) + (behavioral_score * 0.25), 2)

    if overall_score >= 82:
        recommendation = "strong_hire"
        percentile = 91.0
    elif overall_score >= 70:
        recommendation = "hire"
        percentile = 74.0
    elif overall_score >= 55:
        recommendation = "hold"
        percentile = 48.0
    else:
        recommendation = "reject"
        percentile = 18.0

    transcript = _competency_questions(application)
    transcript.append(
        {
            "speaker": "candidate",
            "message": "I keep a tight review loop, verify sources, and escalate when the brief is ambiguous.",
        }
    )
    transcript.append(
        {
            "speaker": "agent",
            "message": "Thank you. The interview will now be scored and ranked against the current pool.",
        }
    )

    scores = [
        {
            "competency_area": competency,
            "score": min(100.0, 60 + years * 5 + document_confidence * 0.2),
            "evidence": "Document and experience evidence reviewed.",
            "notes": "Auto-scored from interview pattern.",
        }
        for competency in application.competency_areas.all()
    ]

    return {
        "mode": "blended",
        "transcript": transcript,
        "transcript_text": "\n".join(f"{item['speaker']}: {item['message']}" for item in transcript),
        "technical_score": round(technical_score, 2),
        "writing_score": round(writing_score, 2),
        "behavioral_score": round(behavioral_score, 2),
        "overall_score": overall_score,
        "recommendation": recommendation,
        "ranking_percentile": percentile,
        "interviewer_version": "academy-agent-v1",
        "scores": scores,
        "metadata": {
            "competency_count": competency_count,
            "years_experience": years,
        },
    }

