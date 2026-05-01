from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from assignments.models import TaskerProfile
from auth.models import UserRole
from marketplace.models import TaskConversationMessage, TaskConversationReadState, TaskOrder, TaskPayment, TaskPremiumSession, TaskSubmission
from subscriptions.models import Subscription, SubscriptionStatus, UserSubscription
from trust.models import CompetencyArea


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
                    "plagiarism_analysis": {
                        "model": "hybrid-plagiarism-detector-v1",
                        "risk_score": 82.5,
                        "risk_level": "high",
                        "decision": "High plagiarism risk",
                        "ai_score": 64.0,
                        "plagiarism_score": 91.0,
                        "stylometric_score": 42.0,
                        "semantic_score": 76.0,
                        "consistency_score": 18.0,
                        "perplexity_score": 67.0,
                        "citation_score": 55.0,
                        "behavior_score": 29.0,
                        "anomaly_score": 14.0,
                        "similarity_score": 93.0,
                        "signals": ["near_duplicate_to_corpus", "missing_citations"],
                        "recommendations": [
                            "Add concrete citations and a real reference list.",
                            "Review the submission for originality and citation coverage.",
                        ],
                        "top_matches": [
                            {
                                "rank": 1,
                                "score": 93.0,
                                "excerpt": "Plants use sunlight and chlorophyll for energy conversion in a clear explanation.",
                            }
                        ],
                    },
                }
            },
        )

        self.client.force_login(self.manager)
        response = self.client.get(reverse("marketplace:task_detail", args=[self.task.pk]))

        self.assertContains(response, "AI verification")
        self.assertContains(response, "Definition accuracy")
        self.assertContains(response, "Matched: sunlight")
        self.assertContains(response, "Plagiarism / AI risk")
        self.assertContains(response, "High plagiarism risk")

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


