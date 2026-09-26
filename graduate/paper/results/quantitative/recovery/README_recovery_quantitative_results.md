# Offline Drift/Retraining Recovery Quantitative Results

## Command used

```bash
python paper/results/quantitative/run_offline_drift_retraining_recovery_eval.py --binary --drift-threshold 0.5 --random-seed 42 --use-mixed-reference-for-drift --drift-benign-mix-fraction 0.0
```

## Scope and claim-safety note

This is an offline replay/recovery experiment. A drift alert triggers review-driven retraining and challenger registration in the experiment design. The experiment does not demonstrate fully automatic production deployment or promotion.

## Binary label mapping

`BENIGN`, `Benign`, `benign`, `Normal`, and `NORMAL` map to `BENIGN`; every other raw label maps to `ATTACK`. Metrics are binary BENIGN-vs-ATTACK metrics, not raw multiclass metrics.

## Scenario construction

For each scenario, the attack-family drift file is de-duplicated by row hash and split into trigger/retraining and future holdout subsets using the configured attack trigger fraction. BENIGN rows from `data/reference_data.csv` are also de-duplicated and split into reference baseline, retraining benign, and evaluation benign holdout subsets.

M0 is trained from `data/train_2_classes.csv`. M1 is trained only with data available after the drift trigger: the decontaminated M0 training data, the scenario trigger attack subset, and the benign retraining subset. Future holdout rows are excluded from M0/M1 fitting by row-hash decontamination and checked again after split.

## Drift method

Drift is computed with `ks_2samp` over the validated 52 numeric features. Feature drift threshold is `p < 0.05` for KS tests. Dataset drift is true when `drift_share >= 0.5`.

## Leakage check result

All scenarios report zero M1-training/future-holdout and trigger/future-holdout row-hash overlap after split: `True`.

## Summary results

- S1 PortScan: drift_share=0.981, fixed Macro-F1=0.1616, retrained Macro-F1=0.9997, Delta Macro-F1=0.8381.
- S2 BruteForce: drift_share=0.942, fixed Macro-F1=0.3744, retrained Macro-F1=0.9995, Delta Macro-F1=0.6251.
- S3 WebAttacks: drift_share=0.981, fixed Macro-F1=0.4664, retrained Macro-F1=0.9975, Delta Macro-F1=0.5311.

## How to use in the paper

Use `recovery_fixed_vs_retrained_comparison.csv` for a concise recovery table. Describe the results as an offline, framework-assisted, review-driven retraining recovery experiment. Report Accuracy, Macro-F1, Weighted-F1, drifted feature count, drift share, drift decision, and Delta Macro-F1. Do not claim fully automatic retraining, deployment, promotion, production-scale validation, or canary/blue-green behavior.

## Output files

- `recovery_dataset_summary.json`
- `recovery_experiment_config.json`
- `recovery_drift_windows.csv`
- `recovery_fixed_vs_retrained_comparison.csv`
- `recovery_fixed_model_metrics.csv`
- `recovery_retrained_model_metrics.csv`
- `recovery_per_class_metrics.csv`
- `recovery_confusion_matrices.json`
- `README_recovery_quantitative_results.md`
