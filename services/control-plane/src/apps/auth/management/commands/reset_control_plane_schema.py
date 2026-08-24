import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Drop and recreate only the configured control-plane PostgreSQL schema."

    def add_arguments(self, parser):
        parser.add_argument("--confirm", required=True)

    def handle(self, *args, **options):
        confirmed = options["confirm"] == "RESET-CONTROL-PLANE"
        enabled = os.environ.get("ALLOW_CONTROL_PLANE_RESET") == "YES"
        if not (confirmed and enabled):
            raise CommandError(
                "Refusing reset. Set ALLOW_CONTROL_PLANE_RESET=YES and pass " "--confirm RESET-CONTROL-PLANE."
            )
        if connection.vendor != "postgresql":
            raise CommandError("Schema reset is supported only for PostgreSQL.")
        schema = connection.ops.quote_name(settings.DB_SCHEMA)
        with connection.cursor() as cursor:
            cursor.execute(f"DROP SCHEMA {schema} CASCADE")
            cursor.execute(f"CREATE SCHEMA {schema}")
        self.stdout.write(self.style.SUCCESS(f"Recreated PostgreSQL schema {settings.DB_SCHEMA}."))
