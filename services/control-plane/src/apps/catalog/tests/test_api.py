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

    response = client.post("/api/models/training-projects/", {"name": "NIDS", "access_mode": "public"}, format="json")

    assert response.status_code == 409
    assert response.data == {
        "error": {
            "code": "conflict",
            "detail": "A model project named NIDS already exists.",
        }
    }


@pytest.mark.django_db
def test_inactive_project_with_same_name_does_not_block_new_project():
    owner = get_user_model().objects.create_user("reuse-owner@example.com", "password123")
    # Projects deleted before names were suffixed, or still being deleted, keep the original name.
    ModelProject.objects.create(owner=owner, name="NIDS", is_active=False, deletion_state="deleted")
    ModelProject.objects.create(owner=owner, name="NIDS", is_active=False, deletion_state="deleting")
    client = APIClient()
    client.force_authenticate(owner)

    response = client.post("/api/models/training-projects/", {"name": "NIDS", "access_mode": "public"}, format="json")

    assert response.status_code == 201
    assert ModelProject.objects.filter(owner=owner, name="NIDS", is_active=True).count() == 1


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
    deployed_project.active_deployment = Deployment.objects.create(
        version=deployed_version, build=deployed_build, status="succeeded"
    )
    deployed_project.save(update_fields=["active_deployment"])

    client = APIClient()
    client.force_authenticate(owner)
    response = client.get("/api/models/")

    assert response.status_code == 200
    statuses = {project["name"]: project["lifecycle_status"] for project in response.data["results"]}
    assert statuses == {
        metadata_project.name: "preview",
        image_project.name: "registered",
        deployed_project.name: "running",
    }


@pytest.mark.django_db
def test_project_list_returns_latest_active_endpoint_for_the_owner():
    owner = get_user_model().objects.create_user("endpoint-owner@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="NIDS")
    version = ModelVersion.objects.create(project=project, version="1")
    build = Build.objects.create(project=project, version=version, flavor="xgboost", status="ready")
    deployment = Deployment.objects.create(version=version, build=build, status="succeeded")
    project.active_deployment = deployment
    project.save(update_fields=["active_deployment"])
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
        "version_number": version.version,
        "url": f"{endpoint.public_url}/predict",
        "health_url": f"{endpoint.public_url}/health",
        "health_status": "unknown",
        "deployment_status": "succeeded",
        "registration_status": "unregistered",
        "last_checked_at": None,
    }


@pytest.mark.django_db
def test_running_attributes_and_label_mapping_with_pickle_and_json(monkeypatch):
    import pickle
    from apps.registry.models import ModelArtifact

    owner = get_user_model().objects.create_user("attr-owner@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="NIDS-Attr")
    version = ModelVersion.objects.create(
        project=project,
        version="1",
        metrics_summary={"accuracy": 0.985, "f1_score": 0.978},
        params_summary={"n_estimators": 100, "max_depth": 5},
        insights_summary={"kind": "feature_importance", "items": [{"name": "col1", "value": 0.42}]},
    )
    build = Build.objects.create(project=project, version=version, flavor="xgboost", status="ready")
    deployment = Deployment.objects.create(version=version, build=build, status="succeeded")
    project.active_deployment = deployment
    project.save(update_fields=["active_deployment"])

    # Create pkl label mapping artifact
    pkl_bytes = pickle.dumps({0: "benign", 1: "attack"})
    ModelArtifact.objects.create(
        version=version,
        kind="label_mapping",
        name="labels.pkl",
        uri="s3://test-bucket/labels.pkl",
        size_bytes=len(pkl_bytes),
    )

    class FakeStorage:
        def parse_uri(self, uri):
            return "test-bucket", "labels.pkl"

        @property
        def client(self):
            class FakeClient:
                def get_object(self, **kwargs):
                    from io import BytesIO
                    return {"Body": BytesIO(pkl_bytes)}
            return FakeClient()

    from apps.catalog.services import snapshots
    monkeypatch.setattr(snapshots, "S3Storage", lambda: FakeStorage())

    client = APIClient()
    client.force_authenticate(owner)

    # Test running-attributes
    res = client.get(f"/api/models/{project.public_id}/running-attributes/")
    assert res.status_code == 200
    assert res.data["metrics"] == {"accuracy": 0.985, "f1_score": 0.978}
    assert res.data["params"] == {"n_estimators": 100, "max_depth": 5}
    assert res.data["insights"]["kind"] == "feature_importance"
    assert res.data["label_mapping"]["filename"] == "labels.pkl"
    assert res.data["label_mapping"]["mapping"] == {"0": "benign", "1": "attack"}

    # Test label-mapping standalone endpoint
    res_lm = client.get(f"/api/models/{project.public_id}/label-mapping/")
    assert res_lm.status_code == 200
    assert res_lm.data["filename"] == "labels.pkl"
    assert res_lm.data["mapping"] == {"0": "benign", "1": "attack"}

