"""Validate scoped task collection and readiness-based deployment reporting."""

from __future__ import annotations

import yaml

from .common import ValidationContext, find_resource, run_standalone


def validate(context: ValidationContext) -> list[str]:
    errors = []
    alloy = context.application("mlops-prod-addon-alloy")
    values = yaml.safe_load(alloy["spec"]["source"]["helm"]["values"])
    rbac = values.get("rbac", {})
    if set(rbac.get("namespaces", [])) != {"mlops-execution", "mlops-model-runtimes", "user-jobs"}:
        errors.append("Alloy must collect only task namespaces")
    if rbac.get("clusterRules") != []:
        errors.append("Alloy must not grant cluster-wide discovery rights")
    for rule in rbac.get("rules", []):
        if set(rule.get("resources", [])) - {"pods", "pods/log"} or set(rule.get("verbs", [])) - {"get", "list", "watch"}:
            errors.append("Alloy RBAC must be read-only Pod/log access")
    content = values.get("alloy", {}).get("configMap", {}).get("content", "")
    for contract in ("stage.structured_metadata", "stage.pack", 'action = "keep"'):
        if contract not in content:
            errors.append(f"Missing task correlation contract: {contract}")
    loki = context.application("mlops-prod-addon-loki")
    values = yaml.safe_load(loki["spec"]["source"]["helm"]["values"])
    if values.get("loki", {}).get("limits_config", {}).get("retention_period") != "168h":
        errors.append("Loki must retain task logs for seven days")
    if values.get("networkPolicy", {}).get("enabled") is not True:
        errors.append("Internal Loki must have a NetworkPolicy")
    execution = context.render("k8s/argo")
    role = find_resource(execution, "Role", "argo-workflow-deploy")
    deployment_verbs = {
        verb
        for rule in role.get("rules", [])
        if "deployments" in rule.get("resources", [])
        for verb in rule.get("verbs", [])
    }
    if not {"get", "list", "watch"} <= deployment_verbs:
        errors.append("Deploy rollout status requires get/list/watch on Deployments")
    template = find_resource(execution, "WorkflowTemplate", "mlops-paas-model-server-deploy-template")
    spec = template.get("spec", {})
    if spec.get("onExit") != "report-deployment-result" or spec.get("activeDeadlineSeconds") != 1800:
        errors.append("Deploy Workflow must have a bounded trusted result reporter")
    templates = {item["name"]: item for item in spec.get("templates", [])}
    manifest = templates.get("apply-deployment", {}).get("resource", {}).get("manifest", "")
    if "model_loaded" not in manifest or "readinessProbe:" not in manifest or "startupProbe:" not in manifest:
        errors.append("Deploy must verify actual model readiness")
    if "callback_token" in manifest:
        errors.append("Tenant runtime must never receive reporter credentials")
    for name in ("await-model-ready", "report-deployment-result"):
        if name not in templates:
            errors.append(f"Missing trusted deploy step {name}")
    return errors


if __name__ == "__main__":
    raise SystemExit(run_standalone("runtime-logging", validate))
