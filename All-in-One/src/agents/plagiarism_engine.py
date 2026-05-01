from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from statistics import mean
from typing import Iterable

import numpy as np

try:
    from sklearn.ensemble import IsolationForest
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    from sklearn.preprocessing import StandardScaler
except Exception:  # pragma: no cover - graceful fallback if sklearn is unavailable
    IsolationForest = None
    TfidfVectorizer = None
    cosine_similarity = None
    StandardScaler = None


FUNCTION_WORDS = {
    "a",
    "about",
    "after",
    "all",
    "also",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "because",
    "been",
    "but",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "he",
    "her",
    "his",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "may",
    "might",
    "more",
    "most",
    "no",
    "not",
    "of",
    "on",
    "or",
    "our",
    "should",
    "so",
    "such",
    "than",
    "that",
    "the",
    "their",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "to",
    "under",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "will",
    "with",
    "would",
    "you",
}

ACADEMIC_PHRASES = {
    "according to research",
    "many studies show",
    "research suggests",
    "it is widely known",
    "the literature shows",
    "some scholars argue",
    "in conclusion",
    "to summarize",
}

REFERENCE_PATTERNS = (
    re.compile(r"\([A-Z][A-Za-z\-]+(?:\s+et\s+al\.)?,?\s*\d{4}\)"),
    re.compile(r"\[[0-9]{1,3}\]"),
    re.compile(r"doi:\s*\S+", re.IGNORECASE),
    re.compile(r"https?://\S+", re.IGNORECASE),
)

SUSPICIOUS_REFERENCE_PATTERNS = (
    "fake reference",
    "placeholder citation",
    "lorem ipsum",
    "sample reference",
    "works cited",
    "bibliography",
)

DEFAULT_PROFILE = {
    "sentence_length_mean": 18.0,
    "sentence_length_std": 6.0,
    "ttr": 0.58,
    "function_word_ratio": 0.38,
    "punctuation_density": 0.05,
    "burstiness": 0.55,
    "lexical_entropy": 0.72,
    "repetition_ratio": 0.15,
}


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def _normalize_text(text: str | None) -> str:
    return (text or "").strip()


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [part.strip() for part in parts if part and part.strip()]


def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9']+", text.lower())


def _safe_mean(values: Iterable[float], default: float = 0.0) -> float:
    values = list(values)
    return float(mean(values)) if values else default


def _safe_std(values: Iterable[float]) -> float:
    values = list(values)
    if len(values) < 2:
        return 0.0
    return float(np.std(values, ddof=0))


def _range_distance(value: float, lower: float, upper: float) -> float:
    if value < lower:
        return (lower - value) / max(lower, 1e-6)
    if value > upper:
        return (value - upper) / max(upper, 1e-6)
    return 0.0


