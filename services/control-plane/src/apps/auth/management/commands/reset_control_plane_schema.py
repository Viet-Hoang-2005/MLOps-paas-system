import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Drop and recreate control-plane schema and known first-party public legacy tables."

    LEGACY_PUBLIC_TABLES = (
        "paas_production_logs",
        "mlops_inference_events",
        "mlops_production_data",
        "paas_automatic_drift_outbox",
    )

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
            for table in self.LEGACY_PUBLIC_TABLES:
                cursor.execute(f"DROP TABLE IF EXISTS public.{connection.ops.quote_name(table)} CASCADE")
        self.stdout.write(
            self.style.SUCCESS(f"Recreated PostgreSQL schema {settings.DB_SCHEMA} and removed known legacy public tables.")
        )
