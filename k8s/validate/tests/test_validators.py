"""Focused negative tests for each standalone validator contract."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from k8s.validate.common import ValidationContext, identity, repository_root
from k8s.validate.validate_application_contract import (
    validate_lifecycle,
    validate_no_default_namespace,
)
from k8s.validate.validate_cluster_capacity import validate_pool
from k8s.validate.validate_execution_security import (
    validate as validate_execution_security,
)
from k8s.validate.validate_helm_sources import validate as validate_helm_sources
from k8s.validate.validate_redis_ha import validate as validate_redis_ha
from k8s.validate.validate_resource_ownership import (
    validate as validate_resource_ownership,
)
from k8s.validate.validate_runtime_logging import validate as validate_runtime_logging
from k8s.validate.validate_secrets import validate as validate_secrets
from k8s.validate.validate_supply_chain import validate_cd_workflow


class FakeContext:
    def __init__(self, *, applications=None, rendered=None, source_root=None):
        self.applications = applications or []
        self._rendered = rendered or {}
        self.source_root = source_root or repository_root()

    def render(self, path):
        return self._rendered.get(path, [])

    def render_helm(self, application, **_kwargs):
        return self._rendered.get((application.get("metadata") or {}).get("name"), [])

    def application(self, name):
        return next(
            (
                app
                for app in self.applications
                if (app.get("metadata") or {}).get("name") == name
            ),
            {},
        )


class CommonTests(unittest.TestCase):
    def test_repository_root_resolves_from_package_location(self):
        root = repository_root()
        self.assertTrue((root / "k8s" / "validate").is_dir())
        self.assertEqual(
            identity(
                {
                    "apiVersion": "v1",
                    "kind": "ConfigMap",
                    "metadata": {"name": "example"},
                }
            ),
            ("v1", "ConfigMap", "", "example"),
        )

    def test_context_caches_kustomize_render(self):
        with tempfile.TemporaryDirectory() as directory:
            context = ValidationContext(Path(directory), Path(directory))
            with (
                patch("k8s.validate.common.shutil.which", return_value="kustomize"),
                patch("k8s.validate.common.subprocess.run") as run,
            ):
                run.return_value.stdout = (
                    "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: cache\n"
                )
                first = context.render("k8s/example")
                second = context.render("k8s/example")
        self.assertEqual(first, second)
        self.assertEqual(run.call_count, 1)


class ValidatorNegativeTests(unittest.TestCase):
    def test_redis_ha_rejects_missing_sentinel_quorum(self):
        context = FakeContext(rendered={"k8s/platform/redis": [
            {"kind": "RedisReplication", "spec": {"clusterSize": 2, "nodeSelector": {"workload-type": "worker"}}},
            {"kind": "RedisSentinel", "spec": {"clusterSize": 3, "redisSentinelConfig": {"quorum": "1"}}},
        ]})
        self.assertTrue(any("quorum two" in error for error in validate_redis_ha(context)))

    def test_application_contract_rejects_missing_child_applications(self):
        self.assertTrue(
            any("exactly 34" in error for error in validate_lifecycle(FakeContext()))
        )

    def test_application_contract_rejects_default_destination(self):
        application = {
            "metadata": {"name": "default-target"},
            "spec": {"destination": {"namespace": "default"}},
        }
        errors = validate_no_default_namespace(FakeContext(applications=[application]))
        self.assertTrue(any("must not target" in error for error in errors))

    def test_resource_ownership_rejects_duplicate_identity(self):
        application = lambda name, path: {
            "metadata": {"name": name},
            "spec": {
                "source": {
                    "repoURL": "https://github.com/Viet-Hoang-2005/MLOps-paas-system.git",
                    "path": path,
                }
            },
        }
        resource = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "duplicate"},
        }
        context = FakeContext(
            applications=[
                application("first", "k8s/a"),
                application("second", "k8s/b"),
            ],
            rendered={"k8s/a": [resource], "k8s/b": [resource]},
        )
        self.assertTrue(
            any(
                "owned by both first and second" in error
                for error in validate_resource_ownership(context)
            )
        )

    def test_capacity_rejects_gpu_pool_without_taint(self):
        pool = {
            "spec": {
                "limits": {"nodes": 1},
                "template": {
                    "spec": {
                        "requirements": [
                            {
                                "key": "karpenter.sh/capacity-type",
                                "values": ["spot", "on-demand"],
                            },
                            {
                                "key": "node.kubernetes.io/instance-type",
                                "values": ["g4dn.xlarge", "g5.xlarge"],
                            },
                        ],
                        "nodeClassRef": {
                            "group": "karpenter.k8s.aws",
                            "kind": "EC2NodeClass",
                            "name": "training-gpu",
                        },
                        "expireAfter": "24h",
                    }
                },
                "disruption": {"consolidateAfter": "5m"},
            }
        }
        errors = validate_pool(
            pool, "gpu", "training-gpu", {"g4dn.xlarge", "g5.xlarge"}, gpu=True
        )
        self.assertTrue(any("nvidia.com/gpu" in error for error in errors))

    def test_supply_chain_rejects_oidc_on_promotion_job(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = root / ".github/workflows"
            workflow.mkdir(parents=True)
            (workflow / "cd.yml").write_text(
                """jobs:\n  build-and-push:\n    permissions:\n      contents: read\n      id-token: write\n    steps:\n      - run: aws-actions/configure-aws-credentials@v4\n      - run: IMAGE_REFERENCE=\"${IMAGE}@${DIGEST}\"\n      - run: cosign sign --yes \"${IMAGE_REFERENCE}\"\n      - run: cosign verify --certificate-identity=\"https://github.com/Viet-Hoang-2005/MLOps-paas-system/.github/workflows/cd.yml@refs/heads/main\" --certificate-oidc-issuer=\"https://token.actions.githubusercontent.com\"\n  gitops-promotion:\n    permissions:\n      id-token: write\n""",
                encoding="utf-8",
            )
            context = FakeContext(source_root=root)
            errors = validate_cd_workflow(
                context,
                {
                    "subject": "https://github.com/Viet-Hoang-2005/MLOps-paas-system/.github/workflows/cd.yml@refs/heads/main",
                    "issuer": "https://token.actions.githubusercontent.com",
                },
            )
        self.assertTrue(
            any("gitops-promotion must not receive" in error for error in errors)
        )

    def test_execution_security_rejects_missing_webhook_auth(self):
        context = FakeContext(
            rendered={
                "k8s/argo": [
                    {
                        "kind": "EventSource",
                        "metadata": {
                            "name": "webhook-eventsource",
                            "namespace": "argo-events",
                        },
                        "spec": {
                            "template": {"serviceAccountName": "argo-eventsource-sa"},
                            "webhook": {},
                        },
                    }
                ],
                "k8s/apps/overlays/production/control-plane": [],
            }
        )
        errors = validate_execution_security(context)
        self.assertTrue(
            any("six trusted execution endpoints" in error for error in errors)
        )

    def test_secrets_rejects_missing_colocated_targets(self):
        errors = validate_secrets(FakeContext())
        self.assertTrue(
            any("ExternalSecret targets must be" in error for error in errors)
        )

    def test_helm_validator_requires_direct_helm_addon(self):
        self.assertEqual(
            validate_helm_sources(FakeContext()),
            ["GitOps must define direct Helm Applications for upstream add-ons"],
        )

    def test_helm_validator_rejects_empty_chart_render(self):
        application = {
            "metadata": {"name": "empty-chart"},
            "spec": {
                "source": {
                    "repoURL": "https://example.test",
                    "chart": "example",
                    "targetRevision": "1.0.0",
                }
            },
        }
        errors = validate_helm_sources(FakeContext(applications=[application]))
        self.assertTrue(
            any("must render at least one resource" in error for error in errors)
        )


