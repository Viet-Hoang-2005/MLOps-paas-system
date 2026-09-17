from unittest.mock import Mock, patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from redis.exceptions import RedisError

from apps.catalog.models import ModelProject
from apps.deployment.models import Build, Deployment, Endpoint
from apps.deployment.services import cache as cache_service
from apps.deployment.tasks import _mark_deployment_healthy, stop_deployment
from apps.registry.models import ModelVersion


class FakeRedisClient:
    def __init__(self):
        self.deleted_keys = []

    def delete(self, key):
        self.deleted_keys.append(key)
        return 1


class CacheInvalidationTests(TestCase):
    def test_invalidate_model_server_cache_success(self):
        fake_redis = FakeRedisClient()
        with patch.object(cache_service.Redis, "from_url", return_value=fake_redis):
            result = cache_service.invalidate_model_server_cache("test-version-uuid")

        self.assertTrue(result)
        self.assertEqual(fake_redis.deleted_keys, ["model-version:test-version-uuid"])

    def test_invalidate_model_server_cache_handles_redis_error(self):
        with patch.object(cache_service.Redis, "from_url", side_effect=RedisError("Connection refused")):
            result = cache_service.invalidate_model_server_cache("test-version-uuid")
        self.assertFalse(result)

    def test_invalidate_model_server_cache_empty_id(self):
        self.assertFalse(cache_service.invalidate_model_server_cache(""))
        self.assertFalse(cache_service.invalidate_model_server_cache(None))

    def test_mark_deployment_healthy_invalidates_cache(self):
        owner = get_user_model().objects.create_user("healthy-owner@example.com", "password123")
        project = ModelProject.objects.create(owner=owner, name="healthy project")
        version = ModelVersion.objects.create(project=project, version="1")
        build = Build.objects.create(project=project, version=version, flavor="sklearn", status="ready")
        deployment = Deployment.objects.create(version=version, build=build, backend="docker", status="deploying")
        Endpoint.objects.create(deployment=deployment, runtime_name="runtime-test", health_status="deploying")

        invalidated_ids = []
        with patch(
            "apps.deployment.tasks.invalidate_model_server_cache",
            side_effect=lambda version_id: invalidated_ids.append(version_id),
        ):
            _mark_deployment_healthy(deployment)

        self.assertIn(str(version.public_id), invalidated_ids)
        deployment.refresh_from_db()
        self.assertEqual(deployment.status, "healthy")

    def test_stop_deployment_invalidates_cache(self):
        owner = get_user_model().objects.create_user("stop-owner@example.com", "password123")
        project = ModelProject.objects.create(owner=owner, name="stop project")
        version = ModelVersion.objects.create(project=project, version="1")
        build = Build.objects.create(project=project, version=version, flavor="sklearn", status="ready")
        deployment = Deployment.objects.create(version=version, build=build, backend="docker", status="healthy")

        invalidated_ids = []
        fake_backend = Mock()
        fake_backend.stop.return_value = None

        with patch(
            "apps.deployment.tasks.invalidate_model_server_cache",
            side_effect=lambda version_id: invalidated_ids.append(version_id),
        ), patch("apps.deployment.tasks.deployment_backend", return_value=fake_backend):
            status = stop_deployment(str(deployment.public_id))

        self.assertEqual(status, "stopped")
        self.assertIn(str(version.public_id), invalidated_ids)
        deployment.refresh_from_db()
        self.assertEqual(deployment.status, "stopped")
