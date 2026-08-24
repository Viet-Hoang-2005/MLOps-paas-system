import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create the optional bootstrap administrator from environment variables."

    def handle(self, *args, **options):
        email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "").strip()
        password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
        if not email:
            self.stdout.write("BOOTSTRAP_ADMIN_EMAIL is empty; skipping bootstrap account.")
            return
        if len(password) < 12:
            raise CommandError("BOOTSTRAP_ADMIN_PASSWORD must contain at least 12 characters.")
        user, created = get_user_model().objects.get_or_create(
            email=email,
            defaults={"is_staff": True, "is_superuser": True},
        )
        if created:
            user.set_password(password)
            user.save(update_fields=["password"])
        self.stdout.write(self.style.SUCCESS("Bootstrap administrator is ready."))
