import pytest
from django.contrib.auth import get_user_model

from apps.catalog.models import ModelDraftRevision, ModelProject
from apps.deployment.models import Build, BuildInputAsset
from apps.registry.tests.factories import create_model_version


@pytest.fixture
def owner(db):
    return get_user_model().objects.create_user("build-owner@example.com", "password123")


@pytest.mark.django_db
def test_build_source_kind_is_derived_from_exactly_one_source(owner):
    project = ModelProject.objects.create(owner=owner, name="Build Source Project")
    draft = project.current_draft
    revision = ModelDraftRevision.objects.create(draft=draft, number=1)
    build_draft = Build.objects.create(project=project, flavor="sklearn", source_draft_revision=revision)

    assert build_draft.source_kind == "draft"
    assert build_draft.source_draft_revision == revision
    assert build_draft.version is None

    version = create_model_version(project)
    build_version = Build.objects.create(project=project, flavor="sklearn", source_version=version)
    assert build_version.source_kind == "model_version"
    assert build_version.source_version == version


@pytest.mark.django_db
def test_build_input_asset_kinds(owner):
    project = ModelProject.objects.create(owner=owner, name="Build Input Kinds Project")
    version = create_model_version(project)
    build = Build.objects.create(project=project, flavor="sklearn", source_version=version)

    for kind, name in (
        ("model", "model.joblib"),
        ("reference_data", "reference.parquet"),
        ("source_code", "train_code.zip"),
        ("data_contract", "contract.json"),
    ):
        asset = BuildInputAsset.objects.create(build=build, kind=kind, name=name, s3_uri=f"s3://bucket/{name}")
        assert asset.kind == kind
        assert asset.name == name
