"""Validate the Argo Events execution-plane authentication and least privilege contract."""

from __future__ import annotations

import json
import yaml

from .common import ARGO_WEBHOOK_EVENTS, ValidationContext, find_resource, resource_namespace, run_standalone


def validate(context: ValidationContext) -> list[str]:
    errors: list[str] = []
    execution = context.render("k8s/argo")
    control_plane = context.render("k8s/apps/overlays/production/control-plane")
    event_source = find_resource(execution, "EventSource", "webhook-eventsource")
    source_spec = event_source.get("spec") or {}
    if resource_namespace(event_source) != "argo-events":
        errors.append("webhook-eventsource must run in argo-events")
    if "service" in source_spec:
        errors.append("EventSource must not generate an unmanaged webhook Service")
    if ((source_spec.get("template") or {}).get("serviceAccountName")) != "argo-eventsource-sa":
        errors.append("EventSource must use the non-privileged dedicated service account")
    webhooks = source_spec.get("webhook") or {}
    if set(webhooks) != ARGO_WEBHOOK_EVENTS:
        errors.append("webhook-eventsource must define exactly the six trusted execution endpoints")
    for event in sorted(ARGO_WEBHOOK_EVENTS):
        webhook = webhooks.get(event) or {}
        if webhook.get("authSecret") != {"name": "argo-events-webhook-server", "key": "token"}:
            errors.append(f"Argo webhook {event} must use the dedicated bearer-token Secret")
        if webhook.get("maxPayloadSize") != 262144:
            errors.append(f"Argo webhook {event} must enforce the 256 KiB payload limit")
    event_bus = find_resource(execution, "EventBus", "default")
    if resource_namespace(event_bus) != "argo-events":
        errors.append("Argo EventBus must run in argo-events")
    if ((((event_bus.get("spec") or {}).get("nats") or {}).get("native") or {}).get("auth")) != "token":
        errors.append("Argo EventBus native NATS authentication must be token")
    rendered_text = json.dumps(execution, sort_keys=True)
    if "argo-workflow-sa" in rendered_text or "argo-events-sa" in rendered_text:
        errors.append("legacy shared Argo service accounts must not be rendered")
    if "body.namespace" in rendered_text:
        errors.append("training namespace must be fixed in Git, not accepted from an event payload")
    forbidden = {"secrets", "pods/exec", "configmaps", "ingressroutes"}
    for role in (resource for resource in execution if resource.get("kind") == "Role"):
        for rule in role.get("rules") or []:
            if set(rule.get("resources") or []) & forbidden:
                errors.append(f"Role {(role.get('metadata') or {}).get('name')} grants forbidden execution access")
    sensor = find_resource(execution, "Sensor", "model-sensor")
    if resource_namespace(sensor) != "argo-events":
        errors.append("model-sensor must run in argo-events")
    sensor_template = ((sensor.get("spec") or {}).get("template") or {})
    if sensor_template.get("serviceAccountName") != "argo-sensor-sa":
        errors.append("model-sensor must use the dedicated sensor service account")
    for trigger in (sensor.get("spec") or {}).get("triggers") or []:
        workflow = (((((trigger.get("template") or {}).get("k8s") or {}).get("source") or {}).get("resource")) or {})
        workflow_spec = workflow.get("spec") or {}
        if resource_namespace(workflow) != "mlops-execution":
            errors.append("Sensor triggers must create Workflows in mlops-execution")
        if not workflow_spec.get("workflowTemplateRef"):
            errors.append("every Sensor trigger must reference a Git-managed WorkflowTemplate")
        if workflow_spec.get("serviceAccountName"):
            errors.append("Sensor trigger must not override a WorkflowTemplate service account")
    policies = {(resource.get("metadata") or {}).get("name") for resource in execution if resource.get("kind") == "NetworkPolicy"}
    required_policies = {"allow-control-plane-worker-to-argo-events-webhook", "isolate-argo-events-eventbus"}
    if not required_policies <= policies:
        errors.append("execution Application must render EventSource and EventBus NetworkPolicies")
    webhook_policy = find_resource(execution, "NetworkPolicy", "allow-control-plane-worker-to-argo-events-webhook")
    if ((webhook_policy.get("spec") or {}).get("ingress") or []) != [{
        "from": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "mlops-control-plane"}}, "podSelector": {"matchLabels": {"app": "mlops-paas-control-plane-worker"}}}],
        "ports": [{"protocol": "TCP", "port": 12000}],
    }]:
        errors.append("EventSource NetworkPolicy must allow only the mlops-control-plane worker on TCP 12000")
    targets = {
        (resource_namespace(resource), ((resource.get("spec") or {}).get("target") or {}).get("name"))
        for resource in execution if resource.get("kind") == "ExternalSecret"
    }
    if ("argo-events", "argo-events-webhook-server") not in targets:
        errors.append("Argo Events server bearer-token Secret must be synchronized by External Secrets")
    for deployment_name, expected_secret in {"mlops-paas-control-plane": "control-plane-api-secret", "mlops-paas-control-plane-worker": "control-plane-worker-secret"}.items():
        deployment = find_resource(control_plane, "Deployment", deployment_name)
        pod_spec = (((deployment.get("spec") or {}).get("template") or {}).get("spec") or {})
        if pod_spec.get("automountServiceAccountToken") is not False or pod_spec.get("serviceAccountName"):
            errors.append(f"{deployment_name} must not receive Kubernetes API credentials")
        token_env = [
            env for container in [*(pod_spec.get("initContainers") or []), *(pod_spec.get("containers") or [])]
            for env in container.get("env") or [] if env.get("name") == "ARGO_EVENTS_WEBHOOK_TOKEN"
        ]
        if not token_env or any((((env.get("valueFrom") or {}).get("secretKeyRef") or {}).get("name")) != expected_secret for env in token_env):
            errors.append(f"{deployment_name} must source the Argo bearer token from {expected_secret}")
    workflow_addon = context.application("mlops-prod-addon-argo-workflows")
    values = (((workflow_addon.get("spec") or {}).get("source") or {}).get("helm") or {}).get("values", "")
    restrictions = ((yaml.safe_load(values) or {}).get("controller") or {}).get("workflowRestrictions")
    if restrictions != {"templateReferencing": "Secure"}:
        errors.append("Argo Workflows must enforce Secure WorkflowTemplate referencing")
    workflow_namespaces = {
        resource_namespace(resource)
        for resource in execution
        if resource.get("kind") == "WorkflowTemplate"
    }
    if workflow_namespaces != {"mlops-execution"}:
        errors.append("all Git-managed WorkflowTemplates must run in mlops-execution")
    workflow_namespaces = ((yaml.safe_load(values) or {}).get("controller") or {}).get("workflowNamespaces")
    if workflow_namespaces != ["mlops-execution", "argo"]:
        errors.append("Argo Workflows must watch only mlops-execution and argo")
    return errors


if __name__ == "__main__":  # pragma: no cover - CLI boundary
    raise SystemExit(run_standalone("execution-security", validate))