def _feature_vector(text: str) -> dict[str, float]:
    normalized = _normalize_text(text)
    words = _tokens(normalized)
    sentences = _sentences(normalized)
    word_count = len(words)
    sentence_lengths = [len(_tokens(sentence)) for sentence in sentences] or [0]
    punctuation_count = len(re.findall(r"[,:;()\[\]{}\-]", normalized))
    digit_count = len(re.findall(r"\d", normalized))
    reference_hits = sum(1 for pattern in REFERENCE_PATTERNS if pattern.search(normalized))
    suspicious_reference_hits = sum(1 for phrase in SUSPICIOUS_REFERENCE_PATTERNS if phrase in normalized.lower())

    token_counts = Counter(words)
    unique_words = len(token_counts)
    repeated_tokens = sum(count - 1 for count in token_counts.values() if count > 1)
    repeated_token_ratio = repeated_tokens / max(word_count, 1)
    function_word_hits = sum(1 for token in words if token in FUNCTION_WORDS)
    function_word_ratio = function_word_hits / max(word_count, 1)
    type_token_ratio = unique_words / max(word_count, 1)
    punctuation_density = punctuation_count / max(len(normalized), 1)
    digit_density = digit_count / max(len(normalized), 1)
    sentence_length_mean = _safe_mean(sentence_lengths, default=float(word_count))
    sentence_length_std = _safe_std(sentence_lengths)
    burstiness = sentence_length_std / max(sentence_length_mean, 1e-6)
    paragraph_count = len([block for block in re.split(r"\n\s*\n", normalized) if block.strip()])
    lexical_entropy = 0.0
    if token_counts:
        total = float(sum(token_counts.values()))
        lexical_entropy = -sum((count / total) * math.log2(count / total) for count in token_counts.values())
        lexical_entropy = lexical_entropy / max(math.log2(len(token_counts) + 1), 1.0)

    unique_sentence_ratio = len(set(sentence for sentence in sentences if sentence)) / max(len(sentences), 1)
    repetition_ratio = 1.0 - unique_sentence_ratio

    return {
        "word_count": float(word_count),
        "sentence_count": float(len(sentences)),
        "sentence_length_mean": float(sentence_length_mean),
        "sentence_length_std": float(sentence_length_std),
        "burstiness": float(burstiness),
        "ttr": float(type_token_ratio),
        "function_word_ratio": float(function_word_ratio),
        "punctuation_density": float(punctuation_density),
        "digit_density": float(digit_density),
        "reference_hits": float(reference_hits),
        "suspicious_reference_hits": float(suspicious_reference_hits),
        "repetition_ratio": float(repetition_ratio),
        "lexical_entropy": float(lexical_entropy),
        "paragraph_count": float(paragraph_count),
    }


def _profile_from_texts(texts: list[str]) -> dict[str, float]:
    vectors = [_feature_vector(text) for text in texts if _normalize_text(text)]
    if not vectors:
        return dict(DEFAULT_PROFILE)

    profile = {}
    for key in DEFAULT_PROFILE:
        profile[key] = _safe_mean((vector[key] for vector in vectors), default=DEFAULT_PROFILE[key])
    return profile


def build_plagiarism_training_payload(texts: list[str], *, sample_limit: int = 25) -> dict:
    normalized_texts = [_normalize_text(text) for text in texts if _normalize_text(text)]
    sample_texts = normalized_texts[: max(sample_limit, 1)]
    profile = _profile_from_texts(normalized_texts)
    _, _, reference_surprisal = _unigram_model(normalized_texts)
    return {
        "text_count": len(normalized_texts),
        "sample_texts": sample_texts,
        "profile": profile,
        "reference_surprisal": round(reference_surprisal, 4),
    }


def _unigram_model(texts: list[str]) -> tuple[Counter[str], int, float]:
    counts: Counter[str] = Counter()
    for text in texts:
        counts.update(_tokens(text))
    total = sum(counts.values())
    if total <= 0:
        return Counter(), 0, 7.5

    sample_surprisals = []
    vocabulary = len(counts)
    smoothing = vocabulary + total
    for text in texts:
        tokens = _tokens(text)
        if not tokens:
            continue
        surprisal = 0.0
        for token in tokens:
            probability = (counts.get(token, 0) + 1.0) / (smoothing + 1.0)
            surprisal += -math.log2(probability)
        sample_surprisals.append(surprisal / max(len(tokens), 1))

    reference_surprisal = _safe_mean(sample_surprisals, default=7.5)
    return counts, total, reference_surprisal


def _sentence_redundancy_score(text: str) -> float:
    if TfidfVectorizer is None or cosine_similarity is None:
        sentences = _sentences(text)
        if len(sentences) < 2:
            return 0.0
        token_sets = [set(_tokens(sentence)) for sentence in sentences if sentence.strip()]
        if len(token_sets) < 2:
            return 0.0
        overlaps = []
        for idx, left in enumerate(token_sets):
            for right in token_sets[idx + 1 :]:
                union = left | right
                if not union:
                    continue
                overlaps.append(len(left & right) / len(union))
        return _clamp(_safe_mean(overlaps, default=0.0) * 100.0)

    sentences = [sentence for sentence in _sentences(text) if sentence]
    if len(sentences) < 2:
        return 0.0

    sentence_matrix = TfidfVectorizer(stop_words="english", ngram_range=(1, 2)).fit_transform(sentences)
    similarity_matrix = cosine_similarity(sentence_matrix)
    scores = []
    for row in range(similarity_matrix.shape[0]):
        for col in range(row + 1, similarity_matrix.shape[1]):
            scores.append(float(similarity_matrix[row, col]))
    return _clamp(_safe_mean(scores, default=0.0) * 100.0)


