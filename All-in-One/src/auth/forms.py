from django import forms

from auth.models import UserRole


PUBLIC_ROLE_CHOICES = [
    (UserRole.RoleType.STUDENT, "Student"),
    (UserRole.RoleType.TASKER, "Tasker"),
    (UserRole.RoleType.MANAGER, "Manager"),
]


class RoleSignupForm(forms.Form):
    """Signup form that lets a new user pick their primary portal role."""

    role = forms.ChoiceField(
        choices=PUBLIC_ROLE_CHOICES,
        initial=UserRole.RoleType.STUDENT,
        help_text="Choose the portal experience you want to start with.",
    )

    field_order = ["username", "email", "role", "password1", "password2"]

    def clean_role(self):
        role = self.cleaned_data.get("role") or UserRole.RoleType.STUDENT
        valid_roles = {choice[0] for choice in PUBLIC_ROLE_CHOICES}
        if role not in valid_roles:
            raise forms.ValidationError("Select a valid role.")
        return role

    def signup(self, request, user):
        role = self.cleaned_data.get("role") or UserRole.RoleType.STUDENT
        UserRole.objects.update_or_create(
            user=user,
            defaults={
                "role_type": role,
                "verified": role == UserRole.RoleType.STUDENT,
            },
        )

        if role == UserRole.RoleType.TASKER:
            from assignments.models import TaskerProfile

            TaskerProfile.objects.get_or_create(
                user=user,
                defaults={"skills": ""},
            )
        elif role == UserRole.RoleType.MANAGER:
            from operations.models import ManagerProfile

            ManagerProfile.objects.get_or_create(user=user)
