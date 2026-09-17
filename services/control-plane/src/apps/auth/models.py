import uuid
from typing import Any

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


def avatar_path(instance, filename):
    user = getattr(instance, "user", instance)
    return f"users/{user.tenant_id}/avatar/{filename}"


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        extra_fields.pop("tenant_id", None)
        user: Any = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password) if password else user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    tenant_id = models.CharField(max_length=50, unique=True, db_index=True)
    full_name = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    pronouns = models.CharField(max_length=30, blank=True)
    company = models.CharField(max_length=150, blank=True)
    avatar = models.ImageField(upload_to=avatar_path, blank=True, null=True, max_length=1024)
    field_of_work = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    auth_provider = models.CharField(max_length=20, default="email")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = CustomUserManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def save(self, *args, **kwargs):
        if not self.public_id:
            self.public_id = uuid.uuid4()
        self.tenant_id = f"T-{self.public_id}"
        super().save(*args, **kwargs)

    def soft_delete(self):
        self.is_active = False
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_active", "deleted_at"])


class UserAvatar(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="avatar_history")
    image = models.ImageField(upload_to=avatar_path, max_length=1024)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Avatar {self.public_id} for {self.user.email}"
