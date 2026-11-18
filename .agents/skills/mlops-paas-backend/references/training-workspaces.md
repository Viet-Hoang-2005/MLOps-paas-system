# Training workspaces and runs

Use the [workspace lifecycle](../../../../docs/dev/training-workspaces.md) for API, route, snapshot and deletion details, and the [model output contract](../../../../docs/dev/training-model-output.md) for Output publication, access and assignment.

| Change or symptom | Start under `services/control-plane/src/apps/training/` |
| --- | --- |
| Draft edits, Run response or history | `api/workspace_urls.py`, `api/workspace_views.py`, `services/drafts.py` |
| Pending, timeout, duplicate delivery or preparation recovery | `services/preparation.py`, `tasks.py`, `tests/test_async_preparation.py` |
| Runtime adoption, stop or cleanup | `services/jobs.py`, `services/workspace_lifecycle.py` and the selected adapter under `src/infrastructure/execution/` |
| One-use runtime configuration delivery | `services/workspace_runs.py` and `services/capabilities.py` |
| Output verification and index | `services/output_finalization.py`, `services/output_index.py`, `services/storage_scope.py` |
| Assignment and Build inputs | `services/project_assignment.py`, `services/artifact_selection.py`, `tests/test_project_assignment.py`, `tests/test_build_registration.py` |
| Input or Output download | `services/downloads.py`, `tests/test_workspace_downloads.py` |

The Workspace owns mutable Input, config and Secrets; each Run creates a new immutable job. For a Pending job with no `submitted_at`, trace publication, preparation lease, and admission before investigating Docker/Argo. Preserve the revision/run key replay behavior, stale-token fencing and resource reservation at admission. A preparation failure retains the draft and history entry. Job deletion leaves workspace drafts intact.

Output completion requires verification and atomic indexing. The runner sends a temporary `model.tar.gz`; a post-commit cleanup task removes that scoped transport object. Public reads use indexed Model/Metadata, while indexed `_mlops` stays private. Artifact assignment and the Build snapshot use explicit saved selections and `output_revision`.

Test the changed stage and its adjacent failure/replay path. Use a real PostgreSQL test when verifying lock or ordering semantics. Treat prior development reset procedures in the lifecycle docs as historical rollout details for those changes.
