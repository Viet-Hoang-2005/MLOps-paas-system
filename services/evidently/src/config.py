"""Runtime configuration validation for a drift-analysis job."""


def validate(threshold: float, tenant_id: str | None, project_id: str | None,
             model_version_id: str | None) -> None:
    if not 0 <= threshold <= 1:
        raise ValueError("DRIFT_THRESHOLD must be between 0 and 1.")
    if not tenant_id or not project_id or not model_version_id:
        raise ValueError("TENANT_ID, PROJECT_ID and MODEL_VERSION_ID must be set.")
