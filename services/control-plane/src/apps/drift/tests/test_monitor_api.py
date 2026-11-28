import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.drift.models import DriftMonitor, DriftRun
from apps.registry.models import ModelVersion


def _monitor_fixture(email="drift-monitor@example.com"):
    owner = get_user_model().objects.create_user(email, "password123")
    project = ModelProject.objects.create(owner=owner, name="NIDS")
    version = ModelVersion.objects.create(project=project, version="1")
    return owner, project, version


@pytest.mark.django_db
def test_monitor_api_returns_the_frontend_drift_contract():
    owner, project, version = _monitor_fixture()
    monitor = DriftMonitor.objects.create(
        version=version,
        reference_uri="s3://bucket/reference.csv",
        reference_name="reference.csv",
        name="default",
        trigger_threshold=1000,
    )
    run = DriftRun.objects.create(
        monitor=monitor,
        idempotency_key="monitor-contract",
        status="completed",
        report_html_uri="s3://bucket/report.html",
        drift_score=0.25,
        has_drift=True,
    )
    client = APIClient()
    client.force_authenticate(owner)

    response = client.get("/api/drift-monitors/")

    assert response.status_code == 200
    payload = response.data["results"][0]
    assert payload["project_id"] == str(project.public_id)
    assert payload["is_active"] is True
    assert payload["reference_name"] == "reference.csv"
    assert payload["runs"][0]["id"] == str(run.public_id)
    assert payload["runs"][0]["report_html_uri"] == "s3://bucket/report.html"
    assert payload["runs"][0]["has_drift"] is True


@pytest.mark.django_db
def test_monitor_list_filters_by_project_before_pagination_and_keeps_owner_scope():
    owner, project, version = _monitor_fixture()
    monitor = DriftMonitor.objects.create(version=version, name="target")
    other_project = ModelProject.objects.create(owner=owner, name="Other")
    other_version = ModelVersion.objects.create(project=other_project, version="1")
    DriftMonitor.objects.create(version=other_version, name="other")
    _, foreign_project, foreign_version = _monitor_fixture("other-owner@example.com")
    DriftMonitor.objects.create(version=foreign_version, name="foreign")
    client = APIClient()
    client.force_authenticate(owner)
    url = "/api/drift-monitors/"

    response = client.get(url, {"project_id": project.public_id, "page_size": 1})

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["next"] is None
    assert [item["id"] for item in response.data["results"]] == [str(monitor.public_id)]
    assert client.get(url).data["count"] == 2
    assert client.get(url, {"project_id": foreign_project.public_id}).data["count"] == 0
    assert client.get(url, {"project_id": "invalid"}).status_code == 400


@pytest.mark.django_db
def test_duplicate_monitor_returns_conflict_with_clear_message():
    owner, _project, version = _monitor_fixture("drift-duplicate@example.com")
    DriftMonitor.objects.create(version=version, reference_uri="s3://bucket/reference.csv", name="default")
    client = APIClient()
    client.force_authenticate(owner)

    response = client.post(
        "/api/drift-monitors/",
        {
            "version": str(version.public_id),
            "name": "default",
            "trigger_threshold": 2000,
        },
        format="json",
    )

    assert response.status_code == 409
    assert response.data == {
        "error": {
            "code": "conflict",
            "detail": "A drift monitor named default already exists for model version 1.",
        }
    }


@pytest.mark.django_db
def test_existing_monitor_can_be_updated_without_conflicting_with_itself():
    owner, _project, version = _monitor_fixture("drift-update@example.com")
    monitor = DriftMonitor.objects.create(version=version, reference_uri="s3://bucket/reference.csv", name="default")
    client = APIClient()
    client.force_authenticate(owner)

    response = client.patch(
        f"/api/drift-monitors/{monitor.public_id}/",
        {
            "name": "default",
            "trigger_threshold": 5000,
            "is_active": True,
        },
        format="json",
    )

    assert response.status_code == 200
    monitor.refresh_from_db()
    assert monitor.trigger_threshold == 5000


@pytest.mark.django_db
def test_completed_run_report_url_is_tenant_scoped_and_presigned(monkeypatch):
    owner, _project, version = _monitor_fixture("drift-report-owner@example.com")
    other = get_user_model().objects.create_user("drift-report-other@example.com", "password123")
    monitor = DriftMonitor.objects.create(version=version, reference_uri="s3://bucket/reference.csv", name="default")
    run = DriftRun.objects.create(
        monitor=monitor,
        idempotency_key="report-url",
        status="completed",
        report_html_uri="s3://bucket/report.html",
    )
    monkeypatch.setattr(
        "apps.drift.runs.api.S3Storage.presigned_get",
        lambda _self, uri, expires_in, **_: f"https://s3.example/{uri.removeprefix('s3://')}?ttl={expires_in}",
    )
    client = APIClient()
    client.force_authenticate(other)

    url = f"/api/drift-runs/{run.public_id}/report-url/"
    assert client.get(url).status_code == 404

    client.force_authenticate(owner)
    response = client.get(url)
    assert response.status_code == 200
    assert response.data == {"url": "https://s3.example/bucket/report.html?ttl=900"}


@pytest.mark.django_db
def test_report_url_is_unavailable_before_run_completes():
    owner, _project, version = _monitor_fixture("drift-report-pending@example.com")
    monitor = DriftMonitor.objects.create(version=version, reference_uri="s3://bucket/reference.csv", name="default")
    run = DriftRun.objects.create(
        monitor=monitor,
        idempotency_key="report-pending",
        status="running",
    )
    client = APIClient()
    client.force_authenticate(owner)

    response = client.get(f"/api/drift-runs/{run.public_id}/report-url/")

    assert response.status_code == 409
    assert response.data["error"]["detail"] == "The drift report is not available until the run has completed."
