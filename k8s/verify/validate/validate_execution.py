"""Validate Execution Plane resources: Argo Events, Argo Workflows, RBAC, and webhook security."""

from __future__ import annotations

import re
import pytest
import yaml

from ..utils import (
    ARGO_WEBHOOK_EVENTS,
    ARGO_WORKFLOW_TEMPLATES,
    ValidationContext,
    find_resource,
    resource_namespace,
)


def _safe_parse_embedded_manifest(raw_manifest: str) -> dict:
    """Safely parse embedded Argo YAML manifest template expressions (e.g. {{=toJson(...)}})."""
    sanitized = re.sub(r"\{\{.*?\}\}", "placeholder", raw_manifest, flags=re.DOTALL)
    return yaml.safe_load(sanitized) or {}


@pytest.mark.validate
def validate_argo_events_security(context: ValidationContext) -> None:
    """Verify Argo EventSource authentication tokens, endpoint whitelists, and payload limits."""
    errors: list[str] = []
    execution = context.render("k8s/argo")
    event_source = find_resource(execution, "EventSource", "webhook-eventsource")
    assert event_source, "k8s/argo must render EventSource webhook-eventsource"

    source_spec = event_source.get("spec") or {}
    if resource_namespace(event_source) != "argo-events":
        errors.append("webhook-eventsource must run in argo-events")
    if "service" in source_spec:
        errors.append("EventSource must not generate an unmanaged webhook Service")
    if ((source_spec.get("template") or {}).get("serviceAccountName")) != "argo-eventsource-sa":
        errors.append("EventSource must use the dedicated service account argo-eventsource-sa")

    webhooks = source_spec.get("webhook") or {}
    if set(webhooks) != ARGO_WEBHOOK_EVENTS:
        errors.append(f"webhook-eventsource endpoints must match {ARGO_WEBHOOK_EVENTS}, found {set(webhooks)}")

    for event in sorted(ARGO_WEBHOOK_EVENTS):
        webhook = webhooks.get(event) or {}
        if webhook.get("authSecret") != {
            "name": "argo-events-webhook-server",
            "key": "token",
        }:
            errors.append(f"Argo webhook {event} must use dedicated authSecret argo-events-webhook-server:token")
        expected_limit = 16384 if event == "reconcile" else 262144
        if webhook.get("maxPayloadSize") != expected_limit:
            errors.append(f"Argo webhook {event} must enforce {expected_limit} byte payload limit")

    assert not errors, "\n".join(errors)


@pytest.mark.validate
def validate_argo_event_bus(context: ValidationContext) -> None:
    """Verify Argo EventBus NATS native token authentication."""
    execution = context.render("k8s/argo")
    event_bus = find_resource(execution, "EventBus", "default")
    assert event_bus, "k8s/argo must render EventBus default"
    assert resource_namespace(event_bus) == "argo-events"
    auth = (((event_bus.get("spec") or {}).get("nats") or {}).get("native") or {}).get("auth")
    assert auth == "token", "Argo EventBus NATS must use native token auth"


@pytest.mark.validate
def validate_argo_workflows_inventory(context: ValidationContext) -> None:
    """Verify all 9 WorkflowTemplates and required ServiceAccounts exist in mlops-paas-execution."""
    execution = context.render("k8s/argo")
    templates = {
        (r.get("metadata") or {}).get("name"): r
        for r in execution
        if r.get("kind") == "WorkflowTemplate"
    }

    errors: list[str] = []
    for role, expected_name in ARGO_WORKFLOW_TEMPLATES.items():
        if expected_name not in templates:
            errors.append(f"Missing WorkflowTemplate '{expected_name}' for task '{role}'")
            continue
        tmpl = templates[expected_name]
        if resource_namespace(tmpl) != "mlops-paas-execution":
            errors.append(f"WorkflowTemplate '{expected_name}' must be in namespace 'mlops-paas-execution'")
        if tmpl.get("apiVersion") != "argoproj.io/v1alpha1":
            errors.append(f"WorkflowTemplate '{expected_name}' must use apiVersion 'argoproj.io/v1alpha1'")

    # Verify dedicated ServiceAccounts
    required_sas = {
        "argo-workflow-basic-sa",
        "argo-workflow-deploy-sa",
        "argo-workflow-delete-sa",
        "argo-workflow-training-sa",
        "argo-job-operations-sa",
    }
    sa_names = {
        (r.get("metadata") or {}).get("name")
        for r in execution
        if r.get("kind") == "ServiceAccount" and resource_namespace(r) == "mlops-paas-execution"
    }
    missing_sas = required_sas - sa_names
    if missing_sas:
        errors.append(f"Missing ServiceAccounts in mlops-paas-execution: {missing_sas}")

    assert not errors, "\n".join(errors)


