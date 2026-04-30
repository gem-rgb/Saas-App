from django.contrib import admin

from auth.models import Permission, RolePermission, RolePermissionTemplate, UserRole


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ("user", "role_type", "verified", "created_at", "updated_at")
    list_filter = ("role_type", "verified")
    search_fields = ("user__username", "user__email")
    autocomplete_fields = ("user",)


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "category")
    list_filter = ("category",)
    search_fields = ("code", "name", "description")


@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    list_display = ("role", "permission")
    list_filter = ("role__role_type", "permission__category")
    autocomplete_fields = ("role", "permission")


@admin.register(RolePermissionTemplate)
class RolePermissionTemplateAdmin(admin.ModelAdmin):
    list_display = ("role_type",)
    filter_horizontal = ("permissions",)
