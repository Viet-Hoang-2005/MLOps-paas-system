import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from infrastructure.runtime_logs import runtime_log_page


@pytest.fixture
def resource(settings):
    settings.LOKI_URL = "http://loki.test:3100"
    return SimpleNamespace(public_id=uuid.uuid4(), backend="argo", created_at=timezone.now() - timedelta(minutes=1))


def response(values):
    return Mock(
        json=lambda: {
            "status": "success",
            "data": {
                "resultType": "streams",
                "result": [
                    {"stream": {"namespace": "mlops-execution", "container": "main"}, "values": values},
                ],
            },
        }
    )


def test_log_pages_use_signed_resource_bound_cursor_and_redact_output(resource, monkeypatch):
    ns = int((timezone.now() - timedelta(seconds=20)).timestamp() * 1_000_000_000)
    get = Mock(return_value=response([[str(ns), "one"], [str(ns), "token=private-value"]]))
    monkeypatch.setattr("infrastructure.runtime_logs.requests.get", get)
    first = runtime_log_page(SimpleNamespace(query_params={}), resource, "build", Mock())
    assert first["next_offset"] == 2
    assert "private-value" not in " ".join(first["logs"])
    query = get.call_args.kwargs["params"]["query"]
    assert str(resource.public_id) in query and 'task_kind="build"' in query
    get.return_value = response([[str(ns), "one"], [str(ns), "token=private-value"], [str(ns + 1), "three"]])
    request = SimpleNamespace(query_params={"cursor": first["next_cursor"], "offset": "2"})
    second = runtime_log_page(request, resource, "build", Mock())
    assert second["logs"] == ["three"]
    other = SimpleNamespace(public_id=uuid.uuid4(), backend="argo", created_at=resource.created_at)
    with pytest.raises(ValidationError):
        runtime_log_page(request, other, "build", Mock())


def test_log_outage_keeps_cursor_and_leaves_status_polling_available(resource, monkeypatch):
    monkeypatch.setattr("infrastructure.runtime_logs.requests.get", Mock(side_effect=requests.Timeout))
    page = runtime_log_page(SimpleNamespace(query_params={}), resource, "deployment", Mock())
    assert page["logs"] == [] and page["log_error"] == "unavailable"
    again = runtime_log_page(
        SimpleNamespace(query_params={"cursor": page["next_cursor"]}), resource, "deployment", Mock()
    )
    assert again["next_cursor"] == page["next_cursor"]


def test_tampered_cursor_never_reaches_log_backend(resource, monkeypatch):
    get = Mock()
    monkeypatch.setattr("infrastructure.runtime_logs.requests.get", get)
    with pytest.raises(ValidationError):
        runtime_log_page(SimpleNamespace(query_params={"cursor": "tampered"}), resource, "training", Mock())
    get.assert_not_called()


def test_docker_keeps_existing_redis_contract(resource, settings):
    resource.backend = "docker"
    fallback = Mock(return_value=(["local output"], 3))
    assert runtime_log_page(SimpleNamespace(query_params={"offset": "2"}), resource, "build", fallback) == {
        "logs": ["local output"],
        "next_offset": 3,
    }
    fallback.assert_called_once_with(resource, 2)


@pytest.mark.django_db
def test_log_api_resolves_tenant_ownership_before_querying_loki(settings, monkeypatch):
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient

    from apps.catalog.models import ModelProject
    from apps.deployment.models import Build

    settings.LOKI_URL = "http://loki.test:3100"
    owner = get_user_model().objects.create_user("log-owner@example.test", "test-password")
    other = get_user_model().objects.create_user("log-other@example.test", "test-password")
    project = ModelProject.objects.create(owner=owner, name="task logs")
    build = Build.objects.create(project=project, backend="argo", flavor="sklearn", status="building")
    get = Mock(return_value=response([]))
    monkeypatch.setattr("infrastructure.runtime_logs.requests.get", get)
    client = APIClient()
    client.force_authenticate(other)
    assert client.get(f"/api/builds/{build.public_id}/logs/").status_code == 404
    get.assert_not_called()
