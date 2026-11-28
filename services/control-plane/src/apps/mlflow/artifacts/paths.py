import re

from django.conf import settings
from rest_framework.exceptions import ValidationError


def _safe_relative(path):
    if "_mlops" in str(path).replace("\\", "/").split("/"):
        raise ValidationError("System artifacts are not publicly accessible.")
    if path and (
        "\\" in path or any(part in {"", ".", ".."} for part in path.split("/")) or any(ord(c) < 32 for c in path)
    ):
        raise ValidationError("Unsafe artifact path.")
    return path


def _bucket_name() -> str:
    return getattr(settings, "AWS_STORAGE_BUCKET_NAME", getattr(settings, "AWS_BUCKET_NAME", "mlops-paas-artifacts"))


def _combine_effective_path(subpath: str, query_path: str | None) -> str:
    subpath = (subpath or "").strip().strip("/")
    if not query_path:
        return subpath
    query_path = query_path.strip().strip("/")
    if not subpath:
        return query_path
    if query_path.startswith("users/"):
        return query_path
    return f"{subpath}/{query_path}"


def _parse_artifact_path(subpath: str):
    """
    Parses subpath into (tenant_id, project_id, job_id, rel_path).
    Supports:
    1. Job-scoped paths (with or without 'mlflow/'):
       - users/<tenant>/models/<project>/training/jobs/<job>/mlflow/artifacts(/<rel_path>)?
       - users/<tenant>/models/<project>/training/jobs/<job>/artifacts(/<rel_path>)?
       - users/<tenant>/models/<project>/training/jobs/<job>(/<rel_path>)?
    2. Experiment-scoped paths:
       - users/<tenant>/models/<project>/training/jobs
       - users/<tenant>/models/<project>
    """
    clean = (subpath or "").strip().strip("/")
    tenant_job = re.fullmatch(r"users/([^/]+)/training/jobs/([^/]+)(?:/(?:mlflow/)?artifacts)?(?:/(.*))?", clean)
    if tenant_job:
        return tenant_job.group(1), None, tenant_job.group(2), _safe_relative(tenant_job.group(3) or "")

    # 1. Job-scoped path
    m_job = re.match(
        r"^users/([^/]+)/models/([^/]+)/training/jobs/([^/]+)(?:/(?:mlflow/)?artifacts)?(?:/(.*))?$",
        clean,
    )
    if m_job:
        tenant, project, job, rel = m_job.group(1), m_job.group(2), m_job.group(3), m_job.group(4)
        return tenant, project, job, _safe_relative(rel or "")

    # 2. Experiment-scoped path
    m_exp = re.match(
        r"^users/([^/]+)/models/([^/]+)(?:/training/jobs)?$",
        clean,
    )
    if m_exp:
        return m_exp.group(1), m_exp.group(2), None, ""

    return None, None, None, clean