@pytest.mark.validate
def validate_workflow_build_task(context: ValidationContext) -> None:
    """Verify Build task: Kaniko/Skopeo pipeline, 2Gi workspace PVC, Harbor secrets, onExit callback."""
    execution = context.render("k8s/argo")
    template = find_resource(execution, "WorkflowTemplate", "mlops-paas-model-packager-template")
    assert template, "WorkflowTemplate mlops-paas-model-packager-template must exist"

    spec = template.get("spec") or {}
    assert spec.get("serviceAccountName") == "argo-workflow-basic-sa"
    assert spec.get("entrypoint") == "build-model"
    assert spec.get("onExit") == "notify-build-exit"

    # VolumeClaimTemplates
    vc_templates = spec.get("volumeClaimTemplates") or []
    workspace_vc = next(
        (v for v in vc_templates if (v.get("metadata") or {}).get("name") == "workspace"),
        None,
    )
    assert workspace_vc, "Build workflow must declare volumeClaimTemplate 'workspace'"
    vc_spec = workspace_vc.get("spec") or {}
    assert vc_spec.get("accessModes") == ["ReadWriteOnce"]
    storage_req = ((vc_spec.get("resources") or {}).get("requests") or {}).get("storage")
    assert storage_req == "2Gi", f"Workspace storage request must be 2Gi, got {storage_req}"

    # Volumes check
    volumes = {v.get("name"): v for v in spec.get("volumes") or []}
    assert "harbor-config" in volumes, "Build workflow must mount harbor-config secret"
    assert (
        volumes["harbor-config"].get("secret", {}).get("secretName")
        == "harbor-registry-dockerconfig"
    )

    # Step templates: prepare -> build -> push -> notify
    step_templates = {t.get("name"): t for t in spec.get("templates") or []}
    main_step = step_templates.get("build-model")
    assert main_step, "Build workflow must have 'build-model' entrypoint template"
    step_names = [s[0].get("name") for s in main_step.get("steps") or [] if s]
    assert step_names == [
        "prepare-package",
        "build-image",
        "push-image",
        "notify-success",
    ], f"Build workflow step order mismatch: {step_names}"

    # Kaniko & Skopeo containers
    kaniko_img = ((step_templates.get("build-image") or {}).get("container") or {}).get("image", "")
    assert "gcr.io/kaniko-project/executor" in kaniko_img
    skopeo_img = ((step_templates.get("push-image") or {}).get("container") or {}).get("image", "")
    assert "quay.io/skopeo/stable" in skopeo_img

    # OnExit callback
    exit_step = step_templates.get("notify-build-exit")
    assert exit_step, "Build workflow must declare 'notify-build-exit' template"
    exit_env = {e.get("name"): e for e in (exit_step.get("container") or {}).get("env") or []}
    assert "CONTROL_PLANE_WEBHOOK_SECRET" in exit_env
    secret_ref = exit_env["CONTROL_PLANE_WEBHOOK_SECRET"].get("valueFrom", {}).get("secretKeyRef", {})
    assert secret_ref.get("name") == "argo-build-callback-secret"


