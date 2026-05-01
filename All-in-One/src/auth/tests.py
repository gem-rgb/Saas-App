from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from auth.forms import PUBLIC_ROLE_CHOICES, RoleSignupForm
from auth.models import UserRole


class PublicSignupTests(TestCase):
    def test_manager_role_is_not_available_publicly(self):
        form = RoleSignupForm(data={"role": UserRole.RoleType.MANAGER})

        self.assertFalse(form.is_valid())
        self.assertNotIn(UserRole.RoleType.MANAGER, [value for value, _ in PUBLIC_ROLE_CHOICES])


class StaffLoginViewTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.manager = self.user_model.objects.create_user(
            username="staff-manager",
            email="staff-manager@example.com",
            password="testpass123",
        )
        UserRole.objects.create(user=self.manager, role_type=UserRole.RoleType.MANAGER)

    def test_manager_staff_login_redirects_to_manager_portal(self):
        response = self.client.post(
            reverse("staff_login"),
            {"login": "staff-manager", "password": "testpass123"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Manager onboarding")

    def test_public_role_cannot_use_staff_login(self):
        student = self.user_model.objects.create_user(
            username="student-user",
            email="student-user@example.com",
            password="testpass123",
        )
        UserRole.objects.create(user=student, role_type=UserRole.RoleType.STUDENT)

        response = self.client.post(
            reverse("staff_login"),
            {"login": "student-user", "password": "testpass123"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Use the public login for student and tasker accounts.")
