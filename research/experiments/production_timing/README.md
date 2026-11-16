# CSoNet production timing

## Current presentation handoff

The current files are `research/slide/CSONET_2026_Presentation.pptx`, its PDF and the bilingual notes in the same folder. The deck has 24 slides. Slides 1–23 retain the original presentation content, including the original slide 18. Hidden backup A2 follows References and presents the serving path, median inference p95 and valid response count from the post-restart cohort. Monitoring report duration is retained in the experiment reports.

The serving backup uses the original 23-slide source from commit `07d1449d` so it can be reproduced after publishing the updated deck. Build it with `author_serving_backup.mjs`, `append_serving_backup.py`, `sync_chart_cache.py`, and `finalize_slides.mjs CSONET_2026_Presentation_Serving_Backup 24`. Export with `export_slides.ps1 -OutputStem CSONET_2026_Presentation_Serving_Backup -ExpectedSlides 24`. The validated exports and notes are also retained in `output/`.

This experiment adds two operational measurements to the deployed NIDS replay.

- Median of the three per-repeat client inference p95 values, in milliseconds.
- Median observed window-to-report availability across completed windows, in seconds, with the completion denominator reported for the three planned repeats.

Each repeat sends the frozen `S0_n1000_s42` window through the public HTTPS endpoint at a target of five requests per second with at most ten concurrent requests. The client reads the complete response body before stopping the inference timer. The report timer starts immediately before dispatching the final request and ends after the automatic run completes and its JSON and HTML reports can be retrieved. It includes persistence, triggering, scheduling, execution, callback, polling and report retrieval.

## Inputs and isolation

Use the retained bundle under `research/paper/experiments/drift_only/handoff_exports/nids_replay_portable_20260928`. `load_bundle` verifies the supplied checksums and 52-feature schema. Model and input artifacts remain unchanged. Labels remain client-side.

The project name starts with `csonet-timing-`. It belongs to the explicitly selected existing owner account. `bridge.py` issues a short-lived owner access token through the server's existing token implementation and keeps it in process memory. It does not store credentials. Project creation, uploads, build, registration, deployment and monitoring use the platform APIs.

Warm up with 50 requests. Audit and remove those benchmark records before creating a monitor. Each of the three repeats uses a fresh monitor with a trigger threshold of 1,000 records. The dataset drift threshold remains 0.60. After saving the report and complete record evidence, disable that monitor and remove only the verified prediction IDs from this benchmark version. Cleanup rejects unexpected IDs or request prefixes. Other projects remain outside the cleanup query.

## Commands

Python dependencies include httpx, numpy, pandas, xgboost, mlflow and pytest. OpenSSH and access to the current K3s master are needed for owner-scoped record audit and cleanup. Replace the connection and account placeholders with the team's current values.

```powershell
python research/experiments/production_timing/prepare.py --host USER@MASTER --key KEY_PATH --owner OWNER_EMAIL --api https://api.mlops-nids-nt114.id.vn/api --bundle BUNDLE_PATH --output OUTPUT_PATH
python research/experiments/production_timing/benchmark_production.py --host USER@MASTER --key KEY_PATH --owner OWNER_EMAIL --api https://api.mlops-nids-nt114.id.vn/api --bundle BUNDLE_PATH --output OUTPUT_PATH
python research/experiments/production_timing/capture_environment.py --host USER@MASTER --key KEY_PATH --output OUTPUT_PATH/environment.json
python -m pytest research/experiments/production_timing/test_benchmark_production.py -q -p no:cacheprovider
```

The benchmark requires a new measurement directory. Failed attempts retain their evidence. To measure again, prepare a fresh output directory with the verified deployment metadata and confirm that the benchmark version has no residual records or active monitors. Preparation can resume from its journal. `--resume` retains already summarized repeats after checking their cleanup receipts and continues the remaining repeats. Measurement refuses to overwrite existing warm-up or unsummarized repeat folders.

## Packaging compatibility

The retained MLflow adapter uses `mlflow.pyfunc.loaders.code_model`, which the current package validator rejects. `package_native.py` creates a derivative package using the supported native `mlflow.xgboost` loader and verifies all 12,000 frozen replay predictions against retained scoring files. It does not retrain the booster.

The first native build exceeded its 512 MiB validation-container memory limit during dependency installation. The CPU package uses XGBoost CPU 3.2.0 with the serving base's pandas/NumPy versions. The smaller CPU distribution is documented by the XGBoost project. Preparation failures, diagnostics and package-verification records are retained in the run folder. [XGBoost installation guide](https://xgboost.readthedocs.io/en/release_3.2.0/install.html)

```powershell
python research/experiments/production_timing/package_native.py --bundle BUNDLE_PATH --output OUTPUT_PATH --cpu
python research/experiments/production_timing/prepare.py --host USER@MASTER --key KEY_PATH --owner OWNER_EMAIL --api https://api.mlops-nids-nt114.id.vn/api --bundle BUNDLE_PATH --output OUTPUT_PATH --replacement-artifact OUTPUT_PATH/native-cpu-model.zip
```

## Evidence and interpretation

The run folder retains the configuration manifest, preparation journal, package verification, request timings, record audit, drift reports, cleanup receipts and per-repeat summaries. Tokens and presigned download URLs are excluded from saved measurement records. Image identities, resource requests/limits and node inventory are captured separately.

HTTP/response failures and prediction mismatches are separate fields. No inference retry is automatic. Following the user's decision recorded in `protocol-amendment.json`, all planned repeats and their client errors remain in the experiment. Inference p95 uses successful responses and reports the error count separately. Record audit permits a failed client response to have an acknowledged server-side record, while requiring all successful response IDs to match the database. It retains missing request IDs explicitly.

A completed report timing requires exactly 1,000 matching records and zero prediction mismatches. The report-time median uses completed windows and displays its denominator. A window below the trigger threshold has no report duration. The percentile method is linear. Report polling occurs every two seconds. The availability observation includes polling, public-network overhead and the complete HTML download. Evidently's script-based HTML fragment is accepted as an HTML report.

This controlled deployed-system timing experiment supplies evidence for inference and monitoring integration. The original September drift/recall measurements retain their own provenance and configuration. Infrastructure recovery before the measurements includes the targeted notification-pod resize, standby restart and the narrowly scoped gateway-to-Control-Plane JWKS policy. The source policy is under `k8s/workloads/base/control-plane/network-policy.yaml`.

## EC2 restart validation

The original cohort is retained in `results/run_20261115`, including its ReadError and incomplete window. `results/run_20261116_postrestart` contains three additional repeats after starting the same master and two workers through AWS CLI. The post-restart report compares both cohorts separately. Authenticate model health requests through the gateway.

The separate post-restart deck and bilingual notes are in `output/`. To rebuild its annotation, pass `run_20261116_postrestart` to `author_slide_metric.mjs`, run `merge_slide_metric.py` and `sync_chart_cache.py`, then pass `CSONET_2026_Presentation_Post_Restart` to `finalize_slides.mjs`. Use the same value with `export_slides.ps1 -OutputStem`. Finalization requires a fresh destination and receipt path, so retain earlier exports before rebuilding.
