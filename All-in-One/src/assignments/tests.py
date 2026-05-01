from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from auth.models import UserRole
from assignments.models import Assignment, AssignmentSubmission, AssignmentVerification, AssignmentVerificationCheck, TaskerProfile
from operations.models import ManagerProfile


@override_settings(
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        }
    }
)
class AssignmentRubricUiTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.creator = self._create_user("creator-user", UserRole.RoleType.STUDENT)
        self.tasker = self._create_user("tasker-user", UserRole.RoleType.TASKER)
        self.manager = self._create_user("manager-user", UserRole.RoleType.MANAGER)
        ManagerProfile.objects.create(user=self.manager)

        self.tasker_profile = TaskerProfile.objects.create(
            user=self.tasker,
            skills="Writing, Editing",
            skill_level="advanced",
            bio="Tasker profile for rubric UI tests.",
        )

        self.assignment = Assignment.objects.create(
            creator=self.creator,
            title="Essay Review",
            description="Review the clarity of the essay response.",
            required_skills="Writing, Research",
            priority="high",
            status="in_progress",
            assigned_to=self.tasker_profile,
            deadline=timezone.now() + timedelta(days=2),
            estimated_hours=4,
            budget_cents=12000,
            verification_rubric={
                "title": "Essay Verification Rubric",
                "answer_type": "essay",
                "grading_style": "partial",
                "minimum_score": 70,
                "criteria": [
                    {
                        "name": "Thesis clarity",
                        "weight": 4,
                        "required_terms": ["thesis"],
                    },
                    {
                        "name": "Evidence use",
                        "weight": 3,
                        "required_terms": ["evidence", "citation"],
                    },
                ],
            },
        )

        self.submission = AssignmentSubmission.objects.create(
            assignment=self.assignment,
            tasker=self.tasker_profile,
            status=AssignmentSubmission.STATUS_CHOICES[0][0],
            submission_text="The essay has a strong thesis and evidence.",
        )

        self.verification = AssignmentVerification.objects.create(
            submission=self.submission,
            assignment=self.assignment,
            status=AssignmentVerification.VerificationStatus.COMPLETED,
            academic_field=AssignmentVerification.AcademicField.HUMANITIES,
            subfield="Writing",
            submission_type="document",
            overall_score=86.0,
            passed=True,
            verification_results={
                "source": "rubric",
                "overall_score": 86.0,
                "passed": True,
                "summary": "Rubric-based verification completed with a score of 86/100.",
                "grading_style": "partial",
                "minimum_score": 70,
                "plagiarism_analysis": {
                    "model": "hybrid-plagiarism-detector-v1",
                    "risk_score": 76.0,
                    "risk_level": "high",
                    "decision": "High plagiarism risk",
                    "signals": ["near_duplicate_to_corpus"],
                    "top_matches": [
                        {
                            "rank": 1,
                            "score": 88.0,
                            "excerpt": "The essay has a strong thesis and evidence with a similar structure.",
                        }
                    ],
                },
            },
            issues_found=[],
            suggestions=[],
            started_at=timezone.now(),
            completed_at=timezone.now(),
        )

        AssignmentVerificationCheck.objects.create(
            verification=self.verification,
            check_type="rubric_alignment",
            score=86.0,
            details={
                "criteria": [
                    {
                        "name": "Thesis clarity",
                        "score": 100,
                        "weight": 4,
                        "feedback": "Thesis is clear and focused.",
                        "matched_terms": ["thesis"],
                        "missing_terms": [],
                    },
                    {
                        "name": "Evidence use",
                        "score": 65,
                        "weight": 3,
                        "feedback": "Evidence is present but citation is missing.",
                        "matched_terms": ["evidence"],
                        "missing_terms": ["citation"],
                    },
                ]
            },
            passed=True,
        )

    def _create_user(self, username, role_type):
        user = self.user_model.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="testpass123",
        )
        UserRole.objects.create(user=user, role_type=role_type)
        return user

    def test_submit_page_shows_rubric_preview(self):
        self.client.force_login(self.tasker)
        response = self.client.get(reverse("assignments:submit_assignment", args=[self.assignment.pk]))

        self.assertContains(response, "AI Verification Rubric")
        self.assertContains(response, "Thesis clarity")
        self.assertContains(response, "Minimum 70/100")

    def test_assignment_detail_shows_criterion_breakdown(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse("assignments:assignment_detail", args=[self.assignment.pk]))

        self.assertContains(response, "AI verification")
        self.assertContains(response, "Thesis clarity")
        self.assertContains(response, "Matched: thesis")
        self.assertContains(response, "Missing: citation")
        self.assertContains(response, "Plagiarism / AI risk")
        self.assertContains(response, "High plagiarism risk")

    def test_assignment_detail_hides_plagiarism_without_subscription(self):
        self.client.force_login(self.creator)
        response = self.client.get(reverse("assignments:assignment_detail", args=[self.assignment.pk]))

        self.assertContains(response, "AI verification")
        self.assertNotContains(response, "Plagiarism / AI risk")
        self.assertContains(response, "Detailed plagiarism and rubric reports are included on the Expert plan.")
