import logging

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.auth.services.bootstrap import ensure_admin_account, update_admin_account

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Create or update the administrator account from environment variables."

    def add_arguments(self, parser):
        parser.add_argument("--email", type=str, default=None, help="Administrator email")
        parser.add_argument("--password", type=str, default=None, help="Administrator password")
        parser.add_argument(
            "--confirm-update-existing", action="store_true",
            help="Explicitly grant superuser permissions and replace the password of an existing account.",
        )

    def handle(self, *args, **options):
        email = options.get("email")
        password = options.get("password")

        if password and len(password) < 8:
            raise CommandError("Administrator password must contain at least 8 characters.")

        if options.get("confirm_update_existing"):
            try:
                user = update_admin_account(email=email, password=password)
            except (ValueError, get_user_model().DoesNotExist) as exc:
                raise CommandError(str(exc)) from exc
        else:
            user, _ = ensure_admin_account(email=email, password=password)
        if user is None:
            logger.info("ADMIN_EMAIL is empty; skipping bootstrap account.")
