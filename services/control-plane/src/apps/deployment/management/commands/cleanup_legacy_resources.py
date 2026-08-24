import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from infrastructure.docker import DockerClient
from infrastructure.harbor import HarborClient
from infrastructure.storage import S3Storage


class Command(BaseCommand):
    help = "Delete legacy users/* S3 artifacts and control-plane Docker runtime resources."

    def add_arguments(self, parser):
        parser.add_argument("--execute", action="store_true")
        parser.add_argument("--confirm", default="")
        parser.add_argument("--include-harbor", action="store_true")

    def handle(self, *args, **options):
        if not options["execute"]:
            self.stdout.write("Dry run: would delete S3 users/ and legacy build/training/drift/endpoint containers.")
            return
        confirmed = options["confirm"] == "DELETE-LEGACY-RESOURCES"
        enabled = os.environ.get("ALLOW_RESOURCE_CLEANUP") == "YES"
        if not (confirmed and enabled):
            raise CommandError(
                "Refusing cleanup. Set ALLOW_RESOURCE_CLEANUP=YES and pass " "--confirm DELETE-LEGACY-RESOURCES."
            )
        S3Storage().delete_prefix("users/")
        prefixes = (
            "build_",
            "build-",
            "local_tjob_",
            "training-",
            "evidently_",
            "drift-",
            "endpoint-",
        )
        for container in DockerClient().client.containers.list(all=True):
            if container.name.startswith(prefixes): # type: ignore[attr-defined]
                container.remove(force=True)
        if options["include_harbor"]:
            harbor = HarborClient()
            for repository in harbor.repositories(settings.HARBOR_USER_PROJECT):
                harbor.delete_repository(settings.HARBOR_USER_PROJECT, repository)
        self.stdout.write(self.style.SUCCESS("Managed S3, Docker, and selected Harbor resources were deleted."))
