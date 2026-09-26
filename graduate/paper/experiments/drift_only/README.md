# Fixed-model NIDS drift experiment

Isolated experiment for the CSoNet revision. The Vietnamese baseline report and limitations are in [CSONET_2026_NIDS_DRIFT_EXPERIMENT_BASELINE_VI.md](CSONET_2026_NIDS_DRIFT_EXPERIMENT_BASELINE_VI.md). Completed artifacts: [results/run_20260926](results/run_20260926). Preserve this run as a baseline; write subsequent experiments to a new output directory.

## Reproduce

Run from the repository root in a Python environment with NumPy, pandas, SciPy, scikit-learn, XGBoost and Matplotlib. Exact versions used are recorded in `results/run_20260926/environment.json`; `requirements.txt` pins those library versions. Use a separate environment if installing dependencies.

```powershell
python -m pip install -r graduate/paper/experiments/drift_only/requirements.txt
python -X utf8 graduate/paper/experiments/drift_only/run_experiment.py --output graduate/paper/experiments/drift_only/results/reproduction
python -X utf8 graduate/paper/experiments/drift_only/verify_results.py graduate/paper/experiments/drift_only/results/reproduction
```

The output directory must not already exist. The runner does not download data, contact cloud services, execute uploaded models, or edit source CSVs/manuscript files. Its audit reads `data/*.csv`. Its experiment uses only `data/reference_data.csv`; the name reflects the original pipeline role, not the new experimental split.

Required source SHA-256:

```text
0728925d293f433a3f7bce4509c00e1648906c59c59d8e63663e1622a226ef6c
```

The team provided the lineage links in `config.json`. Obtain the exact local CSV from the team: downloading a different Kaggle version is not guaranteed to reproduce these results. A public reproducible artifact still needs a versioned data acquisition procedure and licensing checks; local reproducibility alone does not complete that requirement.

## Protocol

- Canonicalize the 52 numeric features; exclude nonfinite rows and feature-identical rows with conflicting labels, then deduplicate exact feature vectors. Split the remaining data into train/development/reference/evaluation pools (50/10/20/20%, per label). Exact feature identities never cross pools.
- Fit one XGBoost model on BENIGN and DDoS only, using the train pool. Other attack families are deliberately unseen during fitting. Keep the model and 0.5 prediction threshold fixed. Development pilot windows check execution only.
- Fix a 5,000-row reference with 70% BENIGN and 30% DDoS. Sample evaluation windows of 500 and 1,000 rows without replacement within each window. Reuse of rows across windows is allowed and explicitly recorded.
- S0: unchanged composition. S1: change attack prevalence to 15/50/85%, keeping DDoS as the only attack. S2: hold total attack prevalence at 30%, replacing 25/50/100% of DDoS with an approximately equal mixture of PortScan, BruteForce and WebAttacks.
- Use two-sided asymptotic KS tests per feature, BH correction within each window at 0.05, and dataset alerts when the proportion of flagged features is at least 0.1/0.3/0.5/0.7. The principal threshold is 0.3. The raw, uncorrected results are retained for sensitivity comparison. This standalone implementation is not a benchmark of the deployed Evidently integration.
- Five sampling seeds per scenario/size; 25 additional S0 seeds per size for a larger stable-control sample. Total: 120 windows, 6,240 feature tests. The main scenario table/plot uses five seeds for every scenario; the threshold table/heatmap uses all 30 stable windows per size and five per shifted scenario/size.
- Report macro-F1, attack recall, benign false-positive rate, ROC-AUC, family recall, drift share and KS effect statistics. Standard deviations describe window sampling under one model/reference, not uncertainty across datasets or model fits. Alerts on S1 are evidence of distribution shift, not false alerts merely because accuracy stays high.

## Artifact map

| Artifact | Purpose |
|---|---|
| `dataset_manifest.json`, `source_file_audit.json`, `source_file_overlap.csv` | Source checksums, exclusions and old-file overlap audit |
| `split_manifest.csv.gz`, `split_counts.csv`, `split_overlap.json` | Exact split assignments and checks |
| `excluded_rows.csv`, `duplicate_rows_removed.csv` | Removal accounting |
| `reference_manifest.csv`, `window_membership.csv.gz` | Original zero-based source row IDs for every comparison |
| `baseline.ubj`, `model_manifest.json` | Fixed model and fit metadata |
| `window_metrics.csv`, `feature_drift.csv.gz` | Full window and per-feature results |
| `scenario_summary.csv`, `threshold_summary.csv` | Aggregated main results and sensitivity |
| `*.png`, `*.pdf` | Raster and vector figures |
| `verification.json` | Independent replay of all predictions/statistical tests |
| `environment.json`, `config.json`, `completion.json` | Runtime, protocol, runner hash and completion |

## Scope limits

These are controlled composition shifts in a third-party preprocessed and team-subsampled CICIDS2017 derivative. No temporal validation, concept-drift identification, retraining comparison, serving scalability, or security-isolation claim follows. Upstream feature selection used combined data; splitting afterward cannot remove that potential leakage. Exact deduplication does not establish flow/session/host independence. Stable windows have fixed class counts; alert frequency is conditional on this sampling design. KS asymptotic p-values on tied network-flow features and correlated features need cautious interpretation; BH here is a defined comparison rule, not a guarantee of dataset-level false-alert control.
