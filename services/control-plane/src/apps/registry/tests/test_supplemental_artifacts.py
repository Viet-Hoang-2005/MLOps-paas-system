from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
import pytest
from rest_framework.exceptions import ValidationError

from apps.catalog.models import ModelProject
from apps.catalog.tests.test_preview_lifecycle import MemoryStorage
from apps.deployment.models import Build
from apps.registry.models import ModelArtifact, ModelVersion
from apps.registry.services.versions import add_supplemental_artifacts
from apps.registry.api.serializers import ModelVersionSerializer
from common.api.exceptions import Conflict


@pytest.fixture
def version_with_model_source(db):
    user = get_user_model().objects.create_user("supp-owner@example.com", "password123")
    project = ModelProject.objects.create(owner=user, name="Supplemental Test")
    version = ModelVersion.objects.create(project=project, version="1")
    Build.objects.create(project=project, version=version, status="ready")
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


@pytest.mark.django_db
def test_supplemental_summary_preserves_registered_snapshot(version_with_model_source):
    _, version, user = version_with_model_source
    version.metrics_summary = {"accuracy": 0.9}
    version.save(update_fields=["metrics_summary"])
    storage = MemoryStorage()
    add_supplemental_artifacts(
        version=version,
        actor=user,
        metrics_file=SimpleUploadedFile("metrics.json", b'{"precision": 0.8}'),
        storage=storage,
    )

    version.refresh_from_db()
    assert version.metrics_summary == {"accuracy": 0.9}
    summary = ModelVersionSerializer(version).data["supplemental_summaries"]["metrics"]
    assert summary["value"] == {"precision": 0.8}
    assert summary["uploaded_by"] == user.email

    with pytest.raises(Conflict):
        add_supplemental_artifacts(
            version=version,
            actor=user,
            metrics_file=SimpleUploadedFile("metrics2.json", b'{"recall": 0.7}'),
            storage=storage,
        )


@pytest.mark.django_db
def test_supplemental_summary_rejects_existing_keys_and_pickle(version_with_model_source):
    _, version, user = version_with_model_source
    version.params_summary = {"max_depth": 5}
    version.save(update_fields=["params_summary"])
    storage = MemoryStorage()
    with pytest.raises(ValidationError):
        add_supplemental_artifacts(
            version=version,
            actor=user,
            params_file=SimpleUploadedFile("params.json", b'{"max_depth": 9}'),
            storage=storage,
        )
    with pytest.raises(ValidationError):
        add_supplemental_artifacts(
            version=version,
            actor=user,
            label_mapping_file=SimpleUploadedFile("labels.pkl", b"pickle"),
            storage=storage,
        )
    assert not version.artifacts.filter(kind__in=["params", "label_mapping"]).exists()


class _HookedStorage(MemoryStorage):
    """MemoryStorage that runs a callback when an object is uploaded."""

    def __init__(self, on_put=None):
        super().__init__()
        self.on_put = on_put

    def put(self, key, file, content_type="application/octet-stream"):
        if self.on_put:
            self.on_put(key)
        return super().put(key, file, content_type)


@pytest.mark.django_db
def test_supplemental_upload_holds_no_transaction_while_talking_to_s3(version_with_model_source, monkeypatch):
    import apps.registry.services.versions as versions_module

    _, version, user = version_with_model_source
    depth = {"value": 0}
    real_atomic = versions_module.transaction.atomic

    class CountingAtomic:
        def __init__(self, *args, **kwargs):
            self.inner = real_atomic(*args, **kwargs)

        def __enter__(self):
            depth["value"] += 1
            return self.inner.__enter__()

        def __exit__(self, *exc):
            depth["value"] -= 1
            return self.inner.__exit__(*exc)

    monkeypatch.setattr(versions_module.transaction, "atomic", CountingAtomic)
    storage = _HookedStorage(on_put=lambda key: pytest.fail("S3 upload inside a transaction") if depth["value"] else None)

    add_supplemental_artifacts(
        version=version,
        actor=user,
        source_code_file=SimpleUploadedFile("inference.py", b"def predict(): pass\n"),
        reference_data_file=SimpleUploadedFile("ref.csv", b"a,b\n1,2\n3,4\n"),
        storage=storage,
    )

    assert len(storage.objects) == 2


@pytest.mark.django_db
def test_losing_a_concurrent_upload_does_not_delete_the_winners_object(version_with_model_source):
    _, version, user = version_with_model_source
    winner_uri = "s3://test-bucket/winner/inference.py"

    def competitor_commits_first(key):
        ModelArtifact.objects.create(
            version=version, kind="source_code", name="inference.py", uri=winner_uri, checksum="w", size_bytes=1
        )

    storage = _HookedStorage(on_put=competitor_commits_first)
    storage.objects[winner_uri] = b"winner"

    with pytest.raises(Conflict, match="already has a source code artifact"):
        add_supplemental_artifacts(
            version=version,
            actor=user,
            source_code_file=SimpleUploadedFile("inference.py", b"def predict(): pass\n"),
            storage=storage,
        )

    assert storage.objects == {winner_uri: b"winner"}
    assert len(storage.deleted) == 1 and storage.deleted[0] != winner_uri


@pytest.mark.django_db
def test_project_deleted_during_upload_rolls_back_and_cleans_up(version_with_model_source):
    project, version, user = version_with_model_source

    def project_gets_deleted(key):
        ModelProject.objects.filter(pk=project.pk).update(deletion_state="deleting")

    storage = _HookedStorage(on_put=project_gets_deleted)

    with pytest.raises(Conflict, match="being deleted"):
        add_supplemental_artifacts(
            version=version,
            actor=user,
            source_code_file=SimpleUploadedFile("inference.py", b"def predict(): pass\n"),
            storage=storage,
        )

    assert storage.objects == {}
    assert not version.artifacts.filter(kind="source_code").exists()


@pytest.mark.django_db
def test_invalid_upload_never_reaches_storage(version_with_model_source):
    _, version, user = version_with_model_source
    storage = _HookedStorage()

    with pytest.raises(ValidationError):
        add_supplemental_artifacts(
            version=version,
            actor=user,
            source_code_file=SimpleUploadedFile("inference.py", b"def predict(): pass\n"),
            metrics_file=SimpleUploadedFile("metrics.json", b"not json"),
            storage=storage,
        )

    assert storage.objects == {}
