import copy
import unittest
from pathlib import Path

import yaml

from k8s.validate.validate_execution_security import validate_runtime_health_processes


class RuntimeHealthProcessTests(unittest.TestCase):
    def resources(self):
        path = Path(__file__).resolve().parents[2] / "apps/base/control-plane/celery.yaml"
        return list(yaml.safe_load_all(path.read_text(encoding="utf-8")))

    def test_processes_are_scoped(self):
        self.assertEqual(validate_runtime_health_processes(self.resources()), [])

    def test_beat_cannot_roll_out_two_schedulers(self):
        resources = self.resources()
        beat = next(r for r in resources if r["metadata"]["name"] == "mlops-paas-celery-beat")
        beat["spec"]["strategy"]["type"] = "RollingUpdate"
        self.assertTrue(any("Recreate" in e for e in validate_runtime_health_processes(resources)))

    def test_worker_cannot_inherit_execution_secrets(self):
        resources = copy.deepcopy(self.resources())
        worker = next(r for r in resources if r["metadata"]["name"] == "mlops-paas-celery-health-worker")
        container = worker["spec"]["template"]["spec"]["containers"][0]
        container["envFrom"].append({"secretRef": {"name": "celery-worker-secret"}})
        self.assertTrue(any("broad" in e for e in validate_runtime_health_processes(resources)))

    def test_celery_deployments_remain_separate(self):
        resources = self.resources()
        self.assertEqual(len(resources), 3)
        self.assertTrue(all(r["kind"] == "Deployment" for r in resources))
        self.assertEqual({r["metadata"]["name"] for r in resources}, {
            "mlops-paas-celery-worker", "mlops-paas-celery-beat", "mlops-paas-celery-health-worker",
        })
