from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from assignments.models import TaskerProfile
from auth.models import UserRole
from marketplace.models import TaskConversationMessage, TaskConversationReadState, TaskOrder, TaskSubmission


@override_settings(
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        }
    }
)
class TaskConversationVisibilityTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()

        self.student = self._create_user("student-user", UserRole.RoleType.STUDENT)
        self.tasker = self._create_user("tasker-user", UserRole.RoleType.TASKER)
        self.other_tasker = self._create_user("other-tasker", UserRole.RoleType.TASKER)
        self.manager = self._create_user("manager-user", UserRole.RoleType.MANAGER)

        self.tasker_profile = TaskerProfile.objects.create(
            user=self.tasker,
            skills="Python, Data Analysis",
            skill_level="expert",
            bio="Primary tasker",
        )
        self.other_tasker_profile = TaskerProfile.objects.create(
            user=self.other_tasker,
            skills="Writing, Editing",
            skill_level="advanced",
            bio="Secondary tasker",
        )

        self.task = TaskOrder.objects.create(
            student=self.student,
            title="Engineering Design Review",
            subject="Mechanical Engineering",
            description="Check the calculations and structure.",
            instructions="Return a polished shared update and keep internal notes private.",
            status=TaskOrder.Status.ASSIGNED,
            assigned_tasker=self.tasker_profile,
            deadline=timezone.now() + timedelta(days=2),
            estimated_hours=5,
            budget_cents=25000,
            metadata={
                "verification_rubric": {
                    "title": "Design Review Rubric",
                    "answer_type": "document",
                    "grading_style": "partial",
                    "minimum_score": 70,
                    "criteria": [
                        {
                            "name": "Definition accuracy",
                            "weight": 4,
                            "required_terms": ["sunlight", "energy conversion"],
                        },
                        {
                            "name": "Clarity",
                            "weight": 2,
                            "required_terms": ["clear"],
                        },
                    ],
                }
            },
        )

        self.shared_message = TaskConversationMessage.objects.create(
            task=self.task,
            sender=self.student,
            message="Shared student note",
            metadata={"visibility": "shared"},
        )
        self.shared_reply = TaskConversationMessage.objects.create(
            task=self.task,
            sender=self.tasker,
            message="Tasker shared update",
            metadata={"visibility": "shared"},
        )
        self.team_message = TaskConversationMessage.objects.create(
            task=self.task,
            sender=self.tasker,
            message="Task team only note",
            metadata={"visibility": "team"},
        )
        self.internal_message = TaskConversationMessage.objects.create(
            task=self.task,
            sender=self.manager,
            message="Manager only note",
            metadata={"visibility": "internal"},
        )

    def _create_user(self, username, role_type):
        user = self.user_model.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="testpass123",
        )
        UserRole.objects.create(user=user, role_type=role_type)
        return user

    def test_student_sees_only_shared_messages(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("marketplace:task_detail", args=[self.task.pk]))

        self.assertContains(response, "Conversation")
        self.assertContains(response, "Shared student note")
        self.assertContains(response, "Tasker shared update")
        self.assertNotContains(response, "Task team only note")
        self.assertNotContains(response, "Manager only note")

    def test_assigned_tasker_sees_shared_and_team_messages(self):
        self.client.force_login(self.tasker)
        response = self.client.get(reverse("marketplace:task_detail", args=[self.task.pk]))

        self.assertContains(response, "Shared student note")
        self.assertContains(response, "Tasker shared update")
        self.assertContains(response, "Task team only note")
        self.assertNotContains(response, "Manager only note")

    def test_manager_sees_all_messages(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse("marketplace:task_detail", args=[self.task.pk]))

        self.assertContains(response, "Shared student note")
        self.assertContains(response, "Tasker shared update")
        self.assertContains(response, "Task team only note")
        self.assertContains(response, "Manager only note")

    def test_tasker_unread_count_and_dashboard_shortcut_render(self):
        self.client.force_login(self.tasker)
        response = self.client.get(reverse("marketplace:task_detail", args=[self.task.pk]))

        self.assertContains(response, "1 unread message")
        self.assertContains(response, reverse("dashboard:tasker-dashboard"))
        state = TaskConversationReadState.objects.get(task=self.task, user=self.tasker)
        self.assertIsNotNone(state.last_read_at)

    def test_tasker_unread_count_clears_after_viewing(self):
        self.client.force_login(self.tasker)
        self.client.get(reverse("marketplace:task_detail", args=[self.task.pk]))
        response = self.client.get(reverse("marketplace:task_detail", args=[self.task.pk]))

        self.assertContains(response, "0 unread messages")

    def test_task_submit_page_shows_rubric_preview(self):
        self.client.force_login(self.tasker)
        response = self.client.get(reverse("marketplace:task_submit", args=[self.task.pk]))

        self.assertContains(response, "Verification Rubric")
        self.assertContains(response, "Definition accuracy")
        self.assertContains(response, "Minimum 70/100")

    def test_task_detail_shows_per_criterion_verification_results(self):
        TaskSubmission.objects.create(
            task=self.task,
            tasker=self.tasker_profile,
            version=1,
            status=TaskSubmission.Status.SUBMITTED,
            submission_text="Plants use sunlight and chlorophyll for energy conversion in a clear explanation.",
            ai_quality_score=88.0,
            quality_score=88.0,
            summary="Rubric-based verification completed with a score of 88/100.",
            metadata={
                "ai_verification": {
                    "source": "rubric",
                    "overall_score": 88.0,
                    "passed": True,
                    "summary": "Rubric-based verification completed with a score of 88/100.",
                    "grading_style": "partial",
                    "minimum_score": 70,
                    "checks": [
                        {
                            "check_type": "rubric_alignment",
                            "score": 88.0,
                            "details": {
                                "criteria": [
                                    {
                                        "name": "Definition accuracy",
                                        "score": 100,
                                        "weight": 4,
                                        "feedback": "Fully covered definition accuracy.",
                                        "matched_terms": ["sunlight", "energy conversion"],
                                        "missing_terms": [],
                                    },
                                    {
                                        "name": "Clarity",
                                        "score": 75,
                                        "weight": 2,
                                        "feedback": "Partial coverage for clarity.",
                                        "matched_terms": ["clear"],
                                        "missing_terms": [],
                                    },
                                ]
                            },
                            "issues": [],
                            "suggestions": [],
                            "passed": True,
                        }
                    ],
                    "criteria": [
                        {
                            "name": "Definition accuracy",
                            "score": 100,
                            "weight": 4,
                            "feedback": "Fully covered definition accuracy.",
                            "matched_terms": ["sunlight", "energy conversion"],
                            "missing_terms": [],
                        },
                        {
                            "name": "Clarity",
                            "score": 75,
                            "weight": 2,
                            "feedback": "Partial coverage for clarity.",
                            "matched_terms": ["clear"],
                            "missing_terms": [],
                        },
                    ],
                }
            },
        )

        self.client.force_login(self.tasker)
        response = self.client.get(reverse("marketplace:task_detail", args=[self.task.pk]))

        self.assertContains(response, "AI verification")
        self.assertContains(response, "Definition accuracy")
        self.assertContains(response, "Matched: sunlight")

    def test_student_can_post_shared_messages(self):
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("marketplace:task_message_post", args=[self.task.pk]),
            {
                "message": "I need a quick update.",
                "audience": "shared",
            },
        )

        self.assertRedirects(response, reverse("marketplace:task_detail", args=[self.task.pk]))
        message = TaskConversationMessage.objects.get(task=self.task, sender=self.student, message="I need a quick update.")
        self.assertEqual(message.metadata.get("visibility"), "shared")

    def test_tasker_can_post_team_notes(self):
        self.client.force_login(self.tasker)
        response = self.client.post(
            reverse("marketplace:task_message_post", args=[self.task.pk]),
            {
                "message": "Internal coordination note.",
                "audience": "team",
            },
        )

        self.assertRedirects(response, reverse("marketplace:task_detail", args=[self.task.pk]))
        message = TaskConversationMessage.objects.get(task=self.task, sender=self.tasker, message="Internal coordination note.")
        self.assertEqual(message.metadata.get("visibility"), "team")

    def test_unassigned_tasker_cannot_post(self):
        self.client.force_login(self.other_tasker)
        response = self.client.post(
            reverse("marketplace:task_message_post", args=[self.task.pk]),
            {
                "message": "I should not be able to send this.",
                "audience": "shared",
            },
        )

        self.assertEqual(response.status_code, 404)
