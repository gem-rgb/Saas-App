from __future__ import annotations


FIELD_KEYWORDS = {
    "software_engineering": (
        "software engineering",
        "software",
        "programming",
        "coding",
        "computer science",
        "computer-science",
        "developer",
        "development",
        "web",
        "algorithm",
    ),
    "data_science": (
        "data science",
        "machine learning",
        "machine-learning",
        "ml",
        "analytics",
        "data analysis",
        "sql",
        "data",
    ),
    "chemistry": (
        "chemistry",
        "chemical",
        "biochemistry",
        "organic chemistry",
        "inorganic chemistry",
    ),
    "biology": (
        "biology",
        "life sciences",
        "life-sciences",
        "anatomy",
        "physiology",
        "microbiology",
        "biological",
    ),
    "mathematics": (
        "mathematics",
        "math",
        "algebra",
        "calculus",
        "geometry",
        "probability",
        "statistics",
    ),
}

FIELD_OPENERS = {
    "software_engineering": (
        "Walk me through how you would handle a {topic} assignment in software engineering "
        "while keeping the work clean, original, and correct."
    ),
    "data_science": (
        "Walk me through how you would handle a {topic} task in data science while validating your analysis and results."
    ),
    "chemistry": (
        "Walk me through how you would handle a {topic} question in chemistry while keeping the reasoning scientifically sound."
    ),
    "biology": (
        "Walk me through how you would handle a {topic} task in biology while keeping the explanation accurate."
    ),
    "mathematics": (
        "Walk me through how you would solve a {topic} problem step by step and verify the result."
    ),
    "general_knowledge": (
        "Walk me through how you would handle a {topic} assignment under deadline pressure while keeping the work original and accurate."
    ),
}


def _competency_areas(source):
    if source is None:
        return []
    if hasattr(source, "all"):
        return list(source.all())
    return list(source)


def _competency_text(area) -> str:
    parts = [
        getattr(area, "name", ""),
        getattr(area, "slug", ""),
        getattr(area, "description", ""),
    ]
    return " ".join(part for part in parts if part).lower()


def _keyword_score(text: str, keywords: tuple[str, ...]) -> int:
    score = 0
    for keyword in keywords:
        if keyword in text:
            score += 2 if " " in keyword else 1
    return score


def infer_interview_focus(application) -> dict:
    """Infer the best interview field and topic from the tasker's competencies."""
    areas = _competency_areas(getattr(application, "competency_areas", None))
    if not areas:
        return {
            "field": "general_knowledge",
            "topic": "academic writing",
            "competency_names": [],
            "competency_slugs": [],
        }

    field_scores = {field: 0 for field in FIELD_KEYWORDS}
    area_matches = []
    for index, area in enumerate(areas):
        text = _competency_text(area)
        scores = {field: _keyword_score(text, keywords) for field, keywords in FIELD_KEYWORDS.items()}
        best_field = max(scores, key=scores.get)
        best_score = scores[best_field]
        area_matches.append(
            {
                "index": index,
                "area": area,
                "scores": scores,
            }
        )
        if best_score > 0:
            field_scores[best_field] += best_score

    inferred_field = max(field_scores, key=field_scores.get) if max(field_scores.values()) > 0 else "general_knowledge"
    field_candidates = [item for item in area_matches if item["scores"].get(inferred_field, 0) > 0]
    if field_candidates:
        primary_area = max(
            field_candidates,
            key=lambda item: (item["scores"][inferred_field], -item["index"]),
        )["area"]
    else:
        primary_area = areas[0]

    return {
        "field": inferred_field,
        "topic": getattr(primary_area, "name", "academic writing") or "academic writing",
        "competency_names": [getattr(area, "name", "") for area in areas if getattr(area, "name", "")],
        "competency_slugs": [getattr(area, "slug", "") for area in areas if getattr(area, "slug", "")],
    }


def _opening_question(field: str, topic: str) -> str:
    template = FIELD_OPENERS.get(field, FIELD_OPENERS["general_knowledge"])
    return template.format(topic=topic or "academic writing")


def _competency_questions(application, focus: dict | None = None):
    competencies = _competency_areas(application.competency_areas)[:5]
    focus = focus or infer_interview_focus(application)
    topic = focus.get("topic") or "academic writing"
    questions = [
        {
            "speaker": "agent",
            "message": _opening_question(focus.get("field", "general_knowledge"), topic),
        }
    ]
    for competency in competencies:
        competency_name = getattr(competency, "name", "this competency")
        if competency_name == topic:
            message = (
                f"What evidence would show that your {competency_name} work is ready to submit without another revision?"
            )
        else:
            message = (
                f"Show us how you would approach a {competency_name} task while protecting quality and originality."
            )
        questions.append(
            {
                "speaker": "agent",
                "message": message,
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
    competencies = _competency_areas(application.competency_areas)
    competency_count = len(competencies)
    focus = infer_interview_focus(application)
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

    transcript = _competency_questions(application, focus=focus)
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
            "evidence": f"Interview focused on {focus['topic']}.",
            "notes": "Auto-scored from field-aligned interview pattern.",
        }
        for competency in competencies
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
            "focus_field": focus["field"],
            "focus_topic": focus["topic"],
            "competency_names": focus["competency_names"],
        },
    }
