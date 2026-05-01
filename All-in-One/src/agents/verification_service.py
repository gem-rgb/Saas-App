"""Shared assignment verification helpers.

This wrapper uses the Gemini-powered agent when the package/API key are
available, and falls back to a local heuristic verifier otherwise.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Iterable

from django.apps import apps
from django.conf import settings

from analytics.plagiarism_cache import load_plagiarism_cache_context
from .plagiarism_engine import build_plagiarism_check
from .rubric_utils import normalize_rubric, score_rubric_submission

logger = logging.getLogger(__name__)


ACADEMIC_FIELD_KEYWORDS = {
    "engineering": {
        "subfields": ["civil", "mechanical", "electrical", "chemical", "software"],
        "keywords": {
            "engineering",
            "civil",
            "mechanical",
            "electrical",
            "chemical",
            "software",
            "structural",
            "design",
            "calculation",
            "diagram",
            "prototype",
        },
    },
    "medicine": {
        "subfields": ["anatomy", "physiology", "pharmacology", "surgery", "pathology"],
        "keywords": {
            "medicine",
            "medical",
            "clinical",
            "patient",
            "diagnosis",
            "pharmacology",
            "anatomy",
            "physiology",
            "surgery",
            "pathology",
            "treatment",
        },
    },
    "technology": {
        "subfields": ["algorithms", "database", "security", "networking", "ai/ml"],
        "keywords": {
            "technology",
            "software",
            "code",
            "algorithm",
            "database",
            "security",
            "network",
            "api",
            "ai",
            "machine learning",
            "cloud",
        },
    },
    "architecture": {
        "subfields": ["design", "urban planning", "structural", "sustainability"],
        "keywords": {
            "architecture",
            "architectural",
            "blueprint",
            "layout",
            "design",
            "structure",
            "floor plan",
            "elevation",
            "diagram",
            "model",
        },
    },
    "law": {
        "subfields": ["constitutional", "criminal", "civil", "corporate", "international"],
        "keywords": {
            "law",
            "legal",
            "statute",
            "case law",
            "citation",
            "contract",
            "argument",
            "brief",
            "precedent",
            "constitutional",
        },
    },
    "business": {
        "subfields": ["accounting", "finance", "management", "marketing", "economics"],
        "keywords": {
            "business",
            "finance",
            "accounting",
            "management",
            "marketing",
            "economics",
            "analysis",
            "budget",
            "revenue",
            "profit",
        },
    },
    "sciences": {
        "subfields": ["chemistry", "physics", "biology", "geology", "astronomy"],
        "keywords": {
            "science",
            "chemistry",
            "physics",
            "biology",
            "geology",
            "astronomy",
            "experiment",
            "equation",
            "formula",
            "calculation",
        },
    },
    "humanities": {
        "subfields": ["literature", "history", "philosophy", "languages", "art"],
        "keywords": {
            "humanities",
            "literature",
            "history",
            "philosophy",
            "language",
            "essay",
            "dissertation",
            "research",
            "analysis",
            "citation",
        },
    },
}


SUBMISSION_TYPE_HINTS = {
    "code": {"def ", "class ", "import ", "function", "algorithm", "#include", "console.log", "SELECT "},
    "calculations": {"=", "+", "-", "*", "/", "equation", "formula", "solve", "proof"},
    "diagram": {"diagram", "figure", "label", "legend", "flowchart", "chart", "graph", "blueprint"},
    "research": {"references", "citation", "methodology", "literature review", "survey", "sources"},
    "document": {"essay", "report", "dissertation", "analysis", "summary", "discussion"},
}


def _normalize(text: str | None) -> str:
    return (text or "").strip().lower()


def _tokenize(text: str | None) -> set[str]:
    normalized = _normalize(text)
    normalized = re.sub(r"[\n\r\t]+", " ", normalized)
    normalized = normalized.replace("/", " ").replace("-", " ")
    return {token for token in normalized.split(" ") if token}


def _count_hits(text: str, keywords: Iterable[str]) -> int:
    haystack = _normalize(text)
    return sum(1 for keyword in keywords if keyword in haystack)


def _dedupe_texts(texts: Iterable[str]) -> list[str]:
    seen = set()
    ordered_texts: list[str] = []
    for text in texts:
        normalized = _normalize(text)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered_texts.append(normalized)
    return ordered_texts


def _collect_submission_texts(model, *, filters: dict | None = None, exclude_pk: int | None = None, limit: int = 25) -> list[str]:
    try:
        qs = model.objects.all()
        if filters:
            qs = qs.filter(**filters)
        if exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
        qs = qs.exclude(submission_text__isnull=True).exclude(submission_text__exact="")
        return list(qs.order_by("-submitted_at").values_list("submission_text", flat=True)[:limit])
    except Exception as exc:  # pragma: no cover - defensive fallback for optional corpus data
        logger.debug("Unable to collect plagiarism corpus from %s: %s", getattr(model, "__name__", model), exc)
        return []


def _build_plagiarism_context(
    *,
    submission_source: str | None = None,
    source_object_id: int | None = None,
    author_id: int | None = None,
    submission_id: int | None = None,
    metadata: dict | None = None,
) -> dict:
    context = {
        "corpus_texts": [],
        "author_texts": [],
        "metadata": metadata if isinstance(metadata, dict) else {},
    }

    if submission_source not in {"marketplace", "assignments"}:
        return context

    try:
        if submission_source == "marketplace":
            model = apps.get_model("marketplace", "TaskSubmission")
            source_filter = {"task_id": source_object_id} if source_object_id is not None else None
            author_filter = {"tasker__user_id": author_id} if author_id is not None else None
        else:
            model = apps.get_model("assignments", "AssignmentSubmission")
            source_filter = {"assignment_id": source_object_id} if source_object_id is not None else None
            author_filter = {"tasker__user_id": author_id} if author_id is not None else None
    except LookupError:
        return context

    cache_context = load_plagiarism_cache_context(
        source_kind=submission_source,
        source_object_id=source_object_id,
        author_id=author_id,
    )
    if isinstance(cache_context, dict):
        context["cache_hits"] = list(cache_context.get("cache_hits") or [])
        context["cache_mode"] = "snapshot" if context["cache_hits"] else "live"
        context["corpus_texts"] = _dedupe_texts(cache_context.get("corpus_texts") or [])
        context["author_texts"] = _dedupe_texts(cache_context.get("author_texts") or [])
        context["corpus_profile"] = cache_context.get("corpus_profile")
        context["author_profile"] = cache_context.get("author_profile")
        context["reference_surprisal"] = cache_context.get("reference_surprisal")

    cache_hits = set(context.get("cache_hits") or [])
    if "corpus" not in cache_hits:
        source_texts = _collect_submission_texts(model, filters=source_filter, exclude_pk=submission_id, limit=25)
        recent_texts = _collect_submission_texts(model, exclude_pk=submission_id, limit=25)
        context["corpus_texts"] = _dedupe_texts(source_texts + recent_texts)
    if author_filter and "author" not in cache_hits:
        author_texts = _collect_submission_texts(model, filters=author_filter, exclude_pk=submission_id, limit=15)
        context["author_texts"] = _dedupe_texts(author_texts)

    if not context.get("cache_hits"):
        context["cache_mode"] = "live"
    return context


def _attach_plagiarism_analysis(
    result: dict,
    *,
    text: str,
    plagiarism_context: dict | None = None,
    submission_source: str | None = None,
    source_object_id: int | None = None,
    author_id: int | None = None,
    submission_id: int | None = None,
    metadata: dict | None = None,
) -> dict:
    if not isinstance(result, dict):
        result = {}

    result.setdefault("issues", [])
    result.setdefault("suggestions", [])
    result.setdefault("checks", [])

    context = plagiarism_context
    if context is None:
        context = _build_plagiarism_context(
            submission_source=submission_source,
            source_object_id=source_object_id,
            author_id=author_id,
            submission_id=submission_id,
            metadata=metadata,
        )

    if not isinstance(context, dict):
        context = {}

    merged_metadata: dict = {}
    if isinstance(metadata, dict):
        merged_metadata.update(metadata)
    context_metadata = context.get("metadata")
    if isinstance(context_metadata, dict):
        merged_metadata.update(context_metadata)

    plagiarism_check = build_plagiarism_check(
        text,
        corpus_texts=context.get("corpus_texts") or [],
        author_texts=context.get("author_texts") or [],
        metadata=merged_metadata,
        corpus_profile=context.get("corpus_profile"),
        author_profile=context.get("author_profile"),
        reference_surprisal=context.get("reference_surprisal"),
    )
    analysis = plagiarism_check.get("details", {}) if isinstance(plagiarism_check, dict) else {}
    if not isinstance(analysis, dict):
        analysis = {}

    result["plagiarism_analysis"] = analysis
    result["plagiarism_risk_score"] = analysis.get("risk_score", 0.0)
    result["plagiarism_decision"] = analysis.get("decision", "")
    result["plagiarism_model"] = analysis.get("model", "")
    result["ai_risk_score"] = analysis.get("ai_score", 0.0)
    result["plagiarism_cache_mode"] = context.get("cache_mode", "live")
    result["plagiarism_cache_hits"] = context.get("cache_hits", [])

    if not any(isinstance(check, dict) and check.get("check_type") == "plagiarism_detection" for check in result["checks"]):
        result["checks"].append(plagiarism_check)

    result["issues"] = sorted(set(result["issues"]) | set(plagiarism_check.get("issues", [])))
    result["suggestions"] = sorted(set(result["suggestions"]) | set(plagiarism_check.get("suggestions", [])))

    if float(analysis.get("risk_score", 0.0)) >= 70.0:
        result["passed"] = False
        result["issues"] = sorted(set(result["issues"]) | {"plagiarism_risk"})
        warning = f"Plagiarism risk detected: {analysis.get('decision', 'review required')}."
        summary = result.get("summary") or ""
        result["summary"] = f"{summary} {warning}".strip()

    return result


def infer_academic_field(
    *,
    title: str = "",
    description: str = "",
    required_skills: str = "",
    instructions: str = "",
    content: str = "",
) -> tuple[str, str]:
    combined = " ".join([title, description, required_skills, instructions, content]).lower()
    best_field = "humanities"
    best_score = -1
    best_subfield = ""

    for field, payload in ACADEMIC_FIELD_KEYWORDS.items():
        score = _count_hits(combined, payload["keywords"])
        if score > best_score:
            best_score = score
            best_field = field
            for subfield in payload["subfields"]:
                if subfield in combined:
                    best_subfield = subfield
                    break

    return best_field, best_subfield


def infer_submission_type(
    *,
    title: str = "",
    description: str = "",
    required_skills: str = "",
    instructions: str = "",
    content: str = "",
    filename: str = "",
) -> str:
    combined = " ".join([title, description, required_skills, instructions, content, filename]).lower()
    scores = Counter()

    for submission_type, hints in SUBMISSION_TYPE_HINTS.items():
        scores[submission_type] = _count_hits(combined, hints)

    if "```" in content or "def " in combined or "class " in combined or "import " in combined:
        scores["code"] += 3
    if any(symbol in combined for symbol in ["=", "+", "-", "*", "/"]) and any(
        term in combined for term in ["calculate", "calculation", "equation", "formula", "solve"]
    ):
        scores["calculations"] += 2
    if any(term in combined for term in ["dissertation", "essay", "report", "paper"]):
        scores["document"] += 2

    if not scores:
        return "document"

    top_type, top_score = scores.most_common(1)[0]
    if top_score <= 0:
        return "mixed"
    return top_type


def _build_check(check_type, score, issues=None, suggestions=None, details=None):
    return {
        "check_type": check_type,
        "score": round(float(score), 2),
        "issues": issues or [],
        "suggestions": suggestions or [],
        "details": details or {},
    }


def _score_writing(content: str) -> dict:
    text = content or ""
    words = _tokenize(text)
    paragraphs = [chunk for chunk in re.split(r"\n\s*\n", text) if chunk.strip()]
    score = 60.0
    issues = []
    suggestions = []

    if len(words) < 120:
        score -= 20
        issues.append("submission_is_too_short")
        suggestions.append("Expand the discussion with more detail and examples.")
    if len(paragraphs) >= 3:
        score += 10
    else:
        issues.append("weak_paragraph_structure")
        suggestions.append("Break the work into clearer sections and paragraphs.")
    if any(marker in text.lower() for marker in ["references", "bibliography", "(1)", "[1]", "doi"]):
        score += 10
    else:
        suggestions.append("Add citations or references where academic sources are used.")
    if len(re.findall(r"[.!?]", text)) >= 8:
        score += 10
    if any(term in text.lower() for term in ["dissertation", "analysis", "conclusion", "methodology"]):
        score += 10

    return _build_check(
        "writing_quality",
        max(0.0, min(100.0, score)),
        issues=issues,
        suggestions=suggestions,
        details={"paragraphs": len(paragraphs), "word_count": len(words)},
    )


def _score_code(content: str) -> dict:
    text = content or ""
    score = 55.0
    issues = []
    suggestions = []

    if "```" in text:
        score += 15
    if any(token in text for token in ["def ", "class ", "function ", "import ", "return "]):
        score += 15
    if any(token in text for token in ["try:", "except", "catch", "raise", "if __name__"]):
        score += 10
    if len(text) < 80:
        score -= 15
        issues.append("submission_is_too_short")
    if "TODO" in text or "fixme" in text.lower():
        score -= 10
        suggestions.append("Remove placeholders and finish the implementation.")
    if len(re.findall(r"\n", text)) >= 5:
        score += 5

    return _build_check(
        "code_quality",
        max(0.0, min(100.0, score)),
        issues=issues,
        suggestions=suggestions,
        details={"line_count": text.count("\n") + 1},
    )


def _score_calculations(content: str) -> dict:
    text = content or ""
    score = 58.0
    issues = []
    suggestions = []

    if any(symbol in text for symbol in ["=", "+", "-", "*", "/", "^"]):
        score += 20
    if any(term in text.lower() for term in ["equation", "formula", "solve", "result", "answer"]):
        score += 12
    if any(term in text.lower() for term in ["unit", "mm", "cm", "m", "kg", "n", "pa"]):
        score += 5
    if len(text) < 60:
        score -= 20
        issues.append("insufficient_working_shown")
        suggestions.append("Show the full working steps and final answer.")

    return _build_check(
        "calculations",
        max(0.0, min(100.0, score)),
        issues=issues,
        suggestions=suggestions,
        details={"symbol_hits": sum(1 for symbol in ["=", "+", "-", "*", "/", "^"] if symbol in text)},
    )


def _score_diagram(content: str) -> dict:
    text = content or ""
    score = 62.0
    issues = []
    suggestions = []

    if any(term in text.lower() for term in ["diagram", "figure", "label", "legend", "flowchart", "graph"]):
        score += 20
    if any(term in text.lower() for term in ["axis", "component", "arrow", "section", "view"]):
        score += 10
    if len(text) < 40:
        score -= 20
        issues.append("diagram_description_is_sparse")
        suggestions.append("Describe the diagram more clearly and label the key parts.")

    return _build_check(
        "diagram_quality",
        max(0.0, min(100.0, score)),
        issues=issues,
        suggestions=suggestions,
        details={"description_length": len(text)},
    )


def _score_research(content: str) -> dict:
    text = content or ""
    score = 60.0
    issues = []
    suggestions = []

    if any(marker in text.lower() for marker in ["references", "bibliography", "methodology", "literature review"]):
        score += 15
    if any(marker in text.lower() for marker in ["doi", "https://", "http://", "[1]", "(1)"]):
        score += 10
    if len(text) < 120:
        score -= 20
        issues.append("research_is_too_short")
        suggestions.append("Add more sources, analysis, and supporting evidence.")

    return _build_check(
        "research_quality",
        max(0.0, min(100.0, score)),
        issues=issues,
        suggestions=suggestions,
        details={"word_count": len(_tokenize(text))},
    )


def _score_technical(content: str) -> dict:
    text = content or ""
    score = 65.0
    issues = []
    suggestions = []

    if any(term in text.lower() for term in ["analysis", "method", "implementation", "design", "result"]):
        score += 10
    if len(text) < 80:
        score -= 15
        issues.append("submission_is_too_short")
    if any(term in text.lower() for term in ["error", "bug", "limitation", "challenge"]):
        score += 5

    return _build_check(
        "technical_accuracy",
        max(0.0, min(100.0, score)),
        issues=issues,
        suggestions=suggestions,
        details={"length": len(text)},
    )


def _heuristic_verify(content: str, submission_type: str, academic_field: str, subfield: str) -> dict:
    checks = []
    if submission_type == "code":
        checks.append(_score_code(content))
    elif submission_type == "document":
        checks.append(_score_writing(content))
    elif submission_type == "calculations":
        checks.append(_score_calculations(content))
    elif submission_type == "diagram":
        checks.append(_score_diagram(content))
    elif submission_type == "research":
        checks.append(_score_research(content))
    else:
        checks.extend([_score_writing(content), _score_technical(content)])

    overall_score = round(sum(check["score"] for check in checks) / max(len(checks), 1), 2)
    issues = []
    suggestions = []
    for check in checks:
        issues.extend(check.get("issues", []))
        suggestions.extend(check.get("suggestions", []))

    return {
        "source": "heuristic",
        "academic_field": academic_field,
        "subfield": subfield,
        "submission_type": submission_type,
        "overall_score": overall_score,
        "passed": overall_score >= 70,
        "checks": checks,
        "issues": sorted(set(issues)),
        "suggestions": sorted(set(suggestions)),
        "summary": f"Heuristic verification completed with a score of {overall_score:.1f}/100.",
    }


def run_assignment_verification(
    *,
    content: str,
    title: str = "",
    description: str = "",
    required_skills: str = "",
    instructions: str = "",
    academic_field: str | None = None,
    subfield: str = "",
    submission_type: str | None = None,
    rubric=None,
    author_id: int | None = None,
    submission_source: str | None = None,
    source_object_id: int | None = None,
    submission_id: int | None = None,
    plagiarism_context: dict | None = None,
    metadata: dict | None = None,
) -> dict:
    """Verify a submission using Gemini when possible, otherwise heuristics."""

    text = content or description or instructions or title or ""
    normalized_rubric = normalize_rubric(rubric)
    if not academic_field:
        academic_field, inferred_subfield = infer_academic_field(
            title=title,
            description=description,
            required_skills=required_skills,
            instructions=instructions,
            content=text,
        )
        if not subfield:
            subfield = inferred_subfield

    if normalized_rubric and not submission_type and normalized_rubric.get("answer_type"):
        submission_type = normalized_rubric["answer_type"]

    if not submission_type:
        submission_type = infer_submission_type(
            title=title,
            description=description,
            required_skills=required_skills,
            instructions=instructions,
            content=text,
        )

    if normalized_rubric and getattr(settings, "GOOGLE_GEMINI_API_KEY", None):
        try:
            from agents.assignment_verification import AssignmentVerificationAgent

            agent = AssignmentVerificationAgent(
                field=academic_field,
                subfield=subfield or academic_field,
                assignment_type=title or required_skills or academic_field,
                rubric=normalized_rubric,
            )
            result = agent.verify_assignment(text, submission_type=submission_type)
            result.setdefault("issues", [])
            result.setdefault("suggestions", [])
            result.setdefault("checks", [])
            result.setdefault("source", "gemini")
            result.setdefault("academic_field", academic_field)
            result.setdefault("subfield", subfield)
            result.setdefault("submission_type", submission_type)
            result.setdefault("rubric", normalized_rubric)
            result.setdefault(
                "summary",
                f"Gemini rubric verification completed with a score of {result.get('overall_score', 0.0):.1f}/100.",
            )
            return _attach_plagiarism_analysis(
                result,
                text=text,
                plagiarism_context=plagiarism_context,
                submission_source=submission_source,
                source_object_id=source_object_id,
                author_id=author_id,
                submission_id=submission_id,
                metadata=metadata,
            )
        except Exception as exc:  # pragma: no cover - Gemini is optional in this environment
            logger.warning("Gemini rubric verification unavailable, falling back to heuristics: %s", exc)

    if normalized_rubric:
        rubric_result = score_rubric_submission(
            content=text,
            rubric=normalized_rubric,
            submission_type=submission_type,
            academic_field=academic_field,
            subfield=subfield,
        )
        if rubric_result:
            rubric_result.setdefault("source", "rubric")
            return _attach_plagiarism_analysis(
                rubric_result,
                text=text,
                plagiarism_context=plagiarism_context,
                submission_source=submission_source,
                source_object_id=source_object_id,
                author_id=author_id,
                submission_id=submission_id,
                metadata=metadata,
            )

    if getattr(settings, "GOOGLE_GEMINI_API_KEY", None):
        try:
            from agents.assignment_verification import AssignmentVerificationAgent

            agent = AssignmentVerificationAgent(
                field=academic_field,
                subfield=subfield or academic_field,
                assignment_type=title or required_skills or academic_field,
            )
            result = agent.verify_assignment(text, submission_type=submission_type)
            result.setdefault("issues", [])
            result.setdefault("suggestions", [])
            result.setdefault("checks", [])
            result.update(
                {
                    "source": "gemini",
                    "academic_field": academic_field,
                    "subfield": subfield,
                    "submission_type": submission_type,
                }
            )
            result.setdefault(
                "summary",
                f"Gemini verification completed with a score of {result.get('overall_score', 0.0):.1f}/100.",
            )
            return _attach_plagiarism_analysis(
                result,
                text=text,
                plagiarism_context=plagiarism_context,
                submission_source=submission_source,
                source_object_id=source_object_id,
                author_id=author_id,
                submission_id=submission_id,
                metadata=metadata,
            )
        except Exception as exc:  # pragma: no cover - Gemini is optional in this environment
            logger.warning("Gemini verification unavailable, falling back to heuristics: %s", exc)

    return _attach_plagiarism_analysis(
        _heuristic_verify(text, submission_type, academic_field, subfield),
        text=text,
        plagiarism_context=plagiarism_context,
        submission_source=submission_source,
        source_object_id=source_object_id,
        author_id=author_id,
        submission_id=submission_id,
        metadata=metadata,
    )
