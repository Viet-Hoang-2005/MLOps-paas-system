"""Validate Execution Plane resources: Argo Events, Argo Workflows, RBAC, and webhook security."""

from __future__ import annotations

import pytest

from ..utils import (
    ARGO_WEBHOOK_EVENTS,
    ValidationContext,
    find_resource,
    resource_namespace,
)


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