def _citation_risk(text: str, features: dict[str, float]) -> tuple[float, list[str]]:
    normalized = text.lower()
    citations = sum(len(pattern.findall(text)) for pattern in REFERENCE_PATTERNS)
    reference_section = any(marker in normalized for marker in ["references", "bibliography", "works cited"])
    signals: list[str] = []
    risk = 0.0

    if features["word_count"] >= 140 and citations == 0:
        risk += 35.0
        signals.append("missing_citations")
    if reference_section and citations == 0:
        risk += 18.0
        signals.append("reference_section_without_citations")
    if features["suspicious_reference_hits"] > 0:
        risk += 22.0
        signals.append("placeholder_references")
    if any(phrase in normalized for phrase in ACADEMIC_PHRASES) and citations == 0:
        risk += 10.0
        signals.append("generic_academic_language")
    if re.search(r"\bet al\.\b", normalized) and citations == 0:
        risk += 12.0
        signals.append("unsupported_et_al_reference")
    if citations > 0 and features["word_count"] >= 200:
        risk -= 8.0

    return _clamp(risk), signals


def _behavioral_risk(metadata: dict | None, text: str) -> tuple[float, list[str]]:
    metadata = metadata if isinstance(metadata, dict) else {}
    signals: list[str] = []
    risk = 0.0

    copy_paste_ratio = float(metadata.get("copy_paste_ratio") or 0.0)
    paste_events = float(metadata.get("paste_events") or 0.0)
    edit_count = float(metadata.get("edit_count") or 0.0)
    typing_speed_wpm = float(metadata.get("typing_speed_wpm") or 0.0)
    revision_count = float(metadata.get("revision_count") or 0.0)

    if copy_paste_ratio >= 0.6:
        risk += 30.0
        signals.append("heavy_copy_paste")
    elif copy_paste_ratio >= 0.3:
        risk += 16.0
        signals.append("copy_paste_spike")

    if paste_events >= 3:
        risk += 16.0
        signals.append("frequent_paste_events")
    elif paste_events >= 1:
        risk += 8.0
        signals.append("paste_event_present")

    if typing_speed_wpm >= 140 and len(_tokens(text)) >= 180:
        risk += 10.0
        signals.append("unusually_fast_typing")

    if edit_count <= 1 and len(_tokens(text)) >= 200:
        risk += 10.0
        signals.append("low_edit_activity")

    if revision_count >= 6:
        risk += 8.0
        signals.append("many_revision_rounds")

    return _clamp(risk), signals


def _top_matches(text: str, corpus_texts: list[str], top_n: int = 3) -> list[dict]:
    if not corpus_texts or TfidfVectorizer is None or cosine_similarity is None:
        return []

    texts = [candidate for candidate in corpus_texts if _normalize_text(candidate)]
    if not texts:
        return []

    word_vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
    char_vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1)
    word_matrix = word_vectorizer.fit_transform(texts + [text])
    char_matrix = char_vectorizer.fit_transform(texts + [text])

    target_word = word_matrix[-1]
    target_char = char_matrix[-1]
    word_similarities = cosine_similarity(target_word, word_matrix[:-1]).flatten()
    char_similarities = cosine_similarity(target_char, char_matrix[:-1]).flatten()

    combined = []
    for index, candidate in enumerate(texts):
        score = float((word_similarities[index] * 0.65) + (char_similarities[index] * 0.35))
        combined.append((score, candidate))

    combined.sort(key=lambda item: item[0], reverse=True)
    matches = []
    for rank, (score, candidate) in enumerate(combined[:top_n], start=1):
        matches.append(
            {
                "rank": rank,
                "score": round(score * 100.0, 2),
                "excerpt": candidate[:220],
            }
        )
    return matches


