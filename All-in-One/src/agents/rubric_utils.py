from __future__ import annotations

import json
import re


_STOPWORDS = {
    "a",
    "an",
    "and",
    "answer",
    "be",
    "for",
    "from",
    "in",
    "include",
    "included",
    "including",
    "is",
    "must",
    "mention",
    "mentioned",
    "mentioning",
    "of",
    "provide",
    "provided",
    "providing",
    "show",
    "shown",
    "should",
    "state",
    "stated",
    "stating",
    "the",
    "cover",
    "covered",
    "covering",
    "describe",
    "described",
    "describing",
    "explain",
    "explained",
    "explaining",
    "give",
    "given",
    "giving",
    "list",
    "listed",
    "listing",
    "required",
    "to",
    "use",
    "with",
}


def _normalize_text(value) -> str:
    return str(value or "").strip().lower()


def _split_terms(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[,;\n]+", value)
        return [part.strip() for part in parts if part.strip()]
    if isinstance(value, dict):
        value = value.get("term") or value.get("keyword") or value.get("name") or value.get("label") or ""
        return _split_terms(value)
    if isinstance(value, (list, tuple, set)):
        terms: list[str] = []
        for item in value:
            terms.extend(_split_terms(item))
        return terms
    text = str(value).strip()
    return [text] if text else []


def _tokenize_words(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?", _normalize_text(text))
        if len(token) > 2 and token not in _STOPWORDS
    ]


def _match_term(text: str, term: str) -> bool:
    normalized_term = _normalize_text(term)
    if not normalized_term:
        return False
    if " " in normalized_term:
        return normalized_term in text
    return re.search(rf"\b{re.escape(normalized_term)}\b", text) is not None


def _bullet_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in str(text or "").splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        match = re.match(r"^(?:[-*•]|\d+[.)])\s*(.+)$", stripped)
        if match:
            candidate = match.group(1).strip()
        elif stripped.lower().startswith(("must ", "should ", "include ", "mention ", "cover ")):
            candidate = stripped
        else:
            candidate = ""
        if candidate:
            lines.append(candidate)
    return lines


def normalize_rubric(rubric) -> dict:
    if not rubric:
        return {}
    if isinstance(rubric, str):
        try:
            rubric = json.loads(rubric)
        except json.JSONDecodeError:
            return {}
    if not isinstance(rubric, dict):
        return {}

    title = str(rubric.get("title") or rubric.get("name") or "").strip()
    description = str(rubric.get("description") or rubric.get("instructions") or rubric.get("prompt") or "").strip()
    grading_style = str(rubric.get("grading_style") or rubric.get("style") or rubric.get("mode") or "partial").strip().lower()
    grading_style = {
        "feedback": "feedback-heavy",
        "feedback_heavy": "feedback-heavy",
    }.get(grading_style, grading_style)
    if grading_style not in {"exact", "partial", "feedback-heavy"}:
        grading_style = "partial"

    answer_type = str(
        rubric.get("answer_type")
        or rubric.get("submission_type")
        or rubric.get("type")
        or rubric.get("kind")
        or ""
    ).strip().lower()

    minimum_score = rubric.get("minimum_score") or rubric.get("pass_mark") or rubric.get("passing_score") or rubric.get("threshold") or 70
    try:
        minimum_score = float(minimum_score)
    except (TypeError, ValueError):
        minimum_score = 70.0

    criteria_raw = rubric.get("criteria") or rubric.get("items") or rubric.get("checks") or []
    criteria_source = list(criteria_raw) if isinstance(criteria_raw, (list, tuple, set)) else []
    if isinstance(criteria_raw, dict):
        criteria_source = [
            {"name": key, **(value if isinstance(value, dict) else {"description": value})}
            for key, value in criteria_raw.items()
        ]

    if not criteria_source:
        criteria_source = [{"name": line, "required_terms": _tokenize_words(line)} for line in _bullet_lines(description)]

    if not criteria_source:
        top_level_terms = rubric.get("required_terms") or rubric.get("keywords") or rubric.get("must_include") or rubric.get("must_mention")
        if top_level_terms:
            criteria_source = [
                {
                    "name": "Required elements",
                    "required_terms": top_level_terms,
                    "weight": 1,
                }
            ]

    normalized_criteria = []
    for index, item in enumerate(criteria_source):
        if isinstance(item, str):
            item = {"name": item}
        if not isinstance(item, dict):
            continue

        name = str(item.get("name") or item.get("title") or item.get("label") or f"Criterion {index + 1}").strip()
        weight = item.get("weight") or item.get("points") or item.get("max_score") or 1
        try:
            weight = float(weight)
        except (TypeError, ValueError):
            weight = 1.0
        weight = max(weight, 0.1)

        required_terms = (
            item.get("required_terms")
            or item.get("must_include")
            or item.get("keywords")
            or item.get("expected_terms")
            or item.get("must_mention")
            or item.get("required_keywords")
            or []
        )
        terms = [term.lower() for term in _split_terms(required_terms)]
        if not terms:
            terms = _tokenize_words(name + " " + str(item.get("description") or item.get("feedback") or ""))
        terms = list(dict.fromkeys(term for term in terms if term))

        normalized_criteria.append(
            {
                "name": name,
                "weight": weight,
                "required_terms": terms,
                "description": str(item.get("description") or item.get("feedback") or "").strip(),
            }
        )

    normalized = {
        "title": title,
        "description": description,
        "answer_type": answer_type,
        "grading_style": grading_style,
        "minimum_score": minimum_score,
        "criteria": normalized_criteria,
    }

    if rubric.get("notes"):
        normalized["notes"] = rubric.get("notes")

    return normalized if normalized_criteria else {}


def format_rubric_prompt(rubric) -> str:
    normalized = normalize_rubric(rubric)
    if not normalized:
        return ""
    return json.dumps(normalized, indent=2, ensure_ascii=False)


def score_rubric_submission(
    *,
    content: str,
    rubric,
    submission_type: str = "",
    academic_field: str = "",
    subfield: str = "",
) -> dict:
    normalized = normalize_rubric(rubric)
    if not normalized or not normalized.get("criteria"):
        return {}

    text = _normalize_text(content)
    criteria_results = []
    issues: list[str] = []
    suggestions: list[str] = []
    weighted_score = 0.0
    total_weight = 0.0

    for criterion in normalized["criteria"]:
        weight = float(criterion.get("weight") or 1.0)
        total_weight += weight
        required_terms = [term for term in criterion.get("required_terms", []) if term]
        matched_terms = [term for term in required_terms if _match_term(text, term)]
        missing_terms = [term for term in required_terms if term not in matched_terms]

        if required_terms:
            coverage = len(matched_terms) / len(required_terms)
            if normalized["grading_style"] == "exact":
                criterion_ratio = 1.0 if not missing_terms else 0.0
            else:
                criterion_ratio = coverage
        else:
            criterion_ratio = 0.5 if text else 0.0

        criterion_score = round(weight * criterion_ratio, 2)
        weighted_score += criterion_score

        if missing_terms:
            issues.append(f"{criterion['name']}: missing {', '.join(missing_terms[:3])}")
            suggestions.append(f"Add evidence for {criterion['name'].lower()}: {', '.join(missing_terms[:3])}.")
        elif required_terms:
            suggestions.append(f"Keep the {criterion['name'].lower()} section concise and explicit.")

        criteria_results.append(
            {
                "name": criterion["name"],
                "weight": weight,
                "score": round(criterion_ratio * 100, 2),
                "weighted_score": criterion_score,
                "matched_terms": matched_terms,
                "missing_terms": missing_terms,
                "feedback": (
                    f"Fully covered {criterion['name']}."
                    if not missing_terms and required_terms
                    else (
                        f"Partial coverage for {criterion['name']}; missing {', '.join(missing_terms[:3])}."
                        if missing_terms
                        else f"Reviewed {criterion['name']} against the rubric."
                    )
                ),
            }
        )

    if total_weight <= 0:
        return {}

    overall_score = round((weighted_score / total_weight) * 100, 2)
    threshold = normalized["minimum_score"]
    passed = overall_score >= threshold

    unique_issues = sorted(set(issues))
    unique_suggestions = sorted(set(suggestions))
    summary = f"Rubric-based verification completed with a score of {overall_score:.1f}/100."

    if normalized["title"]:
        summary = f"{normalized['title']}: {summary}"

    return {
        "source": "rubric",
        "academic_field": academic_field,
        "subfield": subfield,
        "submission_type": submission_type or normalized.get("answer_type") or "mixed",
        "rubric": normalized,
        "overall_score": overall_score,
        "passed": passed,
        "checks": [
            {
                "check_type": "rubric_alignment",
                "score": overall_score,
                "details": {
                    "criteria": criteria_results,
                    "grading_style": normalized["grading_style"],
                    "minimum_score": threshold,
                    "total_weight": round(total_weight, 2),
                    "weighted_score": round(weighted_score, 2),
                    "answer_type": normalized.get("answer_type") or submission_type or "mixed",
                },
                "issues": unique_issues,
                "suggestions": unique_suggestions,
            }
        ],
        "issues": unique_issues,
        "suggestions": unique_suggestions,
        "summary": summary,
        "grading_style": normalized["grading_style"],
        "minimum_score": threshold,
    }
