from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm, UserChangeForm

from .models import CustomUser


class CustomUserChangeForm(UserChangeForm):
    def clean_is_active(self):
        is_active = self.cleaned_data["is_active"]
        # Django's changeform POST runs inside a transaction through save_model().
        current = (
            CustomUser.objects.using(self.instance._state.db).select_for_update().filter(pk=self.instance.pk).first()
        )
        if current is None:
            raise forms.ValidationError("This account has already been deleted.")
        if is_active and current.purge_started_at is not None:
            raise forms.ValidationError("This account cannot be reactivated because permanent deletion has started.")
        self.instance.purge_started_at = current.purge_started_at
        self.instance.purge_next_attempt_at = None if is_active else current.purge_next_attempt_at
        self.instance.deleted_at = None if is_active else current.deleted_at
        return is_active


class CustomUserPasswordChangeForm(AdminPasswordChangeForm):
    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save(update_fields=["password"])
        return user


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    form = CustomUserChangeForm
    change_password_form = CustomUserPasswordChangeForm
    ordering = ("email",)
    list_display = ("email", "tenant_id", "is_active", "is_staff")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Tenant", {"fields": ("tenant_id",)}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),)
