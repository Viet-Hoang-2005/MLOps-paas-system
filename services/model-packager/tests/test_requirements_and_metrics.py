"""Protected-package filtering, Dockerfile failure semantics and strict-JSON callbacks."""

import json
import math
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from src import io, tasks
from src.image_build import (
    PROTECTED_PACKAGES,
    filter_protected_requirements,
    filter_mlflow_requirements,
    normalize_mlflow_requirements,
    render_dockerfile,
    requirement_name,
    write_build_context,
)
from src.security import PackageSecurityError, validate_safe_requirements


@pytest.mark.parametrize(
    "line",
    [
        "fastapi",
        "fastapi==0.163.2",
        "FastAPI>=0.1",
        "fastapi [all] == 0.50.0",
        "fastapi[all]~=0.50",
        "Fast_API==1",  # not the same package: kept below
        "starlette<0.30",
        "uvicorn!=0.1",
        "pydantic==1.10.0",
        "pydantic_core==2.0",
        "pydantic.core==2.0",
        "bentoml>1",
        "httpx===0.1",
        "numpy==2.0.0",
        "pyarrow==26.0.1",
        'fastapi==0.163.2; python_version >= "3.8"',
        "fastapi @ file:///x",
        "fastapi==0.163.2 # pinned",
    ],
)
def test_protected_packages_are_dropped_in_every_spelling(line):
    kept, dropped = filter_protected_requirements(f"pandas==2.2.1\n{line}\nscikit-learn")
    if line.startswith("Fast_API"):
        assert dropped == [] and line in kept
        return
    assert dropped == [line]
    assert kept == "pandas==2.2.1\nscikit-learn"


def test_old_filter_hole_is_closed():
    """The grep pattern anchored the name to the end of the line, so a version let it through."""
    kept, dropped = filter_protected_requirements("fastapi==0.163.2\nrequests")
    assert dropped == ["fastapi==0.163.2"] and kept == "requests"


def test_continuation_lines_cannot_hide_a_protected_package():
    kept, dropped = filter_protected_requirements("numpy\nfastapi \\\n  ==0.50.0\npandas")
    assert kept == "pandas"
    assert len(dropped) == 2
    assert dropped[0] == "numpy"
    assert dropped[1].startswith("fastapi")


def test_blank_lines_and_comments_are_ignored_and_names_are_normalized():
    assert filter_protected_requirements("\n# note\n   \n") == ("", [])
    assert requirement_name("Scikit_Learn==1") == "scikit-learn"
    assert requirement_name("==1.0") is None
    assert {
        "fastapi",
        "pydantic-core",
        "mlflow",
        "mlflow-skinny",
        "mlflow-tracing",
        "numpy",
        "pyarrow",
    } <= PROTECTED_PACKAGES


def test_platform_mlflow_family_is_normalized_without_dropping_model_dependencies():
    assert normalize_mlflow_requirements(
        ["numpy==1.26.4", "MLflow==3.11.1", "mlflow_skinny==3.11.1", "mlflow-tracing==3.11.1"]
    ) == ["numpy==1.26.4", "mlflow==3.18.0"]
    assert normalize_mlflow_requirements(None) == ["mlflow==3.18.0"]


def test_archive_mlflow_pins_are_filtered_for_packager_validation_only():
    assert filter_mlflow_requirements("numpy==1.26.4\nmlflow==3.11.1\nmlflow-skinny==3.11.1\n") == "numpy==1.26.4"


@pytest.mark.parametrize("line", ["==1.0", "<2", "; python_version<'3'", "$(whoami)"])
def test_lines_without_a_package_name_are_refused(line):
    with pytest.raises(ValueError, match="Unrecognised"):
        filter_protected_requirements(f"numpy\n{line}")


@pytest.mark.parametrize("line", ["-r other.txt", "--requirement other.txt", "-c c.txt", "--constraint c.txt"])
def test_nested_requirement_files_are_rejected(line):
    with pytest.raises(PackageSecurityError):
        validate_safe_requirements(f"numpy\n{line}")


