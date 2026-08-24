import uuid

import pytest

from infrastructure.storage.paths import training_input_key, training_job_prefix


def test_training_path_has_no_version_namespace():
    project_id = uuid.uuid4()
    job_id = uuid.uuid4()
    prefix = training_job_prefix("T-ABC", project_id, job_id)
    assert prefix == f"users/T-ABC/models/{project_id}/training/jobs/{job_id}"


def test_training_path_rejects_traversal():
    with pytest.raises(ValueError):
        training_input_key("T-ABC", uuid.uuid4(), uuid.uuid4(), "code", "../secret")
