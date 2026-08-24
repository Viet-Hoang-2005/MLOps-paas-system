"""Run all Kubernetes GitOps validators against one isolated render context."""

from __future__ import annotations

from .common import RenderError, prepared_context
from .validate_application_contract import validate as validate_application_contract
from .validate_cluster_capacity import validate as validate_cluster_capacity
from .validate_execution_security import validate as validate_execution_security
from .validate_helm_sources import validate as validate_helm_sources
from .validate_resource_ownership import validate as validate_resource_ownership
from .validate_secrets import validate as validate_secrets
from .validate_supply_chain import validate as validate_supply_chain


VALIDATORS = (
    ("application-contract", validate_application_contract),
    ("resource-ownership", validate_resource_ownership),
    ("secrets", validate_secrets),
    ("execution-security", validate_execution_security),
    ("supply-chain", validate_supply_chain),
    ("cluster-capacity", validate_cluster_capacity),
    ("helm-sources", validate_helm_sources),
)


def main() -> int:
    all_errors: list[tuple[str, str]] = []
    try:
        with prepared_context() as context:
            for name, validator in VALIDATORS:
                print(f"::group::{name}")
                try:
                    errors = validator(context)
                except Exception as error:  # keep independent checks observable in CI
                    errors = [str(error)]
                if errors:
                    for error in errors:
                        print(f"ERROR [{name}]: {error}")
                        all_errors.append((name, error))
                else:
                    print(f"PASS [{name}]")
                print("::endgroup::")
    except RenderError as error:
        print(f"ERROR [bootstrap]: {error}")
        return 1
    if all_errors:
        print(f"GitOps validation failed with {len(all_errors)} error(s).")
        return 1
    print(f"GitOps validation passed: {len(VALIDATORS)} validator groups.")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI boundary
    raise SystemExit(main())
