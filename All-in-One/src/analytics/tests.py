from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from agents.verification_service import run_assignment_verification
from analytics.models import PlagiarismSnapshot
from analytics.plagiarism_cache import load_plagiarism_cache_context, make_cache_key
from assignments.models import Assignment, AssignmentSubmission, TaskerProfile
from marketplace.models import TaskOrder, TaskSubmission


@override_settings(GOOGLE_GEMINI_API_KEY="")
class PlagiarismCacheRefreshTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.student = user_model.objects.create_user(
            username="cache-student",
            email="student@example.com",
            password="testpass123",
        )
        self.tasker_user = user_model.objects.create_user(
            username="cache-tasker",
            email="tasker@example.com",
            password="testpass123",
        )
        self.tasker_profile = TaskerProfile.objects.create(
            user=self.tasker_user,
            skills="Writing, Research",
            skill_level="advanced",
        )

        self.task = TaskOrder.objects.create(
            student=self.student,
            title="Marketplace task",
            subject="Writing",
            description="Prepare an evidence-based analysis of the topic.",
            instructions="Include citations and a short conclusion.",
            estimated_hours=4,
        )
        self.assignment = Assignment.objects.create(
            creator=self.student,
            title="Assignment brief",
            description="Write a focused report with real sources.",
            required_skills="Research, Writing",
            estimated_hours=5,
        )

        self.old_marketplace_submission = TaskSubmission.objects.create(
            task=self.task,
            tasker=self.tasker_profile,
            version=1,
            submission_text="Older marketplace draft with repeated phrasing and no citations.",
        )
        TaskSubmission.objects.filter(pk=self.old_marketplace_submission.pk).update(
            submitted_at=timezone.now() - timedelta(days=21)
        )

        self.recent_marketplace_submission = TaskSubmission.objects.create(
            task=self.task,
            tasker=self.tasker_profile,
            version=2,
            submission_text="Recent marketplace draft with citations, specifics, and a cleaner structure.",
        )
        TaskSubmission.objects.filter(pk=self.recent_marketplace_submission.pk).update(
            submitted_at=timezone.now() - timedelta(days=2)
        )

        self.assignment_submission = AssignmentSubmission.objects.create(
            assignment=self.assignment,
            tasker=self.tasker_profile,
            submission_text="Assignment submission with research, citations, and concrete recommendations.",
        )
        AssignmentSubmission.objects.filter(pk=self.assignment_submission.pk).update(
            submitted_at=timezone.now() - timedelta(days=1)
        )

    def test_refresh_command_builds_snapshots_and_verification_uses_cache(self):
        call_command(
            "refresh_plagiarism_cache",
            source="all",
            lookback_days=7,
            sample_size=10,
            author_sample_size=10,
            force=True,
            verbosity=0,
        )

        marketplace_corpus = PlagiarismSnapshot.objects.get(
            cache_key=make_cache_key(
                cache_type=PlagiarismSnapshot.CacheType.CORPUS,
                source_kind=PlagiarismSnapshot.SourceKind.MARKETPLACE,
                source_object_id=self.task.id,
            )
        )
        marketplace_author = PlagiarismSnapshot.objects.get(
            cache_key=make_cache_key(
                cache_type=PlagiarismSnapshot.CacheType.AUTHOR,
                source_kind=PlagiarismSnapshot.SourceKind.MARKETPLACE,
                author_id=self.tasker_user.id,
            )
        )
        assignment_corpus = PlagiarismSnapshot.objects.get(
            cache_key=make_cache_key(
                cache_type=PlagiarismSnapshot.CacheType.CORPUS,
                source_kind=PlagiarismSnapshot.SourceKind.ASSIGNMENTS,
                source_object_id=self.assignment.id,
            )
        )
        assignment_author = PlagiarismSnapshot.objects.get(
            cache_key=make_cache_key(
                cache_type=PlagiarismSnapshot.CacheType.AUTHOR,
                source_kind=PlagiarismSnapshot.SourceKind.ASSIGNMENTS,
                author_id=self.tasker_user.id,
            )
        )

        self.assertEqual(marketplace_corpus.sample_text_count, 1)
        self.assertEqual(
            marketplace_corpus.sample_texts,
            [self.recent_marketplace_submission.submission_text.strip()],
        )
        self.assertEqual(marketplace_author.sample_text_count, 1)
        self.assertEqual(assignment_corpus.sample_text_count, 1)
        self.assertEqual(assignment_author.sample_text_count, 1)

        cache_context = load_plagiarism_cache_context(
            source_kind="marketplace",
            source_object_id=self.task.id,
            author_id=self.tasker_user.id,
        )
        self.assertEqual(set(cache_context["cache_hits"]), {"corpus", "author"})
        self.assertEqual(cache_context["corpus_texts"], [self.recent_marketplace_submission.submission_text.strip()])

        verification = run_assignment_verification(
            content=self.recent_marketplace_submission.submission_text,
            title=self.task.title,
            description=self.task.description,
            required_skills=self.task.subject,
            instructions=self.task.instructions,
            submission_source="marketplace",
            source_object_id=self.task.id,
            author_id=self.tasker_user.id,
            submission_id=self.recent_marketplace_submission.id,
        )
        self.assertEqual(verification["plagiarism_cache_mode"], "snapshot")
        self.assertIn("corpus", verification["plagiarism_cache_hits"])
        self.assertIn("author", verification["plagiarism_cache_hits"])
        self.assertIn("plagiarism_detection", [check["check_type"] for check in verification["checks"]])
