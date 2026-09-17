import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.deployment.models import Build, Deployment, Endpoint
from apps.registry.models import ModelVersion


@pytest.mark.django_db
def test_project_api_uses_uuid_and_tenant_scope():
    owner = get_user_model().objects.create_user("owner@example.com", "password123")
    stranger = get_user_model().objects.create_user("stranger@example.com", "password123") 
    project = ModelProject.objects.create(owner=owner, name="NIDS")
    client = APIClient()
    client.force_authenticate(stranger)

    assert client.get(f"/api/models/{project.public_id}/").status_code == 404

    client.force_authenticate(owner)
    response = client.get(f"/api/models/{project.public_id}/")
    assert response.status_code == 200
    assert uuid.UUID(response.data["id"]) == project.public_id


@pytest.mark.django_db
def test_duplicate_project_name_returns_conflict_with_clear_message():
    owner = get_user_model().objects.create_user("duplicate-owner@example.com", "password123") 
    ModelProject.objects.create(owner=owner, name="NIDS")
    client = APIClient()
    client.force_authenticate(owner)

    response = client.post("/api/models/", {"name": "NIDS", "access_mode": "public"}, format="json")

    assert response.status_code == 409
    assert response.data == {
        "error": {
            "code": "conflict",
            "detail": "A model project named NIDS already exists.",
        }
    }


@pytest.mark.django_db
def test_project_list_returns_metadata_image_ready_and_deployed_lifecycle_statuses():
    owner = get_user_model().objects.create_user("lifecycle-owner@example.com", "password123") 
    metadata_project = ModelProject.objects.create(owner=owner, name="Metadata only")
    image_project = ModelProject.objects.create(owner=owner, name="Image ready")
    deployed_project = ModelProject.objects.create(owner=owner, name="Deployed")

    image_version = ModelVersion.objects.create(project=image_project, version="1")
    Build.objects.create(project=image_project, version=image_version, flavor="sklearn", status="ready")

    deployed_version = ModelVersion.objects.create(project=deployed_project, version="1")
    deployed_build = Build.objects.create(
        project=deployed_project,
        version=deployed_version,
        flavor="sklearn",
        status="ready",
    )
    Deployment.objects.create(version=deployed_version, build=deployed_build, status="healthy")

    client = APIClient()
    client.force_authenticate(owner)
    response = client.get("/api/models/")

    assert response.status_code == 200
    statuses = {project["name"]: project["lifecycle_status"] for project in response.data["results"]}
    assert statuses == {
        metadata_project.name: "metadata",
        image_project.name: "image_ready",
        deployed_project.name: "deployed",
    }


@pytest.mark.django_db
def test_project_list_returns_latest_active_endpoint_for_the_owner():
    owner = get_user_model().objects.create_user("endpoint-owner@example.com", "password123") 
    project = ModelProject.objects.create(owner=owner, name="NIDS")
    version = ModelVersion.objects.create(project=project, version="1")
    build = Build.objects.create(project=project, version=version, flavor="xgboost", status="ready")
    deployment = Deployment.objects.create(version=version, build=build, status="healthy")
    endpoint = Endpoint.objects.create(
        deployment=deployment,
        public_url="http://localhost:5002/tenant/models/project/version",
        health_status="healthy",
    )

    client = APIClient()
    client.force_authenticate(owner)
    response = client.get("/api/models/")

    assert response.status_code == 200
    active_endpoint = response.data["results"][0]["active_endpoint"]
    assert active_endpoint == {
        "id": str(endpoint.public_id),
        "deployment_id": str(deployment.public_id),
        "version_id": str(version.public_id),
        "url": f"{endpoint.public_url}/predict",
        "health_url": f"{endpoint.public_url}/health",
        "health_status": "healthy",
        "deployment_status": "healthy",
        "last_checked_at": None,
    }