@dataclass
class PlagiarismAnalyzer:
    corpus_texts: list[str]
    author_texts: list[str]
    metadata: dict | None = None
    corpus_profile_override: dict | None = None
    author_profile_override: dict | None = None
    reference_surprisal_override: float | None = None

    def __post_init__(self):
        self.corpus_texts = [_normalize_text(text) for text in self.corpus_texts if _normalize_text(text)]
        self.author_texts = [_normalize_text(text) for text in self.author_texts if _normalize_text(text)]
        self.metadata = self.metadata if isinstance(self.metadata, dict) else {}

        self.corpus_profile = self.corpus_profile_override or _profile_from_texts(self.corpus_texts)
        self.author_profile = self.author_profile_override or (_profile_from_texts(self.author_texts) if self.author_texts else None)
        if self.reference_surprisal_override is not None:
            self.language_counts, self.language_total, self.reference_surprisal = _unigram_model(self.corpus_texts or self.author_texts)
            self.reference_surprisal = float(self.reference_surprisal_override)
        else:
            self.language_counts, self.language_total, self.reference_surprisal = _unigram_model(self.corpus_texts or self.author_texts)
        self.word_vectorizer = None
        self.char_vectorizer = None
        self.word_matrix = None
        self.char_matrix = None
        self.scaler = None
        self.anomaly_model = None
        self.corpus_feature_matrix = None

        if TfidfVectorizer is not None and self.corpus_texts:
            self.word_vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
            self.char_vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1)
            self.word_matrix = self.word_vectorizer.fit_transform(self.corpus_texts)
            self.char_matrix = self.char_vectorizer.fit_transform(self.corpus_texts)

        if StandardScaler is not None:
            self.corpus_feature_matrix = np.asarray([
                list(_feature_vector(text).values()) for text in self.corpus_texts
            ], dtype=float) if self.corpus_texts else None
            if self.corpus_feature_matrix is not None and self.corpus_feature_matrix.size:
                self.scaler = StandardScaler()
                scaled = self.scaler.fit_transform(self.corpus_feature_matrix)
                if IsolationForest is not None and len(self.corpus_texts) >= 8:
                    contamination = min(0.25, max(0.05, 5.0 / len(self.corpus_texts)))
                    self.anomaly_model = IsolationForest(
                        n_estimators=120,
                        contamination=contamination,
                        random_state=42,
                    )
                    self.anomaly_model.fit(scaled)

    def _style_risk(self, features: dict[str, float]) -> tuple[float, list[str]]:
        profile = self.corpus_profile or DEFAULT_PROFILE
        signals: list[str] = []
        deltas = []

        for key, lower, upper in [
            ("sentence_length_mean", 12.0, 24.0),
            ("sentence_length_std", 3.0, 12.0),
            ("ttr", 0.38, 0.78),
            ("function_word_ratio", 0.28, 0.55),
            ("punctuation_density", 0.01, 0.12),
            ("burstiness", 0.22, 1.20),
            ("lexical_entropy", 0.45, 0.92),
            ("repetition_ratio", 0.0, 0.35),
        ]:
            target = profile.get(key, DEFAULT_PROFILE[key])
            if key in {"sentence_length_mean", "sentence_length_std"}:
                distance = _range_distance(features[key], lower, upper)
            else:
                distance = _range_distance(features[key], lower, upper)
            if distance > 0.35:
                signals.append(f"{key}_deviation")
            deltas.append(distance)

        risk = _clamp(_safe_mean(deltas, default=0.0) * 100.0)
        if features["sentence_count"] <= 2 and features["word_count"] >= 180:
            risk += 10.0
            signals.append("too_few_sentences")
        if features["burstiness"] <= 0.25 and features["word_count"] >= 120:
            risk += 12.0
            signals.append("low_burstiness")
        if features["ttr"] <= 0.45 and features["word_count"] >= 150:
            risk += 12.0
            signals.append("low_vocabulary_richness")
        if features["repetition_ratio"] >= 0.35:
            risk += 15.0
            signals.append("repetitive_structure")

        return _clamp(risk), sorted(set(signals))

    def _consistency_risk(self, features: dict[str, float]) -> tuple[float, list[str]]:
        if not self.author_profile:
            return 0.0, []

        signals: list[str] = []
        comparisons = []
        for key in ["sentence_length_mean", "sentence_length_std", "ttr", "function_word_ratio", "punctuation_density", "burstiness", "lexical_entropy", "repetition_ratio"]:
            baseline = self.author_profile.get(key, DEFAULT_PROFILE[key])
            diff = abs(features[key] - baseline)
            comparisons.append(diff)
            if diff > 0.18 and key in {"ttr", "function_word_ratio", "burstiness", "repetition_ratio"}:
                signals.append(f"author_{key}_shift")

        risk = _clamp(_safe_mean(comparisons, default=0.0) * 130.0)
        if features["word_count"] >= 150 and risk <= 12.0:
            signals.append("stable_author_signature")
        return risk, sorted(set(signals))

    def _perplexity_risk(self, text: str) -> tuple[float, list[str]]:
        tokens = _tokens(text)
        if not tokens:
            return 0.0, []

        vocabulary = max(len(self.language_counts), 1)
        smoothing = self.language_total + vocabulary
        surprisal = 0.0
        for token in tokens:
            probability = (self.language_counts.get(token, 0) + 1.0) / (smoothing + 1.0)
            surprisal += -math.log2(probability)
        sample_surprisal = surprisal / max(len(tokens), 1)
        delta = self.reference_surprisal - sample_surprisal
        risk = _clamp(50.0 + (delta * 12.0))
        signals = []
        if risk >= 65.0:
            signals.append("predictable_language")
        elif risk <= 30.0:
            signals.append("higher_language_entropy")
        return risk, signals

    def _anomaly_risk(self, features: dict[str, float]) -> tuple[float, list[str]]:
        if self.anomaly_model is None or self.scaler is None or self.corpus_feature_matrix is None:
            return 0.0, []

        feature_vector = np.asarray([list(features.values())], dtype=float)
        scaled = self.scaler.transform(feature_vector)
        anomaly_score = float(-self.anomaly_model.decision_function(scaled)[0])
        risk = _clamp((anomaly_score + 0.25) * 80.0)
        signals = ["statistical_anomaly"] if risk >= 45.0 else []
        return risk, signals

    def analyze(self, text: str) -> dict:
        normalized = _normalize_text(text)
        features = _feature_vector(normalized)

        perplexity_risk, perplexity_signals = self._perplexity_risk(normalized)
        style_risk, style_signals = self._style_risk(features)
        consistency_risk, consistency_signals = self._consistency_risk(features)
        semantic_risk = _sentence_redundancy_score(normalized)
        semantic_signals = ["semantic_redundancy"] if semantic_risk >= 45.0 else []
        citation_risk, citation_signals = _citation_risk(normalized, features)
        behavior_risk, behavior_signals = _behavioral_risk(self.metadata, normalized)
        anomaly_risk, anomaly_signals = self._anomaly_risk(features)
        similarity_matches = _top_matches(normalized, self.corpus_texts)
        best_similarity = similarity_matches[0]["score"] if similarity_matches else 0.0
        similarity_risk = _clamp(best_similarity)
        if best_similarity >= 75.0:
            semantic_signals.append("near_duplicate_to_corpus")

        ai_score = _clamp(
            (
                perplexity_risk * 0.32
                + style_risk * 0.28
                + semantic_risk * 0.20
                + consistency_risk * 0.20
            )
        )
        plagiarism_score = _clamp(
            (
                similarity_risk * 0.52
                + citation_risk * 0.16
                + behavior_risk * 0.12
                + anomaly_risk * 0.10
                + semantic_risk * 0.10
            )
        )
        final_risk = _clamp((plagiarism_score * 0.55) + (ai_score * 0.45))

        decision = "Likely human-written"
        if plagiarism_score >= 80.0:
            decision = "High plagiarism risk"
        elif ai_score >= 70.0:
            decision = "Likely AI-generated"
        elif consistency_risk >= 60.0:
            decision = "Writing style inconsistency"

        risk_level = "low"
        if final_risk >= 80.0:
            risk_level = "high"
        elif final_risk >= 55.0:
            risk_level = "medium"

        signals = sorted(
            set(
                perplexity_signals
                + style_signals
                + consistency_signals
                + semantic_signals
                + citation_signals
                + behavior_signals
                + anomaly_signals
            )
        )

        recommendations = []
        if "missing_citations" in signals or "reference_section_without_citations" in signals:
            recommendations.append("Add concrete citations and a real reference list.")
        if "low_burstiness" in signals or "low_vocabulary_richness" in signals:
            recommendations.append("Vary sentence length and vocabulary to better match your normal style.")
        if "semantic_redundancy" in signals or "repetitive_structure" in signals:
            recommendations.append("Remove repeated ideas and tighten the argument structure.")
        if "heavy_copy_paste" in signals or "copy_paste_spike" in signals:
            recommendations.append("Write in smaller revisions instead of pasting large blocks at once.")
        if not recommendations:
            recommendations.append("Review the submission for originality and citation coverage.")

        return {
            "model": "hybrid-plagiarism-detector-v1",
            "risk_score": round(final_risk, 2),
            "risk_level": risk_level,
            "decision": decision,
            "ai_score": round(ai_score, 2),
            "plagiarism_score": round(plagiarism_score, 2),
            "stylometric_score": round(style_risk, 2),
            "semantic_score": round(semantic_risk, 2),
            "consistency_score": round(consistency_risk, 2),
            "perplexity_score": round(perplexity_risk, 2),
            "citation_score": round(citation_risk, 2),
            "behavior_score": round(behavior_risk, 2),
            "anomaly_score": round(anomaly_risk, 2),
            "similarity_score": round(similarity_risk, 2),
            "features": features,
            "top_matches": similarity_matches,
            "signals": signals,
            "recommendations": recommendations,
        }