@pytest.mark.validate
def validate_workflow_deploy_task(context: ValidationContext) -> None:
    """Verify Deploy task: target namespace mlops-paas-serving, probe security, automountToken=false, timeout."""
    execution = context.render("k8s/argo")

    # 1. Deploy Template
    deploy_tmpl = find_resource(execution, "WorkflowTemplate", "mlops-paas-model-server-deploy-template")
    assert deploy_tmpl, "WorkflowTemplate mlops-paas-model-server-deploy-template must exist"
    spec = deploy_tmpl.get("spec") or {}
    assert spec.get("serviceAccountName") == "argo-workflow-deploy-sa"
    assert spec.get("entrypoint") == "deploy-model"
    assert spec.get("activeDeadlineSeconds") == 1800
    assert spec.get("onExit") == "report-deployment-result"

    step_templates = {t.get("name"): t for t in spec.get("templates") or []}
    apply_dep = step_templates.get("apply-deployment")
    assert apply_dep, "Deploy workflow must define apply-deployment template"
    raw_manifest = (apply_dep.get("resource") or {}).get("manifest", "")
    dep_manifest = _safe_parse_embedded_manifest(raw_manifest)

    # Validate target namespace and Pod security
    assert dep_manifest.get("metadata", {}).get("namespace") == "mlops-paas-serving"
    pod_spec = (dep_manifest.get("spec", {}).get("template", {})).get("spec", {})
    assert pod_spec.get("automountServiceAccountToken") is False, (
        "Serving pod must not mount K8s ServiceAccount token"
    )
    assert pod_spec.get("nodeSelector", {}).get("workload-type") == "worker"
    container = pod_spec.get("containers", [{}])[0]
    assert container.get("resources", {}).get("limits", {}).get("memory") == "1Gi"
    assert "startupProbe" in container and "readinessProbe" in container

    # 2. Delete Template
    delete_tmpl = find_resource(execution, "WorkflowTemplate", "mlops-paas-model-server-delete-template")
    assert delete_tmpl, "WorkflowTemplate mlops-paas-model-server-delete-template must exist"
    del_spec = delete_tmpl.get("spec") or {}
    assert del_spec.get("serviceAccountName") == "argo-workflow-delete-sa"
    assert del_spec.get("entrypoint") == "delete-model-project"
    assert (del_spec.get("ttlStrategy") or {}).get("secondsAfterCompletion") == 300
    assert (del_spec.get("podGC") or {}).get("strategy") == "OnPodCompletion"


@pytest.mark.validate
def validate_workflow_evidently_task(context: ValidationContext) -> None:
    """Verify Evidently task: worker nodeSelector, multi-tenancy labels, envFrom secrets, resource caps."""
    execution = context.render("k8s/argo")
    template = find_resource(execution, "WorkflowTemplate", "mlops-paas-evidently-template")
    assert template, "WorkflowTemplate mlops-paas-evidently-template must exist"

    spec = template.get("spec") or {}
    assert spec.get("serviceAccountName") == "argo-workflow-basic-sa"
    assert spec.get("entrypoint") == "run-evidently"

    # Multi-tenancy labels
    pod_labels = (spec.get("podMetadata") or {}).get("labels") or {}
    assert "mlops-paas.io/drift-run-id" in pod_labels
    assert "mlops-paas.io/project-id" in pod_labels
    assert "mlops-paas.io/tenant-id" in pod_labels

    templates = {t.get("name"): t for t in spec.get("templates") or []}
    evidently_step = templates.get("run-evidently")
    assert evidently_step, "Evidently workflow must define 'run-evidently' template"
    assert (evidently_step.get("nodeSelector") or {}).get("workload-type") == "worker"

    container = evidently_step.get("container") or {}
    assert "mlops-paas-evidently" in container.get("image", "")

    # envFrom checks
    env_from = container.get("envFrom") or []
    secret_refs = [e.get("secretRef", {}).get("name") for e in env_from if "secretRef" in e]
    cm_refs = [e.get("configMapRef", {}).get("name") for e in env_from if "configMapRef" in e]
    assert "argo-evidently-secret" in secret_refs
    assert "mlops-paas-execution-config" in cm_refs

    # Resource caps
    resources = container.get("resources") or {}
    assert ((resources.get("limits") or {}).get("memory")) == "2Gi"


