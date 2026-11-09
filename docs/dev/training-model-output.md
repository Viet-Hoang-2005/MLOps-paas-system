# Training model output

Workspace runs do not require a Model Project or a platform SDK. The workspace
has its own URL and editable draft; each Run saves the draft, checks its revision,
and creates a separate immutable input archive and Training Job. While a job is
active, workspace changes are rejected on both the frontend and backend.

## Workspace runtime contract

| Environment variable | Contract |
| --- | --- |
| `SM_CHANNEL_TRAIN` | Unified Input root, mounted read-only by Docker/Kubernetes |
| `SM_MODEL_DIR` | Writable directory for the official model artifact |
| `SM_OUTPUT_DIR` | Writable directory for supported metrics and metadata |
| `MLOPS_WORK_DIR` | Writable temporary workspace and Python working directory |

Resolve input paths relative to `SM_CHANNEL_TRAIN`; write intermediate files in
`MLOPS_WORK_DIR`. Only model output and supported metadata are collected. Files
left in Work are not automatically published.

```python
import json
import os
from pathlib import Path

input_root = Path(os.environ["SM_CHANNEL_TRAIN"])
work = Path(os.environ["MLOPS_WORK_DIR"])
model_dir = Path(os.environ["SM_MODEL_DIR"])
# data = pandas.read_csv(input_root / "data" / "train.csv")
# model.fit(data)
# joblib.dump(model, model_dir / "model.joblib")
Path(os.environ["SM_OUTPUT_DIR"], "metrics.json").write_text(
    json.dumps({"accuracy": 0.95}), encoding="utf-8"
)
```

`requirements.txt` is optional and fixed at the Input root. Edit its text in the
editor; replacement upload requires deleting the existing file first.
Environment and Secrets are managed separately. Secret reads return names and
metadata only. The backend needs `TRAINING_SECRET_ENCRYPTION_KEY` configured
with a Fernet key to accept secrets; there is no default key. Runtime configuration
is delivered using a job-scoped, expiring, one-use capability. Known values are
masked in captured logs, but code given a secret can still intentionally expose it.

## Project assignment and retention

After successful execution and verified model upload, Continue opens Project
assignment. Save links a new or existing Project and saves supplemental artifacts
at the checked output revision. It does not change Model Preview or start a build.
A job can be assigned repeatedly to the same Project, but cannot be moved to
another Project in this version. Build Model selects Preview or an assigned,
successful Training Job explicitly.

Deleting a Project first stops its active training jobs. Legacy training objects
are copied to the independent tenant/job namespace and checksum-verified with
resumable checkpoints before Project cleanup. Jobs, outputs, logs, and quota
records survive deletion. Deleting a workspace also leaves its run snapshots intact.

## APIs and rollout

- `/api/training-workspaces/`: drafts, revision-checked file/folder operations,
  Environment and Secrets.
- `/api/training-workspaces/{id}/runs/`: GET history, POST snapshot and submit.
- `/api/training-jobs/{id}/input/`: immutable input listing/content/download.
- `/api/training-jobs/{id}/project/`: assign with `output_revision` and either
  `project_id` or `new_project`.
- Existing job logs, runtime/experiment metrics, cancellation, artifact editing,
  downloads, and builds keep their separate endpoints.

Apply additive training migrations through `0016`, then update Control Plane,
workers, and the runner image together. Production Workflow init and training
containers must use the same promoted runner image. Render/validate manifests
before GitOps rollout; no AWS or Kubernetes deployment is performed by this change.

The disposable local integration check is
`services/control-plane/scripts/verify_training_workspace.py`. Run it inside the
ready Control Plane container after building `training-runner`. It exercises actual
Docker read-only mounts, S3 upload, assignment, legacy storage migration, Project
deletion, and cleanup. It creates its own test tenant and deletes only its own data.

## Model validation

Write the trained model into the directory named by `SM_MODEL_DIR`. For example:

```python
import os
from pathlib import Path

model_dir = Path(os.environ["SM_MODEL_DIR"])
model_dir.mkdir(parents=True, exist_ok=True)
# Replace this with your framework's model-saving method.
# model.save(model_dir / "model.keras")
```

The runner packages the files in this directory only after the training process
exits successfully. At least one model file must exist outside the reserved
`_mlops` metadata directory. Symlinks, hard links, special files, and outputs
exceeding 100,000 files or 20 GiB are rejected. Successful packaging does not
guarantee that a model is compatible with the model build or serving runtime.

For existing jobs, `SM_CHANNEL_TRAIN` continues to point to the separate data
directory, and `SM_OUTPUT_DIR` remains the location used for runner metadata.
