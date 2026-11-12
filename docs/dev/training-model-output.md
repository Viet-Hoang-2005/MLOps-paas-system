# Training Output contract v2

Only this Output contract is supported. Development databases and S3 must be reset
by the operator before testing the application; this change edits the original
TrainingJob migration and does not migrate existing output packages.

## User directories

- `SM_CHANNEL_TRAIN`: immutable Input; `MLOPS_WORK_DIR`: writable working directory.
- `SM_MODEL_DIR`: one or more independent model files, all for `MODEL_FLAVOR`.
  Scikit-learn and XGBoost accept `.pkl`/`.joblib`; PyTorch accepts `.pt`/`.pth`;
  TensorFlow/Keras accepts `.h5`/`.keras`. Empty files, links, special files,
  reserved `_mlops` paths and unsupported extensions fail the job. The runner
  validates files without deserialization; compatibility is checked at Build.
  Native XGBoost, SavedModel, TorchScript and standalone state dictionaries are
  not part of this contract.
- `SM_OUTPUT_DIR`: original reports and metadata, including label mapping and
  input schema. Supported extensions: JSON, CSV, TXT, MD, PNG, JPG/JPEG, PDF.
  Nested directories are preserved. Maximum 512 MiB total, 100 MiB per file.

The combined public result may contain at most 20,000 files. Models retain the
20 GiB total limit. The runner never gathers the whole working directory.

## Private package and publication

After successful user-process completion, the runner creates `model.tar.gz`
outside both user directories. Its three namespaces are `model/`, `metadata/`
and private `_mlops/`. The v2 manifest records framework, path, role/group, size
and SHA-256 for every public file. System-normalized metrics and captured logs
remain under `_mlops`; original Metadata is preserved. The runner sends supported
tracking params/metrics, never the package through MLflow artifact upload.

Completion observers and the trusted reporter move the job to `uploading` and
enqueue the registered Celery output finalizer. It streams and validates the
archive, materializes files with isolated attempt keys under the tenant/job
output namespace, and commits the complete index atomically. Failed attempts
remove their unpublished objects; repeated successful tasks are safe. Abruptly
killed attempts leave only unreferenced private objects, covered by job purge.
Only verified, indexed outputs become `completed`. Runtime accounting uses the
runtime's finish timestamp, excluding indexing. Cancellation/deletion fences
publication, and runtime cleanup follows the committed terminal result.

The archive is temporary transport. The indexer also materializes every `_mlops/`
file (including the manifest) under the job's `output/internal/` prefix, with
private TrainingOutput rows recording path, size and SHA-256. Those rows use
group `_mlops`; they never pass `public_outputs()`.

After the complete index commits, a separate Celery task deletes only the scoped
`model.tar.gz`. Storage failures retry with backoff without failing the completed
training result. Verification replay uses the committed index and does not HEAD
or download the deleted archive. The runner still creates the archive for upload;
it is no longer retained as the final S3 representation.

Public serializers and all downloads use only
indexed `Model/` and `Metadata/` entries. No archive row or `_mlops` row is
published. MLflow artifact paths cannot address `_mlops` or escape their prefix.
Output deletion removes the archive, materialized files and supplemental uploads;
Input snapshots remain separate.

## Explicit Project assignment

`POST /api/training-jobs/{id}/project/` accepts multipart:

- `output_revision`, required `model_id` from the job's indexed Model files;
- `project_id` or JSON `new_project`;
- JSON `artifacts`: optional slot-to-Metadata-file UUID map;
- optional `<slot>_file` JSON uploads, mutually exclusive with that slot's UUID.

The six slots are `label_mapping`, `input_schema`, `metrics`, `params`,
`model_insights`, `feature_importance`. Every selected JSON is finite UTF-8,
at most 1 MiB and validated for its role. Arbitrary filenames are valid; names
never imply roles. The client uses the shared Select for every model and Metadata
choice, requires explicit model selection even for one result, and defaults each
slot to unused. Uploaded metadata is a new immutable object, never an overwrite.

Storage validation happens before the short transaction. Under the job lock,
the service rechecks revision, ownership and availability, saves the selection
and increments `output_revision` while assigning the Project. Identical replay
is safe; conflicts return 409. Project metadata/Model Preview are not changed,
and Save does not Build or Deploy. Build source code, reference data and build
requirements remain separate supplemental configuration.

Build snapshots only the selected raw model and explicit metadata slots at the
saved revision. It never searches the package for the first model or fills gaps
from filenames, tracking, `_mlops` or Model Preview. Selected mapping/schema are
included in the serving package; selected Advanced artifacts are registered on
the version. Training metrics/log history stays unchanged.

## Output UI and downloads

The read-only tree has fixed `Model/` and `Metadata/` roots. Select a file to
download its bytes; select a directory to download that directory as ZIP; select
nothing to download both public groups as ZIP. Download is disabled for empty
selections. Text preview is capped at 2 MiB and image preview at 10 MiB; PDF is
download-only. User HTML is not executed.

Deploy the updated Control Plane/workers, runner, model-packager, Argo manifests
and FE together. Kubernetes validation is offline; cluster/staging acceptance
requires a separately authorized environment.
