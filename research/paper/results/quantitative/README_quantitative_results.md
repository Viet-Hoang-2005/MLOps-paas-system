# Offline Drift/Retraining Quantitative Results

## Command used

```bash
python paper/results/quantitative/run_offline_drift_retraining_eval.py --binary --drift-threshold 0.5 --random-seed 42
```

## Data files used

- `data/train_2_classes.csv` (fixed baseline training)
- `data/train_5_classes.csv` (challenger training (decontaminated against evaluation windows))
- `data/reference_data.csv` (reference drift baseline)
- `data/test_data.csv` (similar/holdout replay window)
- `data/drift_portscan.csv` (drift replay window)
- `data/drift_bruteforce.csv` (drift replay window)
- `data/drift_webattacks.csv` (drift replay window)
- `data/portscan.csv` (optional drift replay window)

## Binary label mapping

The experiment maps `BENIGN`, `Benign`, `benign`, `Normal`, and `NORMAL` to `BENIGN`. Every other label is mapped to `ATTACK`. Raw multiclass labels are not compared directly.

## Model training sources

- Fixed baseline model `M0-fixed-XGB`: trained freshly and reproducibly on `data/train_2_classes.csv` after removing rows that overlap evaluation windows by row hash.
- Challenger/retrained model `M1-challenger-XGB`: trained freshly and reproducibly on `data/train_5_classes.csv` after removing rows that overlap evaluation windows by row hash.
- Existing `models/v1` and `models/v2` artifacts are inspected for compatibility only and are not used for metric generation.

## Drift method

Drift is computed between `data/reference_data.csv` and each replay window over the validated 52-feature schema. Method used: `ks_2samp`. Dataset drift is true when `drift_share >= 0.5`. For KS drift, feature drift is true when `p < 0.05`. If SciPy is unavailable, the script falls back to a documented PSI-style threshold.

## Threshold

- Feature-level p-value threshold: `0.05`.
- Dataset-level drift-share threshold: `0.5`.

## Leakage check result

No row-hash overlap was detected after removing overlapping training rows before model fitting.

The leakage check uses row hashes over numeric feature columns plus normalized binary `Label`. See `experiment_config.json` for per-pair overlap counts and removed training-row counts.

## Summary results

- W1 `test_data.csv`: drift_share=0.981, fixed Macro-F1=0.4519, framework Macro-F1=0.4519, Delta Macro-F1=0.0000.
- W2 `drift_portscan.csv`: drift_share=0.981, fixed Macro-F1=0.0000, framework Macro-F1=0.0000, Delta Macro-F1=0.0000.
- W3 `drift_bruteforce.csv`: drift_share=0.981, fixed Macro-F1=0.0015, framework Macro-F1=0.0000, Delta Macro-F1=-0.0015.
- W4 `drift_webattacks.csv`: drift_share=0.981, fixed Macro-F1=0.0000, framework Macro-F1=0.0000, Delta Macro-F1=0.0000.
- W5 `portscan.csv`: drift_share=0.981, fixed Macro-F1=0.0000, framework Macro-F1=0.0000, Delta Macro-F1=0.0000.

## How to cite/use these numbers in the paper

Use `fixed_vs_framework_comparison.csv` for the main quantitative table. Phrase the experiment as an offline replay comparing a fixed baseline model with a framework-assisted path where a drift alert triggers review-driven retraining/registration. In the active-model comparison, the first detected drift window is the alert/review trigger and the challenger is used for subsequent windows. Report Accuracy, Macro-F1, Weighted-F1, drifted feature count, drift share, drift decision, and Delta Macro-F1. Avoid describing the path as fully automatic production deployment or automatic promotion.

## Claim-safety note

This is an offline replay experiment. It does not demonstrate production-scale validation or fully automatic deployment/promotion.

## Output files

- `dataset_summary.json`
- `model_compatibility.json`
- `drift_windows.csv`
- `drift_results.json`
- `fixed_model_metrics.csv`
- `challenger_model_metrics.csv`
- `fixed_vs_framework_comparison.csv`
- `per_class_metrics.csv`
- `confusion_matrices.json`
- `experiment_config.json`
- `README_quantitative_results.md`
