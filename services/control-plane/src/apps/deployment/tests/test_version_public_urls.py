from importlib import import_module
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.catalog.models import ModelProject
from apps.deployment.models import Build, Deployment, Endpoint
from apps.registry.models import ModelVersion


@pytest.mark.django_db
def test_saved_gateway_urls_move_to_version_routes_and_can_be_restored():
    owner = get_user_model().objects.create_user("gateway-owner@example.test")
    project = ModelProject.objects.create(owner=owner, name="Gateway routes")
    version = ModelVersion.objects.create(project=project, version="1")
    build = Build.objects.create(project=project, version=version)
    first = Deployment.objects.create(version=version, build=build)
    second = Deployment.objects.create(version=version, build=build)
    old_url = f"https://gateway.example/{owner.tenant_id}/models/{project.public_id}/{version.public_id}"
    endpoint = Endpoint.objects.create(deployment=first, public_url=old_url, internal_url="http://worker:5001")
    custom = Endpoint.objects.create(deployment=second, public_url="https://custom.example/predict")
    migration_name = "0003_version_public_urls"
    migration = import_module(f"apps.deployment.migrations.{migration_name}")
    apps = MigrationExecutor(connection).loader.project_state([("deployment", migration_name)]).apps
    schema_editor = SimpleNamespace(connection=connection)

    migration.update_public_urls(apps, schema_editor)
    migration.update_public_urls(apps, schema_editor)
    endpoint.refresh_from_db()
    custom.refresh_from_db()
    assert endpoint.public_url == f"https://gateway.example/model-versions/{version.public_id}"
    assert endpoint.internal_url == "http://worker:5001"
    assert custom.public_url == "https://custom.example/predict"

    migration.restore_public_urls(apps, schema_editor)
    endpoint.refresh_from_db()
    assert endpoint.public_url == old_url
