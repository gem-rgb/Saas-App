from __future__ import annotations

import hashlib
from typing import Iterable

from analytics.models import PlagiarismSnapshot
from agents.plagiarism_engine import build_plagiarism_training_payload


def _normalize_texts(texts: Iterable[str] | None) -> list[str]:
    normalized: list[str] = []
    for text in texts or []:
        cleaned = (text or "").strip()
        if cleaned:
            normalized.append(cleaned)
    return normalized


def make_cache_key(
    *,
    cache_type: str,
    source_kind: str,
    source_object_id: int | None = None,
    author_id: int | None = None,
) -> str:
    cache_type = (cache_type or "").strip().lower()
    source_kind = (source_kind or "").strip().lower()
    if cache_type == PlagiarismSnapshot.CacheType.CORPUS:
        return f"plagiarism:corpus:{source_kind}:{source_object_id or 0}"
    if cache_type == PlagiarismSnapshot.CacheType.AUTHOR:
        return f"plagiarism:author:{source_kind}:user:{author_id or 0}"
    return f"plagiarism:{cache_type}:{source_kind}:{source_object_id or author_id or 0}"


def fingerprint_texts(texts: Iterable[str] | None) -> str:
    digest = hashlib.sha256()
    for text in _normalize_texts(texts):
        digest.update(text.encode("utf-8"))
        digest.update(b"\x1e")
    return digest.hexdigest()


def build_snapshot_payload(texts: Iterable[str] | None, *, sample_limit: int = 25) -> dict:
    normalized = _normalize_texts(texts)
    payload = build_plagiarism_training_payload(normalized, sample_limit=sample_limit)
    payload["text_count"] = len(normalized)
    payload["sample_limit"] = sample_limit
    return payload


def load_plagiarism_cache_context(
    *,
    source_kind: str,
    source_object_id: int | None = None,
    author_id: int | None = None,
) -> dict:
    context = {
        "cache_hits": [],
        "corpus_texts": [],
        "corpus_profile": None,
        "author_texts": [],
        "author_profile": None,
        "reference_surprisal": None,
    }

    if source_object_id is not None:
        corpus_key = make_cache_key(
            cache_type=PlagiarismSnapshot.CacheType.CORPUS,
            source_kind=source_kind,
            source_object_id=source_object_id,
        )
        corpus_snapshot = PlagiarismSnapshot.objects.filter(cache_key=corpus_key).first()
        if corpus_snapshot is not None:
            context["cache_hits"].append("corpus")
            context["corpus_texts"] = corpus_snapshot.sample_texts
            context["corpus_profile"] = corpus_snapshot.profile
            context["reference_surprisal"] = corpus_snapshot.reference_surprisal

    if author_id is not None:
        author_key = make_cache_key(
            cache_type=PlagiarismSnapshot.CacheType.AUTHOR,
            source_kind=source_kind,
            author_id=author_id,
        )
        author_snapshot = PlagiarismSnapshot.objects.filter(cache_key=author_key).first()
        if author_snapshot is not None:
            context["cache_hits"].append("author")
            context["author_texts"] = author_snapshot.sample_texts
            context["author_profile"] = author_snapshot.profile
            if context["reference_surprisal"] is None:
                context["reference_surprisal"] = author_snapshot.reference_surprisal

    return context


def upsert_plagiarism_snapshot(
    *,
    cache_type: str,
    source_kind: str,
    texts: Iterable[str] | None,
    source_object_id: int | None = None,
    author=None,
    author_id: int | None = None,
    sample_limit: int = 25,
    window_days: int = 30,
    force: bool = False,
) -> tuple[PlagiarismSnapshot, bool]:
    normalized_texts = _normalize_texts(texts)
    resolved_author_id = author_id if author_id is not None else getattr(author, "id", None)
    cache_key = make_cache_key(
        cache_type=cache_type,
        source_kind=source_kind,
        source_object_id=source_object_id,
        author_id=resolved_author_id,
    )
    source_hash = fingerprint_texts(normalized_texts)
    payload = build_snapshot_payload(normalized_texts, sample_limit=sample_limit)

    existing = PlagiarismSnapshot.objects.filter(cache_key=cache_key).first()
    if (
        existing
        and not force
        and existing.source_hash == source_hash
        and existing.source_window_days == window_days
        and (existing.payload or {}).get("sample_limit") == sample_limit
    ):
        return existing, False

    snapshot, _ = PlagiarismSnapshot.objects.update_or_create(
        cache_key=cache_key,
        defaults={
            "cache_type": cache_type,
            "source_kind": source_kind,
            "source_object_id": source_object_id,
            "author_id": resolved_author_id,
            "payload": payload,
            "source_hash": source_hash,
            "sample_text_count": len(normalized_texts),
            "source_window_days": window_days,
        },
    )
    return snapshot, True