@override_settings(
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        }
    }
)
class PremiumSessionFlowTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()

        self.student = self._create_user("premium-student", UserRole.RoleType.STUDENT)
        self.tasker = self._create_user("premium-tasker", UserRole.RoleType.TASKER)
        self.manager = self._create_user("premium-manager", UserRole.RoleType.MANAGER)
        self.subject = CompetencyArea.objects.create(name="Mathematics", slug="mathematics", description="Math and exam prep")

        self.tasker_profile = TaskerProfile.objects.create(
            user=self.tasker,
            skills="Mathematics, Exam Revision",
            skill_level="expert",
            bio="Premium session tasker",
            is_active_tasker=True,
            approval_status=TaskerProfile.ApprovalStatus.APPROVED,
            admin_approved=True,
            kyc_status=TaskerProfile.KYCStatus.APPROVED,
            competency_status=TaskerProfile.CompetencyStatus.VERIFIED,
            interview_status=TaskerProfile.InterviewStatus.PASSED,
        )
        self.tasker_profile.competency_areas.add(self.subject)

        self.task = TaskOrder.objects.create(
            student=self.student,
            title="Exam revision support",
            subject="Mathematics",
            description="I need a dedicated revision session before the exam.",
            instructions="Focus on derivatives and word problems.",
            status=TaskOrder.Status.ASSIGNED,
            assigned_tasker=self.tasker_profile,
            deadline=timezone.now() + timedelta(days=4),
            estimated_hours=4,
            budget_cents=30000,
        )

        self.expert_subscription = Subscription.objects.create(
            name="Expert",
            subtitle="Premium sessions tier",
            features="Priority matching\nPremium exam sessions",
            feature_codes=["priority_matching", "premium_sessions"],
        )
        UserSubscription.objects.create(
            user=self.student,
            subscription=self.expert_subscription,
            status=SubscriptionStatus.ACTIVE,
            active=True,
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timedelta(days=30),
        )

    def _create_user(self, username, role_type):
        user = self.user_model.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="testpass123",
        )
        UserRole.objects.create(user=user, role_type=role_type)
        return user

    def test_standard_student_cannot_request_premium_session(self):
        standard_student = self._create_user("standard-student", UserRole.RoleType.STUDENT)
        self.client.force_login(standard_student)

        response = self.client.post(
            reverse("marketplace:task_premium_session_request", args=[self.task.pk]),
            {
                "session_type": TaskPremiumSession.SessionType.REVISION,
                "topic": "Derivatives revision",
                "scheduled_for": (timezone.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
                "duration_minutes": 90,
                "extra_fee_cents": 12000,
                "student_notes": "Please focus on exam-style questions.",
            },
        )

        self.assertRedirects(response, reverse("marketplace:task_detail", args=[self.task.pk]))
        self.assertFalse(TaskPremiumSession.objects.filter(task=self.task, student=standard_student).exists())

    @patch("marketplace.views.initialize_transaction")
    @patch("marketplace.views.verify_transaction")
    def test_premium_session_request_accept_pay_and_complete_flow(self, mock_verify_transaction, mock_initialize_transaction):
        mock_initialize_transaction.return_value = {
            "data": {
                "authorization_url": "https://paystack.example/checkout/premium-session",
                "reference": "paystack-session-ref",
            }
        }
        mock_verify_transaction.return_value = {
            "data": {
                "status": "success",
                "reference": "paystack-session-ref",
                "metadata": {
                    "premium_session_id": 1,
                },
            }
        }

        self.client.force_login(self.student)
        request_response = self.client.post(
            reverse("marketplace:task_premium_session_request", args=[self.task.pk]),
            {
                "session_type": TaskPremiumSession.SessionType.REVISION,
                "topic": "Derivatives revision",
                "scheduled_for": (timezone.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
                "duration_minutes": 90,
                "extra_fee_cents": 12000,
                "student_notes": "Please focus on exam-style questions.",
            },
        )

        self.assertRedirects(request_response, reverse("marketplace:task_detail", args=[self.task.pk]))
        session = TaskPremiumSession.objects.get(task=self.task, student=self.student)
        self.assertEqual(session.status, TaskPremiumSession.Status.REQUESTED)

        self.client.force_login(self.tasker)
        accept_response = self.client.post(
            reverse("marketplace:task_premium_session_accept", args=[self.task.pk, session.pk]),
        )

        self.assertRedirects(accept_response, reverse("marketplace:task_detail", args=[self.task.pk]))
        session.refresh_from_db()
        self.assertEqual(session.status, TaskPremiumSession.Status.AWAITING_PAYMENT)
        self.assertIsNotNone(session.payment)
        self.assertEqual(session.payment.payment_kind, TaskPayment.PaymentKind.PREMIUM_SESSION)
        self.assertEqual(session.payment.provider_reference, "paystack-session-ref")
        self.assertEqual(session.payment.metadata.get("authorization_url"), "https://paystack.example/checkout/premium-session")

        self.client.force_login(self.student)
        finalize_response = self.client.get(
            reverse("marketplace:task_premium_session_finalize", args=[self.task.pk, session.pk]),
            {"reference": "paystack-session-ref"},
        )

        self.assertRedirects(finalize_response, reverse("marketplace:task_detail", args=[self.task.pk]))
        session.refresh_from_db()
        self.assertEqual(session.status, TaskPremiumSession.Status.PAID)
        self.assertEqual(session.payment.status, TaskPayment.Status.AUTHORIZED)
        self.assertEqual(session.payment.escrow_status, "held")

        self.client.force_login(self.tasker)
        complete_response = self.client.post(
            reverse("marketplace:task_premium_session_complete", args=[self.task.pk, session.pk]),
        )

        self.assertRedirects(complete_response, reverse("marketplace:task_detail", args=[self.task.pk]))
        session.refresh_from_db()
        session.payment.refresh_from_db()
        self.assertEqual(session.status, TaskPremiumSession.Status.COMPLETED)
        self.assertEqual(session.payment.status, TaskPayment.Status.RELEASED)
        self.assertEqual(session.payment.escrow_status, "released")