class RuntimeLoggingTests(unittest.TestCase):
    def context(self):
        root = repository_root()
        addon_path = root / "k8s/gitops/production/applications/addons"
        apps = [yaml.safe_load((addon_path / name).read_text()) for name in ("alloy.yaml", "loki.yaml")]
        template = yaml.safe_load((root / "k8s/argo/workflows/deploy-workflowtemplate.yaml").read_text())
        roles = list(yaml.safe_load_all((root / "k8s/argo/rbac.yaml").read_text()))
        return FakeContext(applications=apps, rendered={"k8s/argo": [template, *roles]})

    def test_current_runtime_logging_contract(self):
        self.assertEqual(validate_runtime_logging(self.context()), [])

    def test_collector_secret_access_and_tenant_callback_token_are_rejected(self):
        context = self.context()
        app = context.application("mlops-prod-addon-alloy")
        values = yaml.safe_load(app["spec"]["source"]["helm"]["values"])
        values["rbac"]["rules"].append({"resources": ["secrets"], "verbs": ["get"]})
        app["spec"]["source"]["helm"]["values"] = yaml.safe_dump(values)
        spec = context.render("k8s/argo")[0]["spec"]
        template = next(item for item in spec["templates"] if item["name"] == "apply-deployment")
        template["resource"]["manifest"] += "callback_token: unsafe\n"
        errors = validate_runtime_logging(context)
        self.assertTrue(any("read-only" in error for error in errors))
        self.assertTrue(any("never receive" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
