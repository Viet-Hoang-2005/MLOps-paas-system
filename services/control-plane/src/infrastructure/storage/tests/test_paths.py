import uuid

import pytest

from infrastructure.storage.paths import (
    build_input_prefix,
    dataset_snapshot_prefix,
    draft_asset_key,
    draft_prefix,
    training_input_key,
    training_job_prefix,
)


def test_training_path_has_no_version_namespace():
    project_id = uuid.uuid4()
    job_id = uuid.uuid4()
    prefix = training_job_prefix("T-ABC", project_id, job_id)
    assert prefix == f"users/T-ABC/models/{project_id}/training/jobs/{job_id}"


def test_training_path_rejects_traversal():
    with pytest.raises(ValueError):
        training_input_key("T-ABC", uuid.uuid4(), uuid.uuid4(), "code", "../secret")


def test_draft_path_and_asset_key():
    project_id = uuid.uuid4()
    draft_id = uuid.uuid4()
    prefix = draft_prefix("T-ABC", project_id, draft_id)
    assert prefix == f"users/T-ABC/models/{project_id}/draft/{draft_id}/"

    key = draft_asset_key("T-ABC", project_id, draft_id, "model", "model.joblib")
    assert key == f"users/T-ABC/models/{project_id}/draft/{draft_id}/assets/model/model.joblib"


def test_dataset_snapshot_prefix():
    project_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    prefix = dataset_snapshot_prefix("T-ABC", project_id, snapshot_id)
    assert prefix == f"users/T-ABC/models/{project_id}/datasets/{snapshot_id}/"


def test_build_input_prefix_supports_new_kinds():
    project_id = uuid.uuid4()
    build_id = uuid.uuid4()
    for kind in ("model", "reference_data", "source_code", "data_contract"):
        prefix = build_input_prefix("T-ABC", project_id, build_id, kind)
        assert prefix == f"users/T-ABC/models/{project_id}/builds/{build_id}/inputs/{kind}/"