@pytest.mark.validate
def validate_workflow_training_task(context: ValidationContext) -> None:
    """Verify Training task: CPU/GPU conditional branching, Kubeflow PyTorchJob CRD, completion conditions."""
    execution = context.render("k8s/argo")
    template = find_resource(execution, "WorkflowTemplate", "mlops-paas-training-pipeline-template")
    assert template, "WorkflowTemplate mlops-paas-training-pipeline-template must exist"

    spec = template.get("spec") or {}
    assert spec.get("serviceAccountName") == "argo-workflow-training-sa"
    assert spec.get("entrypoint") == "training-pipeline"
    assert spec.get("onExit") == "report-status"

    templates = {t.get("name"): t for t in spec.get("templates") or []}
    pipeline = templates.get("training-pipeline")
    assert pipeline, "Training workflow must define 'training-pipeline' entrypoint"

    # Verify CPU vs GPU conditional steps
    steps = (pipeline.get("steps") or [[]])[0]
    cpu_step = next((s for s in steps if s.get("name") == "run-cpu-pytorch-job"), None)
    gpu_step = next((s for s in steps if s.get("name") == "run-gpu-pytorch-job"), None)
    assert cpu_step, "Training pipeline must include 'run-cpu-pytorch-job' step"
    assert gpu_step, "Training pipeline must include 'run-gpu-pytorch-job' step"
    assert "!= 'gpu'" in cpu_step.get("when", "")
    assert "== 'gpu'" in gpu_step.get("when", "")

    # Verify PyTorchJob CRD manifest
    cpu_job_tmpl = templates.get("cpu-pytorch-job")
    assert cpu_job_tmpl, "Training workflow must define 'cpu-pytorch-job' template"
    cpu_res = cpu_job_tmpl.get("resource") or {}
    assert cpu_res.get("action") == "create"
    assert cpu_res.get("successCondition") == "status.replicaStatuses.Master.succeeded == 1"
    assert cpu_res.get("failureCondition") == "status.replicaStatuses.Master.failed > 0"

    raw_manifest = cpu_res.get("manifest", "")
    job_manifest = _safe_parse_embedded_manifest(raw_manifest)
    assert job_manifest.get("apiVersion") == "kubeflow.org/v1"
    assert job_manifest.get("kind") == "PyTorchJob"
    assert job_manifest.get("metadata", {}).get("namespace") == "mlops-paas-training"
    assert job_manifest.get("spec", {}).get("runPolicy", {}).get("cleanPodPolicy") == "Running"

    # Verify cancel template
    cancel_tmpl = find_resource(execution, "WorkflowTemplate", "mlops-paas-training-cancel-template")
    assert cancel_tmpl, "WorkflowTemplate mlops-paas-training-cancel-template must exist"
    assert cancel_tmpl.get("spec", {}).get("serviceAccountName") == "argo-workflow-training-sa"


@pytest.mark.validate
def validate_workflow_operations_task(context: ValidationContext) -> None:
    """Verify Operations tasks: retry backoff, activeDeadline, TTL tombstone, job_ops.py contract."""
    execution = context.render("k8s/argo")

    # 1. Submit template
    submit_tmpl = find_resource(execution, "WorkflowTemplate", "mlops-paas-job-submit-template")
    assert submit_tmpl, "WorkflowTemplate mlops-paas-job-submit-template must exist"
    sub_spec = submit_tmpl.get("spec") or {}
    assert sub_spec.get("serviceAccountName") == "argo-job-operations-sa"
    assert sub_spec.get("activeDeadlineSeconds") == 240
    assert (sub_spec.get("ttlStrategy") or {}).get("secondsAfterCompletion") == 300
    assert (sub_spec.get("podGC") or {}).get("strategy") == "OnPodCompletion"

    sub_step = (sub_spec.get("templates") or [{}])[0]
    retry = sub_step.get("retryStrategy") or {}
    assert retry.get("limit") == "3"
    assert retry.get("backoff", {}).get("duration") == "2s"
    assert retry.get("backoff", {}).get("maxDuration") == "30s"
    cmd = (sub_step.get("container") or {}).get("command") or []
    assert cmd == ["python", "/ops/job_ops.py", "submit"]

    # 2. Reconcile template
    rec_tmpl = find_resource(execution, "WorkflowTemplate", "mlops-paas-job-reconcile-template")
    assert rec_tmpl, "WorkflowTemplate mlops-paas-job-reconcile-template must exist"
    rec_step = (rec_tmpl.get("spec", {}).get("templates") or [{}])[0]
    rec_cmd = (rec_step.get("container") or {}).get("command") or []
    assert rec_cmd == ["python", "/ops/job_ops.py", "reconcile"]

    # 3. Tombstone template
    tombstone_tmpl = find_resource(execution, "WorkflowTemplate", "mlops-paas-job-tombstone-template")
    assert tombstone_tmpl, "WorkflowTemplate mlops-paas-job-tombstone-template must exist"
    tomb_spec = tombstone_tmpl.get("spec") or {}
    assert tomb_spec.get("serviceAccountName") == "argo-workflow-basic-sa"
    assert (tomb_spec.get("ttlStrategy") or {}).get("secondsAfterCompletion") == 300
    assert (tomb_spec.get("podGC") or {}).get("strategy") == "OnPodCompletion"
    tomb_step = (tomb_spec.get("templates") or [{}])[0]
    assert (tomb_step.get("container") or {}).get("command") == ["true"]

    # 4. Script validation in job_ops.py
    script_path = (
        context.source_root
        / "k8s"
        / "argo"
        / "workflows"
        / "operations"
        / "scripts"
        / "job_ops.py"
    )
    assert script_path.exists(), "job_ops.py script must exist"
    content = script_path.read_text(encoding="utf-8")
    assert 'UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"' in content
    assert '"T-" + UUID' in content
    assert "TOMBSTONE_TTL_SECONDS = 7 * 24 * 3600" in content


