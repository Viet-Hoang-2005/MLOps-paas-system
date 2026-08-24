"""Validate the Kyverno/Cosign admission and CD signing contract together."""

from __future__ import annotations

import re

from .common import (
    KEYLESS_SIGNER_IDENTITY,
    KEYLESS_SIGNER_ISSUER,
    PLATFORM_IMAGE_PATTERN,
    ValidationContext,
    find_resource,
    resource_namespace,
    run_standalone,
)


def job_block(workflow: str, name: str) -> str:
    match = re.search(rf"^  {re.escape(name)}:\n(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)", workflow, re.MULTILINE | re.DOTALL)
    return match.group(0) if match else ""


def validate_policy(context: ValidationContext) -> tuple[list[str], dict]:
    errors: list[str] = []
    kyverno = context.application("mlops-prod-addon-kyverno")
    source = ((kyverno.get("spec") or {}).get("source") or {})
    if source.get("repoURL") != "https://kyverno.github.io/kyverno" or source.get("chart") != "kyverno" or source.get("targetRevision") != "3.8.2":
        errors.append("mlops-prod-addon-kyverno must pin the official Kyverno chart at 3.8.2")
    if (((kyverno.get("spec") or {}).get("destination") or {}).get("namespace")) != "kyverno":
        errors.append("mlops-prod-addon-kyverno must install into kyverno")
    verification_app = context.application("mlops-prod-cluster-image-verification")
    if ((((verification_app.get("spec") or {}).get("source") or {}).get("path"))) != "k8s/cluster/policies/image-verification":
        errors.append("image-verification must use the Git-backed policy source")
    if (((verification_app.get("spec") or {}).get("destination") or {}).get("namespace")) != "kyverno":
        errors.append("image-verification must reconcile in kyverno")
    resources = context.render("k8s/cluster/policies/image-verification")
    credentials = find_resource(resources, "ExternalSecret", "kyverno-harbor-registry-auth-sync")
    credentials_spec = credentials.get("spec") or {}
    target = credentials_spec.get("target") or {}
    if resource_namespace(credentials) != "kyverno" or target.get("name") != "kyverno-harbor-registry-auth":
        errors.append("Kyverno registry credential must be scoped to kyverno/kyverno-harbor-registry-auth")
    if (target.get("template") or {}).get("type") != "kubernetes.io/dockerconfigjson":
        errors.append("Kyverno registry credential must be a dockerconfigjson Secret")
    if credentials_spec.get("secretStoreRef") != {"kind": "ClusterSecretStore", "name": "aws-secrets-manager"}:
        errors.append("Kyverno registry credential must use aws-secrets-manager")
    policy = find_resource(resources, "ClusterPolicy", "verify-platform-images")
    spec = policy.get("spec") or {}
    if spec.get("background") is not False or spec.get("failurePolicy") != "Fail" or spec.get("validationFailureAction") != "Enforce":
        errors.append("image verification must be fail-closed and enforced")
    if spec.get("webhookTimeoutSeconds") != 30:
        errors.append("image verification must use a bounded 30-second registry timeout")
    verify_images = (((spec.get("rules") or [{}])[0].get("verifyImages")) or [])
    if len(verify_images) != 1:
        errors.append("image verification policy must contain exactly one verifyImages rule")
        return errors, {}
    verification = verify_images[0]
    if verification.get("imageReferences") != [PLATFORM_IMAGE_PATTERN]:
        errors.append("image verification must cover only platform images")
    for field in ("required", "mutateDigest", "verifyDigest"):
        if verification.get(field) is not True:
            errors.append(f"image verification must set {field}=true")
    if (verification.get("imageRegistryCredentials") or {}).get("secrets") != ["kyverno-harbor-registry-auth"]:
        errors.append("image verification must authenticate to Harbor with its scoped credential")
    entries = (((verification.get("attestors") or [{}])[0].get("entries")) or [])
    keyless = (((entries[0] if entries else {}).get("keyless")) or {})
    if keyless.get("subject") != KEYLESS_SIGNER_IDENTITY:
        errors.append("image verification must require the exact CD keyless identity")
    if keyless.get("issuer") != KEYLESS_SIGNER_ISSUER:
        errors.append("image verification must require the GitHub Actions OIDC issuer")
    if keyless.get("rekor", {}).get("url") != "https://rekor.sigstore.dev":
        errors.append("image verification must verify the Rekor transparency-log entry")
    return errors, keyless


def validate_cd_workflow(context: ValidationContext, keyless: dict) -> list[str]:
    errors: list[str] = []
    workflow = (context.source_root / ".github/workflows/cd.yml").read_text(encoding="utf-8")
    build = job_block(workflow, "build-and-push")
    promotion = job_block(workflow, "gitops-promotion")
    if not build:
        return ["cd.yml must define the build-and-push job"]
    if not re.search(r"^    permissions:\n(?:.*\n)*?      id-token: write$", build, re.MULTILINE):
        errors.append("build-and-push must grant id-token: write for keyless Cosign signing")
    if "aws-actions/configure-aws-credentials@" not in build:
        errors.append("build-and-push must acquire AWS credentials before Harbor push")
    if "cosign sign --yes \"${IMAGE_REFERENCE}\"" not in build or "${IMAGE}@${DIGEST}" not in build:
        errors.append("build-and-push must keylessly sign the immutable image digest")
    subject = keyless.get("subject") or KEYLESS_SIGNER_IDENTITY
    issuer = keyless.get("issuer") or KEYLESS_SIGNER_ISSUER
    if f'--certificate-identity="{subject}"' not in build:
        errors.append("CD Cosign verification identity must match the Kyverno policy")
    if f'--certificate-oidc-issuer="{issuer}"' not in build:
        errors.append("CD Cosign verification issuer must match the Kyverno policy")
    if not promotion:
        errors.append("cd.yml must define the gitops-promotion job")
    else:
        if "id-token: write" in promotion or "aws-actions/configure-aws-credentials@" in promotion:
            errors.append("gitops-promotion must not receive AWS OIDC credentials")
        if "secretsmanager" in promotion.lower() or "Fetch Secrets from AWS" in promotion:
            errors.append("gitops-promotion must not fetch AWS Secrets Manager values")
    for name in re.findall(r"^  ([A-Za-z0-9_-]+):\n", workflow, re.MULTILINE):
        if name not in {"build-and-push"} and "id-token: write" in job_block(workflow, name):
            errors.append(f"only build-and-push may receive id-token: write, found it in {name}")
    return errors


def validate(context: ValidationContext) -> list[str]:
    policy_errors, keyless = validate_policy(context)
    return [*policy_errors, *validate_cd_workflow(context, keyless)]


if __name__ == "__main__":  # pragma: no cover - CLI boundary
    raise SystemExit(run_standalone("supply-chain", validate))
