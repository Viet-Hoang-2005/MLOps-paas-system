"""Control Plane callback delivery for drift results."""


def trigger_webhook(*, requests_module, retry_factory, adapter_factory, webhook_url,
                    webhook_secret, tenant_id, project_id, model_version_id,
                    drift_summary, threshold, detail, on_error):
    detail("Triggering Django Webhook...")
    session = requests_module.Session()
    retry_strategy = retry_factory(
        total=3, backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["POST"],
    )
    adapter = adapter_factory(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    payload = {
        "tenant_id": tenant_id,
        "project_id": project_id,
        "model_version_id": model_version_id,
        "drift_summary": drift_summary,
        "threshold": threshold,
    }
    try:
        response = session.post(
            webhook_url,
            headers={"Authorization": f"Bearer {webhook_secret}", "Content-Type": "application/json"},
            json=payload,
            timeout=15,
        )
        if response.status_code in [200, 201, 204]:
            detail("Webhook sent successfully to Django Control Plane.")
        else:
            on_error("Drift callback failed", status_code=response.status_code)
    except Exception as exc:
        on_error("Failed to send drift callback", reason=str(exc))
