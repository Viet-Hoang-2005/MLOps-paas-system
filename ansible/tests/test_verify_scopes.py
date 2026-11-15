"""Keep pre-CD infrastructure verification independent of application images."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ANSIBLE = ROOT / "ansible"


def load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_platform_waits_only_for_infrastructure():
    variables = load(ANSIBLE / "group_vars/all.yml")
    application_dir = ROOT / "k8s/gitops/production/applications"
    infrastructure = variables["core_platform_application_names"]
    workloads = variables["workload_application_names"]
    assert not set(infrastructure) & set(workloads)
    apps = {
        app["metadata"]["name"]: app
        for path in application_dir.rglob("*.yaml")
        if (app := load(path)).get("kind") == "Application"
    }
    assert all(
        int(apps[name]["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"]) < 12
        for name in infrastructure
    )
    assert {name for name in apps if name.startswith("mlops-prod-workload-")} <= set(
        workloads
    )
    assert "mlops-prod-platform-harbor" in infrastructure
    assert "mlops-prod-execution-argo" in infrastructure
    assert "mlops-prod-platform-routing" in workloads
    tasks = load(ANSIBLE / "roles/platform_core/tasks/main.yml")
    application_waits = [
        task for task in tasks if "reconciled_core_application" == task.get("register")
    ]
    assert len(application_waits) == 1
    assert "core_platform_application_names" in application_waits[0]["loop"]
    assert all(
        task.get("kubernetes.core.k8s_info", {}).get("name") != "mlops-paas-system"
        for task in tasks
    )


def test_root_health_is_required_only_after_cd():
    platform = load(ANSIBLE / "roles/verify/tasks/platform.yml")
    workloads = load(ANSIBLE / "roles/verify/tasks/workloads.yml")
    root = next(
        task for task in platform if task.get("register") == "verified_root_application"
    )
    assert "sync.revision" in root["failed_when"]
    assert "ComparisonError" in root["failed_when"]
    assert "health.status" not in root["failed_when"]
    root = next(
        task for task in workloads if task.get("register") == "verified_workload_root"
    )
    assert any("'Healthy'" in condition for condition in root["until"])
    assert any("'Synced'" in condition for condition in root["until"])


def test_workload_checks_and_secrets_do_not_leak_into_platform():
    platform = load(ANSIBLE / "roles/verify/tasks/platform.yml")
    workloads = load(ANSIBLE / "roles/verify/tasks/workloads.yml")
    variables = load(ANSIBLE / "group_vars/all.yml")
    assert not set(variables["platform_secret_namespaces"]) & set(
        variables["workload_secret_namespaces"]
    )
    for task in platform:
        info = task.get("kubernetes.core.k8s_info", {})
        assert info.get("namespace") != "mlops-paas-core"
        if info.get("kind") == "ExternalSecret":
            assert info["namespace"] == "{{ item }}"
            assert task["loop"] == "{{ platform_secret_namespaces }}"
    deployments = next(
        task
        for task in workloads
        if task.get("register") == "verified_workload_deployments"
    )
    assert len(deployments["loop"]) == 5
    assert all(item["namespace"] == "mlops-paas-core" for item in deployments["loop"])


def test_scope_dispatch_and_cli_override_have_separate_plays():
    dispatcher = load(ANSIBLE / "roles/verify/tasks/main.yml")
    assert len(dispatcher) == 4
    for scope in ["bootstrap", "platform", "training", "workloads"]:
        task = next(
            task
            for task in dispatcher
            if task.get("ansible.builtin.include_tasks") == f"{scope}.yml"
        )
        assert f"verify_scope in ['{scope}', 'all']" in task["when"]
        assert f"verify_phase | default('all') in ['{scope}', 'all']" in task["when"]
    plays = load(ANSIBLE / "site.yml")
    for play in plays:
        for role in play.get("roles", []):
            if isinstance(role, dict) and role.get("role") == "verify":
                assert (
                    f"verify_scope in ['{role['verify_phase']}', 'all']" in role["when"]
                )
                if role["verify_phase"] == "workloads":
                    assert "platform-core" not in play["tags"]
                    assert "verify-workloads" in play["tags"]


@pytest.mark.parametrize(
    ("tags", "scope", "expected"),
    [
        ("platform-core", None, ["platform"]),
        ("verify-workloads", "workloads", ["workloads"]),
        ("verify", "platform", ["platform"]),
        ("verify", "all", ["bootstrap", "platform", "training", "workloads"]),
    ],
)
def test_actual_ansible_tag_and_scope_dispatch(tmp_path, tags, scope, expected):
    """Run the real dispatcher with local spies instead of any cluster modules."""
    executable = shutil.which("ansible-playbook")
    if not executable:
        pytest.skip("Ansible control host is required for dispatch integration checks")
    plays = load(ANSIBLE / "site.yml")
    for play in plays:
        play["become"] = False
        play["gather_facts"] = False
    (tmp_path / "site.yml").write_text(yaml.safe_dump(plays), encoding="utf-8")
    role = tmp_path / "roles/verify"
    (role / "tasks").mkdir(parents=True)
    (role / "defaults").mkdir()
    shutil.copyfile(ANSIBLE / "roles/verify/tasks/main.yml", role / "tasks/main.yml")
    shutil.copyfile(
        ANSIBLE / "roles/verify/defaults/main.yml", role / "defaults/main.yml"
    )
    for phase in ["bootstrap", "platform", "training", "workloads"]:
        (role / f"tasks/{phase}.yml").write_text(
            yaml.safe_dump(
                [
                    {
                        "name": f"Observe {phase}",
                        "ansible.builtin.debug": {"msg": f"VERIFIED:{phase}"},
                        "tags": ["verify", f"verify-{phase}"],
                    }
                ]
            ),
            encoding="utf-8",
        )
    for name in [
        "preflight",
        "common",
        "k3s_master",
        "k3s_worker",
        "helm",
        "platform_core",
        "platform_training",
    ]:
        directory = tmp_path / f"roles/{name}/tasks"
        directory.mkdir(parents=True)
        (directory / "main.yml").write_text("[]", encoding="utf-8")
    inventory = {
        "all": {
            "vars": {
                "ansible_connection": "local",
                "bootstrap_k3s_cluster": True,
                "deploy_core_platform": True,
                "deploy_training_platform": True,
            },
            "children": {
                "master": {"hosts": {"master-node": {}}},
                "workers": {"hosts": {"worker-node": {}}},
            },
        }
    }
    (tmp_path / "inventory.yml").write_text(yaml.safe_dump(inventory), encoding="utf-8")
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nstdout_callback=default\n", encoding="utf-8")
    command = [
        executable,
        "-i",
        str(tmp_path / "inventory.yml"),
        str(tmp_path / "site.yml"),
        "--tags",
        tags,
    ]
    if scope:
        command += ["-e", f"verify_scope={scope}"]
    result = subprocess.run(
        command,
        check=False,
        env={**os.environ, "ANSIBLE_CONFIG": str(config), "ANSIBLE_NOCOLOR": "1"},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert re.findall(r'"msg": "VERIFIED:([a-z]+)"', result.stdout) == expected, (
        result.stdout
    )
