from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
import pytest
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.catalog.tests.test_preview_lifecycle import MemoryStorage
from apps.deployment.models import Build
from apps.registry.models import ModelArtifact, ModelVersion
from apps.registry.services.versions import add_supplemental_artifacts
from common.api.exceptions import Conflict


@pytest.fixture
def version_with_model_source(db):
    user = get_user_model().objects.create_user("supp-owner@example.com", "password123")
    project = ModelProject.objects.create(owner=user, name="Supplemental Test")
    version = ModelVersion.objects.create(project=project, version="1")
    build = Build.objects.create(project=project, version=version, status="ready")
    # Model artifact from preview has kind="source"
    ModelArtifact.objects.create(
        version=version,
        kind="source",
        name="model.pkl",
        uri="s3://test-bucket/model.pkl",
        checksum="abc123model",
        size_bytes=1000,
        content_type="application/octet-stream",
    )
    return project, version, user


@pytest.mark.django_db
def test_add_supplemental_source_code_allowed_when_source_artifact_present(version_with_model_source):
    project, version, user = version_with_model_source
    storage = MemoryStorage()

    py_file = SimpleUploadedFile("inference.py", b"def predict(): pass\n", "text/x-python")

    # Should succeed and not be blocked by kind="source"
    updated_version = add_supplemental_artifacts(
        version=version,
        actor=user,
        source_code_file=py_file,
        storage=storage,
    )

    assert updated_version.artifacts.filter(kind="source_code").count() == 1
    artifact = updated_version.artifacts.get(kind="source_code")
    assert artifact.name == "inference.py"
    assert storage.objects[artifact.uri] == b"def predict(): pass\n"


@pytest.mark.django_db
def test_add_supplemental_reference_csv(version_with_model_source):
    _, version, user = version_with_model_source
    storage = MemoryStorage()
    csv_file = SimpleUploadedFile("reference.csv", b"feature,label\n1,normal\n", "text/csv")

    updated_version = add_supplemental_artifacts(
        version=version,
        actor=user,
        reference_data_file=csv_file,
        storage=storage,
    )

    artifact = updated_version.artifacts.get(kind="reference_data")
    assert artifact.name == "reference.csv"
    assert artifact.metadata["format"] == "csv"
    assert storage.objects[artifact.uri] == b"feature,label\n1,normal\n"


@pytest.mark.django_db
def test_add_supplemental_artifact_cleans_up_storage_on_failure(version_with_model_source):
    project, version, user = version_with_model_source
    storage = MemoryStorage()

    py_file = SimpleUploadedFile("inference.py", b"def predict(): pass\n", "text/x-python")

    # Simulate failure during ModelArtifact creation
    with patch("apps.registry.models.ModelArtifact.objects.create", side_effect=RuntimeError("db error")):
        with pytest.raises(RuntimeError, match="db error"):
            add_supplemental_artifacts(
                version=version,
                actor=user,
                source_code_file=py_file,
                storage=storage,
            )

    # Object uploaded to storage must be cleaned up
    assert len(storage.deleted) == 1
    assert len(storage.objects) == 0


@pytest.mark.django_db
def test_cannot_add_duplicate_supplemental_source_code(version_with_model_source):
    project, version, user = version_with_model_source
    storage = MemoryStorage()

    py_file = SimpleUploadedFile("inference.py", b"def predict(): pass\n", "text/x-python")
    add_supplemental_artifacts(
        version=version,
        actor=user,
        source_code_file=py_file,
        storage=storage,
    )

    py_file_second = SimpleUploadedFile("other.py", b"print(2)\n", "text/x-python")
    with pytest.raises(Conflict, match="already has a source code artifact"):
        add_supplemental_artifacts(
            version=version,
            actor=user,
            source_code_file=py_file_second,
            storage=storage,
        )
