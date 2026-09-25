import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from apps.catalog.models import DraftAsset, ModelDraft, ModelDraftRevision, ModelProject


@pytest.fixture
def owner(db):
    return get_user_model().objects.create_user("owner@example.com", "password123")


@pytest.mark.django_db
def test_project_has_one_draft(owner):
    project = ModelProject.objects.create(owner=owner, name="Diabetes Project", task_domain="binary_classification")
    draft = project.current_draft

    assert isinstance(draft, ModelDraft)
    assert draft.project == project
    assert draft.revision == 1
    assert draft.saved_revision == 0
    assert draft.status == "editing"
    assert draft.is_dirty is True
    assert draft.can_build() is False


@pytest.mark.django_db
def test_cannot_create_second_draft_for_same_project(owner):
    project = ModelProject.objects.create(owner=owner, name="Duplicate Draft Project")
    ModelDraft.objects.create(project=project)

    with pytest.raises(IntegrityError):
        ModelDraft.objects.create(project=project)


@pytest.mark.django_db
def test_draft_asset_unique_per_kind(owner):
    project = ModelProject.objects.create(owner=owner, name="Asset Project")
    draft = project.current_draft

    DraftAsset.objects.create(
        draft=draft,
        kind="model",
        name="model.joblib",
        s3_uri="s3://bucket/model.joblib",
    )

    with pytest.raises(IntegrityError):
        DraftAsset.objects.create(
            draft=draft,
            kind="model",
            name="another_model.joblib",
            s3_uri="s3://bucket/another_model.joblib",
        )


@pytest.mark.django_db
def test_draft_readiness_and_can_build(owner):
    project = ModelProject.objects.create(owner=owner, name="Build Ready Project")
    draft = project.current_draft

    assert draft.has_mandatory_assets() is False
    assert draft.can_build() is False

    # Add model asset
    DraftAsset.objects.create(
        draft=draft,
        kind="model",
        name="model.joblib",
        s3_uri="s3://bucket/model.joblib",
    )
    assert draft.has_mandatory_assets() is False
    assert draft.can_build() is False

    # Add reference data asset
    DraftAsset.objects.create(
        draft=draft,
        kind="reference_data",
        name="reference.parquet",
        s3_uri="s3://bucket/reference.parquet",
    )
    assert draft.has_mandatory_assets() is True
    # Still cannot build because is_dirty (revision=1, saved_revision=0)
    assert draft.can_build() is False

    # Save draft (revision == saved_revision)
    draft.saved_snapshot = ModelDraftRevision.objects.create(draft=draft, number=draft.revision)
    draft.saved_revision = draft.revision
    draft.status = "ready"
    draft.save()
    assert draft.can_build() is True

    # If locked, cannot build
    draft.status = "locked"
    draft.save()
    assert draft.can_build() is False


@pytest.mark.django_db
def test_project_metadata_update_does_not_mutate_draft(owner):
    project = ModelProject.objects.create(owner=owner, name="Init Name", description="Desc 1")
    draft = project.current_draft
    initial_revision = draft.revision

    # Update project identity
    project.name = "Updated Name"
    project.description = "Updated Desc"
    project.task_domain = "multiclass_classification"
    project.save()

    draft.refresh_from_db()
    assert draft.revision == initial_revision
    assert draft.project.name == "Updated Name"
    assert draft.project.task_domain == "multiclass_classification"


@pytest.mark.django_db
def test_project_deletion_cascades_to_draft_and_assets(owner):
    project = ModelProject.objects.create(owner=owner, name="Cascade Project")
    draft = project.current_draft
    DraftAsset.objects.create(
        draft=draft,
        kind="model",
        name="model.joblib",
        s3_uri="s3://bucket/model.joblib",
    )

    draft_id = draft.id
    project.delete()

    assert not ModelDraft.objects.filter(id=draft_id).exists()
    assert not DraftAsset.objects.filter(draft_id=draft_id).exists()
