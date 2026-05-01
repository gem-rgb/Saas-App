from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from analytics.models import PlagiarismSnapshot
from analytics.plagiarism_cache import upsert_plagiarism_snapshot
from assignments.models import AssignmentSubmission
from marketplace.models import TaskSubmission


SOURCE_CONFIG = {
    PlagiarismSnapshot.SourceKind.MARKETPLACE: {
        "submission_model": TaskSubmission,
        "source_field": "task_id",
        "author_field": "tasker__user_id",
    },
    PlagiarismSnapshot.SourceKind.ASSIGNMENTS: {
        "submission_model": AssignmentSubmission,
        "source_field": "assignment_id",
        "author_field": "tasker__user_id",
    },
}


class Command(BaseCommand):
    help = "Refresh persisted plagiarism corpus and author snapshots."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            choices=["all", PlagiarismSnapshot.SourceKind.MARKETPLACE, PlagiarismSnapshot.SourceKind.ASSIGNMENTS],
            default="all",
            help="Refresh all sources or a single source kind.",
        )
        parser.add_argument(
            "--lookback-days",
            type=int,
            default=180,
            help="Only use submissions from the last N days when available.",
        )
        parser.add_argument(
            "--sample-size",
            type=int,
            default=25,
            help="Maximum number of texts to keep in each corpus snapshot.",
        )
        parser.add_argument(
            "--author-sample-size",
            type=int,
            default=15,
            help="Maximum number of texts to keep in each author snapshot.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Refresh snapshots even when the source hash has not changed.",
        )

    def handle(self, *args, **options):
        selected_sources = [
            PlagiarismSnapshot.SourceKind.MARKETPLACE,
            PlagiarismSnapshot.SourceKind.ASSIGNMENTS,
        ] if options["source"] == "all" else [options["source"]]

        lookback_days = max(int(options["lookback_days"] or 0), 0)
        sample_size = max(int(options["sample_size"] or 1), 1)
        author_sample_size = max(int(options["author_sample_size"] or 1), 1)
        force = bool(options["force"])

        totals = {
            "corpus_refreshed": 0,
            "corpus_skipped": 0,
            "author_refreshed": 0,
            "author_skipped": 0,
        }

        for source_kind in selected_sources:
            summary = self._refresh_source(
                source_kind=source_kind,
                lookback_days=lookback_days,
                sample_size=sample_size,
                author_sample_size=author_sample_size,
                force=force,
            )
            for key, value in summary.items():
                totals[key] += value
            self.stdout.write(
                f"{source_kind}: corpus {summary['corpus_refreshed']} refreshed, "
                f"{summary['corpus_skipped']} skipped; authors {summary['author_refreshed']} refreshed, "
                f"{summary['author_skipped']} skipped."
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Plagiarism cache refresh complete: "
                f"{totals['corpus_refreshed']} corpus snapshots refreshed, "
                f"{totals['author_refreshed']} author snapshots refreshed."
            )
        )

    def _refresh_source(self, *, source_kind: str, lookback_days: int, sample_size: int, author_sample_size: int, force: bool) -> dict:
        config = SOURCE_CONFIG.get(source_kind)
        if config is None:
            raise CommandError(f"Unsupported source kind: {source_kind}")

        submission_model = config["submission_model"]
        source_field = config["source_field"]
        author_field = config["author_field"]

        base_qs = submission_model.objects.exclude(submission_text__isnull=True).exclude(submission_text__exact="")
        if lookback_days > 0:
            cutoff = timezone.now() - timedelta(days=lookback_days)
            window_qs = base_qs.filter(submitted_at__gte=cutoff)
        else:
            window_qs = base_qs

        summary = {
            "corpus_refreshed": 0,
            "corpus_skipped": 0,
            "author_refreshed": 0,
            "author_skipped": 0,
        }

        source_ids = list(base_qs.order_by().values_list(source_field, flat=True).distinct())
        for source_object_id in source_ids:
            texts = self._collect_texts(
                window_qs,
                source_field=source_field,
                source_object_id=source_object_id,
                sample_size=sample_size,
            )
            if not texts and lookback_days > 0:
                texts = self._collect_texts(
                    base_qs,
                    source_field=source_field,
                    source_object_id=source_object_id,
                    sample_size=sample_size,
                )
            if not texts:
                summary["corpus_skipped"] += 1
                continue

            _, changed = upsert_plagiarism_snapshot(
                cache_type=PlagiarismSnapshot.CacheType.CORPUS,
                source_kind=source_kind,
                texts=texts,
                source_object_id=source_object_id,
                sample_limit=sample_size,
                window_days=lookback_days,
                force=force,
            )
            if changed:
                summary["corpus_refreshed"] += 1
            else:
                summary["corpus_skipped"] += 1

        author_ids = list(base_qs.order_by().values_list(author_field, flat=True).distinct())
        for author_id in author_ids:
            texts = self._collect_texts(
                window_qs,
                source_field=author_field,
                source_object_id=author_id,
                sample_size=author_sample_size,
            )
            if not texts and lookback_days > 0:
                texts = self._collect_texts(
                    base_qs,
                    source_field=author_field,
                    source_object_id=author_id,
                    sample_size=author_sample_size,
                )
            if not texts:
                summary["author_skipped"] += 1
                continue

            _, changed = upsert_plagiarism_snapshot(
                cache_type=PlagiarismSnapshot.CacheType.AUTHOR,
                source_kind=source_kind,
                texts=texts,
                author_id=author_id,
                sample_limit=author_sample_size,
                window_days=lookback_days,
                force=force,
            )
            if changed:
                summary["author_refreshed"] += 1
            else:
                summary["author_skipped"] += 1

        return summary

    @staticmethod
    def _collect_texts(queryset, *, source_field: str, source_object_id: int, sample_size: int) -> list[str]:
        return list(
            queryset.filter(**{source_field: source_object_id})
            .order_by("-submitted_at")
            .values_list("submission_text", flat=True)[:sample_size]
        )
