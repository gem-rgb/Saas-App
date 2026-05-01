import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from assignments.models import Assignment, AssignmentSubmission, TaskerProfile
from auth.models import UserRole
from auth.permissions import portal_url_for_user
from operations.models import ManagerApplication, ManagerProfile
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


@override_settings(
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        }
    }
)
class ManagerOnboardingFlowTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.manager = self.user_model.objects.create_user(
            username="manager-candidate",
            email="manager-candidate@example.com",
            password="testpass123",
        )
        UserRole.objects.create(user=self.manager, role_type=UserRole.RoleType.MANAGER)
        self.admin = self.user_model.objects.create_superuser(
            username="admin-user",
            email="admin-user@example.com",
            password="testpass123",
        )
        self.media_root = tempfile.mkdtemp(prefix="manager-onboarding-")
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)

    def _files(self):
        return {
            "cv_file": SimpleUploadedFile("manager-cv.pdf", b"cv-bytes", content_type="application/pdf"),
            "selfie_file": SimpleUploadedFile("selfie.png", b"selfie-bytes", content_type="image/png"),
            "id_front_file": SimpleUploadedFile("id-front.png", b"id-front-bytes", content_type="image/png"),
            "id_back_file": SimpleUploadedFile("id-back.png", b"id-back-bytes", content_type="image/png"),
        }

    def test_manager_onboarding_submits_cv_and_kyc_for_admin_review(self):
        self.client.force_login(self.manager)

        with self.settings(MEDIA_ROOT=self.media_root):
            response = self.client.get(reverse("operations:manager-onboarding"))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Manager onboarding")
            self.assertEqual(portal_url_for_user(self.manager), reverse("operations:manager-onboarding"))

            response = self.client.post(
                reverse("operations:manager-onboarding"),
                {
                    "title": "Regional Manager",
                    "bio": "Operations lead with field review experience.",
                    "years_experience": 5,
                    **self._files(),
                },
                follow=True,
            )

            self.assertEqual(response.status_code, 200)
            application = ManagerApplication.objects.get(user=self.manager)
            self.assertEqual(application.status, ManagerApplication.Status.SUBMITTED)
            self.assertTrue(application.cv_file.name)
            self.assertContains(response, "Manager onboarding submitted")

            self.client.force_login(self.admin)
            approve_response = self.client.post(
                reverse("operations:manager-application-review", args=[application.pk]),
                {
                    "action": "approve",
                    "decision_reason": "Approved after CV and KYC review.",
                },
                follow=True,
            )

            self.assertEqual(approve_response.status_code, 200)
            application.refresh_from_db()
            self.assertEqual(application.status, ManagerApplication.Status.APPROVED)
            self.assertIsNotNone(application.reviewed_by)
            self.assertEqual(application.reviewed_by, self.admin)
            self.assertTrue(ManagerProfile.objects.filter(user=self.manager, active=True).exists())
            self.assertEqual(portal_url_for_user(self.manager), reverse("operations:dashboard"))