@pytest.mark.validate
def validate_workflow_rbac_isolation(context: ValidationContext) -> None:
    """Verify least-privilege scoping across execution, serving, and training planes."""
    execution = context.render("k8s/argo")

    roles = [r for r in execution if r.get("kind") == "Role"]
    errors: list[str] = []

    # Ensure no role grants wildcard '*' verbs or resources
    for role in roles:
        role_name = (role.get("metadata") or {}).get("name", "")
        role_ns = resource_namespace(role)
        for rule in (role.get("rules") or []):
            verbs = rule.get("verbs", [])
            resources = rule.get("resources", [])
            if "*" in verbs and "*" in resources:
                errors.append(f"Role '{role_name}' in '{role_ns}' must not grant wildcard '*' on '*'")

    # Specific RBAC constraints:
    # 1. argo-workflow-deploy in mlops-paas-serving: apps + core services only
    deploy_role = find_resource(roles, "Role", "argo-workflow-deploy")
    assert deploy_role, "Role argo-workflow-deploy must exist"
    assert resource_namespace(deploy_role) == "mlops-paas-serving"
    deploy_groups = {g for rule in deploy_role.get("rules", []) for g in rule.get("apiGroups", [])}
    assert deploy_groups.issubset({"", "apps"}), f"Deploy role exceeded scope: {deploy_groups}"

    # 2. argo-training-job-role in mlops-paas-training: kubeflow.org + core pods/logs/events only
    training_role = find_resource(roles, "Role", "argo-training-job-role")
    assert training_role, "Role argo-training-job-role must exist"
    assert resource_namespace(training_role) == "mlops-paas-training"
    training_groups = {g for rule in training_role.get("rules", []) for g in rule.get("apiGroups", [])}
    assert training_groups.issubset({"", "kubeflow.org"}), f"Training role exceeded scope: {training_groups}"

    # 3. argo-job-operations in mlops-paas-execution
    ops_role = find_resource(roles, "Role", "argo-job-operations")
    assert ops_role, "Role argo-job-operations must exist"
    assert resource_namespace(ops_role) == "mlops-paas-execution"

    assert not errors, "\n".join(errors)


@pytest.mark.validate
def validate_workflow_network_policies(context: ValidationContext) -> None:
    """Verify network policies enforce domain isolation and deny AWS IMDS metadata access."""
    execution = context.render("k8s/argo")
    netpols = {
        ((r.get("metadata") or {}).get("namespace"), (r.get("metadata") or {}).get("name")): r
        for r in execution
        if r.get("kind") == "NetworkPolicy"
    }

    required_policies = {
        ("mlops-paas-execution", "np-mlops-paas-model-packager"),
        ("mlops-paas-serving", "np-mlops-paas-serving"),
        ("mlops-paas-execution", "np-mlops-paas-evidently"),
        ("mlops-paas-training", "np-mlops-paas-training"),
        ("mlops-paas-execution", "np-mlops-paas-job-operations"),
        ("mlops-paas-execution", "default-deny-all-ingress-execution"),
    }
    missing = required_policies - set(netpols)
    assert not missing, f"Missing workflow NetworkPolicies: {missing}"

    # Verify IMDS metadata is denied in packaging policy
    packager_policy = netpols[("mlops-paas-execution", "np-mlops-paas-model-packager")]
    egress_rules = (packager_policy.get("spec") or {}).get("egress") or []
    has_imds_block = False
    for rule in egress_rules:
        for to_target in rule.get("to") or []:
            ip_block = to_target.get("ipBlock") or {}
            if "169.254.169.254/32" in ip_block.get("except", []):
                has_imds_block = True
    assert has_imds_block, "Packager NetworkPolicy must explicitly block AWS IMDS (169.254.169.254/32)"
