from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


class UserRole(models.Model):
    """User role types and permissions"""
    
    class RoleType(models.TextChoices):
        STUDENT = "student", "Student"
        TASKER = "tasker", "Tasker"
        MANAGER = "manager", "Manager/Moderator"
        ADMIN = "admin", "Administrator"
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="user_role")
    role_type = models.CharField(
        max_length=20,
        choices=RoleType.choices,
        default=RoleType.STUDENT
    )
    
    # Role metadata
    verified = models.BooleanField(default=False)  # For tasker verification
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["-created_at"]
    
    def __str__(self):
        return f"{self.user.username} - {self.get_role_type_display()}"
    
    def is_student(self):
        return self.role_type == self.RoleType.STUDENT
    
    def is_tasker(self):
        return self.role_type == self.RoleType.TASKER
    
    def is_manager(self):
        return self.role_type == self.RoleType.MANAGER
    
    def is_admin(self):
        return self.role_type == self.RoleType.ADMIN


class Permission(models.Model):
    """Define available permissions"""
    
    class PermissionCategory(models.TextChoices):
        DASHBOARD = "dashboard", "Dashboard Access"
        MARKETPLACE = "marketplace", "Marketplace Access"
        ASSIGNMENTS = "assignments", "Assignment Management"
        CHAT = "chat", "Chat & Communication"
        VERIFICATION = "verification", "Assignment Verification"
        MODERATION = "moderation", "Moderation Tools"
        ADMIN = "admin", "Admin Tools"
    
    code = models.CharField(max_length=100, unique=True)  # e.g., "view_student_dashboard"
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    category = models.CharField(max_length=50, choices=PermissionCategory.choices)
    
    class Meta:
        ordering = ["category", "name"]
    
    def __str__(self):
        return self.name


class RolePermission(models.Model):
    """Map roles to permissions"""
    
    role = models.ForeignKey(
        'UserRole',
        on_delete=models.CASCADE,
        related_name="permissions"
    )
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ("role", "permission")
    
    def __str__(self):
        return f"{self.role.get_role_type_display()} - {self.permission.code}"


class RolePermissionTemplate(models.Model):
    """Template for default role permissions"""
    
    role_type = models.CharField(
        max_length=20,
        choices=UserRole.RoleType.choices,
        unique=True
    )
    permissions = models.ManyToManyField(Permission, related_name="role_templates")
    
    class Meta:
        verbose_name_plural = "Role Permission Templates"
    
    def __str__(self):
        return f"{self.get_role_type_display()} Permissions"
