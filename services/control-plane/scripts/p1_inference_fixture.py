"""Disposable inference metadata and tokens for the local browser smoke."""

import json
import sys
import uuid
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.auth.api.serializers import TenantTokenSerializer
from apps.catalog.models import ModelProject
from apps.deployment.models import Build, Deployment, Endpoint
from apps.registry.models import ModelVersion
from common.redis_client import redis_client


path = Path("/tmp/p1-browser-fixture.json")
mode = globals().get("P1_FIXTURE_MODE", "create")
if mode == "cleanup":
    if path.exists():
        data = json.loads(path.read_text())
        Deployment.objects.filter(version__project__public_id__in=data["projects"]).delete()
        get_user_model().objects.filter(public_id__in=data["owners"]).delete()
        for version in data["versions"]:
            redis_client().delete(f"model-version:{version}")
        path.unlink()
    print("Fixture cleaned.")
else:
    if path.exists():
        raise RuntimeError("A P1 browser fixture already exists; clean it first.")
    owner = get_user_model().objects.create_user(f"p1-browser-{uuid.uuid4()}@example.invalid")
    stranger = get_user_model().objects.create_user(f"p1-browser-{uuid.uuid4()}@example.invalid")
    token = TenantTokenSerializer.get_token(owner)
    expired = token.access_token
    expired.set_exp(from_time=timezone.now() - timedelta(hours=1), lifetime=timedelta(seconds=1))
    data = {"owners": [str(owner.public_id), str(stranger.public_id)], "projects": [], "versions": [],
        "access": str(token.access_token), "refresh": str(token), "expired": str(expired),
        "wrong_access": str(TenantTokenSerializer.get_token(stranger).access_token), "cookie": settings.AUTH_COOKIE_NAME}
    for mode in ("public", "private"):
        project = ModelProject.objects.create(owner=owner, name=f"P1 browser {mode}", access_mode=mode)
        version = ModelVersion.objects.create(project=project, version="p1", flavor="sklearn")
        build = Build.objects.create(project=project, version=version, flavor="sklearn", status="ready")
        deployment = Deployment.objects.create(version=version, build=build, status="succeeded", backend="docker")
        runtime = f"mlops-p1-inference-{mode}"
        Endpoint.objects.create(deployment=deployment, runtime_name=runtime, internal_url=f"http://{runtime}:5001", public_url=f"http://localhost:5002/{owner.tenant_id}/models/{project.public_id}/{version.public_id}")
        project.active_deployment = deployment
        project.save(update_fields=["active_deployment"])
        data["projects"].append(str(project.public_id))
        data["versions"].append(str(version.public_id))
        data[mode] = {"url": f"http://localhost:5002/{owner.tenant_id}/models/{project.public_id}/{version.public_id}/predict", "project": str(project.public_id), "version": str(version.public_id)}
    path.write_text(json.dumps(data))
    path.chmod(0o600)
    print(json.dumps(data))
