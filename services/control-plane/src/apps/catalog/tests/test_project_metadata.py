import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from apps.catalog.models import ModelDraft, ModelProject
from apps.catalog.services.draft import ensure_project_draft
from apps.catalog.services.project_metadata import update_project_metadata
from apps.registry.models import ModelVersion


@pytest.fixture
def owner(db):
    return get_user_model().objects.create_user("be-project-owner@example.com", "password123")


@pytest.fixture
def project(owner):
    return ModelProject.objects.create(
        owner=owner,
        name="Fraud Detection Project",
        description="Initial fraud detection description",
        task_domain="binary_classification",
    )


@pytest.mark.django_db
def test_project_draft_one_to_one(project):
    draft = ensure_project_draft(project=project)
    assert draft is not None
    assert project.draft.id == draft.id

    with pytest.raises(IntegrityError):
        ModelDraft.objects.create(
            project=project,
            flavor="xgboost",
        )


@pytest.mark.django_db
def test_project_metadata_edit_no_version(project):
    assert ModelVersion.objects.filter(project=project).count() == 0

    update_project_metadata(
        project=project,
        name="Updated Fraud Project",
        description="Brand new description without creating version",
        task_domain="multiclass_classification",
    )

    project.refresh_from_db()
    assert project.name == "Updated Fraud Project"
    assert project.description == "Brand new description without creating version"
    assert project.task_domain == "multiclass_classification"
    assert ModelVersion.objects.filter(project=project).count() == 0