def test_dockerfile_never_swallows_an_install_failure():
    dockerfile = render_dockerfile("base:latest", has_requirements=True)
    install = next(line for line in dockerfile.splitlines() if "pip install" in line)
    assert "||" not in install and "echo" not in install
    assert "-c /tmp/constraints.txt" in install
    # The only tolerated failure is "nothing to pin", never the install itself.
    assert "grep" in dockerfile and dockerfile.count("|| true") == 1
    assert "grep -i -v" not in dockerfile and "safe_requirements" not in dockerfile


def test_dockerfile_without_requirements_installs_nothing():
    dockerfile = render_dockerfile("base:latest", has_requirements=False)
    assert "pip" not in dockerfile and dockerfile.endswith("COPY model /app/model_artifact\n")


def test_build_context_uses_the_filtered_requirements(tmp_path):
    detail = Mock()
    kept = write_build_context(
        tmp_path,
        "base:latest",
        "numpy==2.0.0\npyarrow==26.0.1\nscikit-learn==1.7.2\nfastapi==0.163.2\n",
        detail,
    )
    assert kept == "scikit-learn==1.7.2"
    assert (tmp_path / "requirements.txt").read_text() == "scikit-learn==1.7.2\n"
    assert "fastapi" not in (tmp_path / "requirements.txt").read_text()
    log_messages = [call.args[0] for call in detail.call_args_list]
    assert any("numpy==2.0.0" in message for message in log_messages)
    assert any("pyarrow==26.0.1" in message for message in log_messages)
    assert any("fastapi==0.163.2" in message for message in log_messages)
    assert "pip install" in (tmp_path / "Dockerfile").read_text()
    kept = write_build_context(
        tmp_path,
        "base:latest",
        "numpy==2.0.0\nmlflow==2.13.2\nmlflow_skinny==2.13.2\nmlflow-tracing==2.13.2\n",
        detail,
    )
    assert kept == ""
    assert "mlflow" not in (tmp_path / "requirements.txt").read_text()
    write_build_context(tmp_path, "base:latest", "fastapi==0.163.2", detail)
    assert "pip" not in (tmp_path / "Dockerfile").read_text()


# ---- NaN / Infinity ---------------------------------------------------------------------------


def test_finite_json_replaces_non_finite_numbers_everywhere():
    value = {"a": float("nan"), "b": [1.0, float("inf"), {"c": -math.inf}], "d": "nan", "e": 2}
    assert io.finite_json(value) == {"a": None, "b": [1.0, None, {"c": None}], "d": "nan", "e": 2}
    json.dumps(io.finite_json(value), allow_nan=False)


def test_callback_with_nan_is_sent_as_strict_json():
    """`requests` serializes with allow_nan=False, so a raw NaN made every delivery fail."""
    sent = []

    def post(url, json=None, **kwargs):
        import json as stdlib_json

        stdlib_json.dumps(json, allow_nan=False)
        sent.append(json)
        return SimpleNamespace(status_code=200)

    io.post_webhook(
        "http://callback",
        {"build_id": "b", "metrics_summary": {"loss": float("nan")}},
        SimpleNamespace(post=post),
        {},
    )
    assert sent == [{"build_id": "b", "metrics_summary": {"loss": None}}]


def test_notify_task_cleans_a_context_prepared_with_nan(tmp_path, monkeypatch):
    (tmp_path / "webhook_payload.json").write_text(
        '{"build_id": "b", "metrics_summary": {"loss": NaN}}', encoding="utf-8"
    )
    posted = Mock()
    monkeypatch.setattr(tasks, "post_webhook", posted)
    tasks.run_notify_task(str(tmp_path), "http://callback")
    assert posted.call_args.args[1]["metrics_summary"] == {"loss": None}
