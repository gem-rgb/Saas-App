from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from assignments.models import Assignment, AssignmentSubmission, TaskerProfile
from auth.models import UserRole
from operations.models import ManagerProfile
from marketplace.models import TaskOrder, TaskSubmission


@override_settings(
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        }
    }
)
class ManagerDashboardViewTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.manager = self.user_model.objects.create_user(
            username="ops-manager",
            email="ops-manager@example.com",
            password="testpass123",
        )
        ManagerProfile.objects.create(user=self.manager)

    def test_manager_dashboard_renders_without_queryset_slice_error(self):
        self.client.force_login(self.manager)

        response = self.client.get(reverse("operations:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Command Center")


@override_settings(
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        }
    }
)
class PlagiarismReviewViewTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.manager = self.user_model.objects.create_user(
            username="ops-manager",
            email="ops-manager@example.com",
            password="testpass123",
        )
        UserRole.objects.create(user=self.manager, role_type=UserRole.RoleType.MANAGER)
        ManagerProfile.objects.create(user=self.manager)
        self.student = self.user_model.objects.create_user(
            username="student-user",
            email="student-user@example.com",
            password="testpass123",
        )
        UserRole.objects.create(user=self.student, role_type=UserRole.RoleType.STUDENT)
        self.tasker = self.user_model.objects.create_user(
            username="tasker-user",
            email="tasker-user@example.com",
            password="testpass123",
        )
        UserRole.objects.create(user=self.tasker, role_type=UserRole.RoleType.TASKER)
        self.tasker_profile = TaskerProfile.objects.create(
            user=self.tasker,
            skills="Writing, Research",
            skill_level="advanced",
            bio="Tasker profile for plagiarism review tests.",
        )

    def test_marketplace_plagiarism_review_renders(self):
        task = TaskOrder.objects.create(
            student=self.student,
            title="Market Task",
            subject="Humanities",
            description="Explain the impact of repeated ideas in writing.",
            instructions="Use original wording and cite sources.",
            status=TaskOrder.Status.QUALITY_REVIEW,
            assigned_tasker=self.tasker_profile,
        )
        submission = TaskSubmission.objects.create(
            task=task,
            tasker=self.tasker_profile,
            version=1,
            status=TaskSubmission.Status.SUBMITTED,
            submission_text="This analysis discusses repeated ideas, citation patterns, and original phrasing.",
        )

        self.client.force_login(self.manager)
        response = self.client.get(reverse("operations:plagiarism_review", args=["marketplace", submission.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Plagiarism Review")
        self.assertContains(response, task.title)

    def test_assignment_plagiarism_review_renders(self):
        assignment = Assignment.objects.create(
            creator=self.student,
            title="Assignment Task",
            description="Review the originality of the response.",
            required_skills="Writing, Research",
            priority="high",
            status="in_progress",
            assigned_to=self.tasker_profile,
            estimated_hours=3,
        )
        submission = AssignmentSubmission.objects.create(
            assignment=assignment,
            tasker=self.tasker_profile,
            submission_text="This analysis discusses repeated ideas, citation patterns, and original phrasing.",
        )

        self.client.force_login(self.manager)
        response = self.client.get(reverse("operations:plagiarism_review", args=["assignments", submission.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Plagiarism Review")
        self.assertContains(response, assignment.title)