def analyze_plagiarism(
    text: str,
    *,
    corpus_texts: list[str] | None = None,
    author_texts: list[str] | None = None,
    metadata: dict | None = None,
    corpus_profile: dict | None = None,
    author_profile: dict | None = None,
    reference_surprisal: float | None = None,
) -> dict:
    analyzer = PlagiarismAnalyzer(
        corpus_texts=corpus_texts or [],
        author_texts=author_texts or [],
        metadata=metadata or {},
        corpus_profile_override=corpus_profile,
        author_profile_override=author_profile,
        reference_surprisal_override=reference_surprisal,
    )
    return analyzer.analyze(text)


def build_plagiarism_check(
    text: str,
    *,
    corpus_texts: list[str] | None = None,
    author_texts: list[str] | None = None,
    metadata: dict | None = None,
    corpus_profile: dict | None = None,
    author_profile: dict | None = None,
    reference_surprisal: float | None = None,
) -> dict:
    analysis = analyze_plagiarism(
        text,
        corpus_texts=corpus_texts,
        author_texts=author_texts,
        metadata=metadata,
        corpus_profile=corpus_profile,
        author_profile=author_profile,
        reference_surprisal=reference_surprisal,
    )
    return {
        "check_type": "plagiarism_detection",
        "score": round(max(0.0, 100.0 - analysis["risk_score"]), 2),
        "passed": analysis["risk_score"] < 70.0,
        "issues": analysis["signals"],
        "suggestions": analysis["recommendations"],
        "details": analysis,
    }
