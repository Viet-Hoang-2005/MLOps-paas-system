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
    render_dockerfile,
    requirement_name,
    write_build_context,
)
from src.security import PackageSecurityError, validate_safe_requirements


@pytest.mark.parametrize(
    "line",
    [
        "fastapi",
        "fastapi==0.50.0",
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
        'fastapi==0.50.0; python_version >= "3.8"',
        "fastapi @ file:///x",
        "fastapi==0.50.0 # pinned",
    ],
)
def test_protected_packages_are_dropped_in_every_spelling(line):
    kept, dropped = filter_protected_requirements(f"numpy==1.26\n{line}\nscikit-learn")
    if line.startswith("Fast_API"):
        assert dropped == [] and line in kept
        return
    assert dropped == [line]
    assert kept == "numpy==1.26\nscikit-learn"


def test_old_filter_hole_is_closed():
    """The grep pattern anchored the name to the end of the line, so a version let it through."""
    kept, dropped = filter_protected_requirements("fastapi==0.50.0\nrequests")
    assert dropped == ["fastapi==0.50.0"] and kept == "requests"


def test_continuation_lines_cannot_hide_a_protected_package():
    kept, dropped = filter_protected_requirements("numpy\nfastapi \\\n  ==0.50.0\npandas")
    assert kept == "numpy\npandas"
    assert len(dropped) == 1 and dropped[0].startswith("fastapi")


def test_blank_lines_and_comments_are_ignored_and_names_are_normalized():
    assert filter_protected_requirements("\n# note\n   \n") == ("", [])
    assert requirement_name("Scikit_Learn==1") == "scikit-learn"
    assert requirement_name("==1.0") is None
    assert {"fastapi", "pydantic-core"} <= PROTECTED_PACKAGES


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
    kept = write_build_context(tmp_path, "base:latest", "numpy==1.26\nfastapi==0.50.0\n", detail)
    assert kept == "numpy==1.26"
    assert (tmp_path / "requirements.txt").read_text() == "numpy==1.26\n"
    assert "fastapi" not in (tmp_path / "requirements.txt").read_text()
    assert "fastapi==0.50.0" in detail.call_args.args[0]
    assert "pip install" in (tmp_path / "Dockerfile").read_text()
    write_build_context(tmp_path, "base:latest", "fastapi==0.50.0", detail)
    assert "pip" not in (tmp_path / "Dockerfile").read_text()


# ---- NaN / Infinity ---------------------------------------------------------------------------


def test_finite_json_replaces_non_finite_numbers_everywhere():
    value = {"a": float("nan"), "b": [1.0, float("inf"), {"c": -math.inf}], "d": "nan", "e": 2}
    assert io.finite_json(value) == {"a": None, "b": [1.0, None, {"c": None}], "d": "nan", "e": 2}
    json.dumps(io.finite_json(value), allow_nan=False)


def test_training_summaries_with_nan_become_strict_json(tmp_path):
    mlops = tmp_path / "_mlops"
    mlops.mkdir()
    (mlops / "metrics.json").write_text('{"loss": NaN, "acc": 0.9, "grad": Infinity}', encoding="utf-8")
    (mlops / "params.json").write_text('{"lr": 0.1}', encoding="utf-8")
    (mlops / "model_insights.json").write_text('{"items": [{"value": -Infinity}]}', encoding="utf-8")
    summaries, _ = tasks.read_training_summaries(tmp_path)
    assert summaries["metrics_summary"] == {"loss": None, "acc": 0.9, "grad": None}
    json.dumps(summaries, allow_nan=False)


def test_callback_with_nan_is_sent_as_strict_json():
    """`requests` serializes with allow_nan=False, so a raw NaN made every delivery fail."""
    sent = []

    def post(url, json=None, **kwargs):  # noqa: A002 - mirrors requests
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

