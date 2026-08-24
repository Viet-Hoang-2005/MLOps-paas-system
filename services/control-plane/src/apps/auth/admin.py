from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import CustomUser, UserAvatar


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    ordering = ("email",)
    list_display = ("email", "tenant_id", "is_active", "is_staff")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Tenant", {"fields": ("tenant_id",)}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),)


admin.site.register(UserAvatar)
