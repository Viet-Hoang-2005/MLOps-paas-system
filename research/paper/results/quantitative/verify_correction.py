#!/usr/bin/env python3
"""Verify that Bonferroni and Benjamini-Hochberg corrections do not change
the drift detection conclusions for any of the 9 scenarios."""

from __future__ import annotations
import hashlib, json, sys, warnings
from pathlib import Path
from typing import Any, List, Sequence

sys.dont_write_bytecode = True
import numpy as np, pandas as pd
from scipy.stats import ks_2samp

warnings.filterwarnings("ignore")

LABEL_COL = "Label"
BENIGN_ALIASES = {"BENIGN", "Benign", "benign", "Normal", "NORMAL", "normal"}
SEED = 42
MAX_TRAIN = 100_000
MAX_WIN = 50_000
TRIGGER_FRAC = 0.60
LEVELS = [("Mild", 0.15), ("Moderate", 0.40), ("Severe", 0.85)]
ATTACKS = [("PortScan", "drift_portscan.csv"), ("BruteForce", "drift_bruteforce.csv"), ("WebAttacks", "drift_webattacks.csv")]

def repo_root(): return Path(__file__).resolve().parents[3]
def norm(v): return "BENIGN" if str(v).strip() in BENIGN_ALIASES else "ATTACK"
def load(p, mx):
    df = pd.read_csv(p)
    if mx > 0 and len(df) > mx: df = df.sample(n=mx, random_state=SEED).sort_index().reset_index(drop=True)
    return df.reset_index(drop=True)
def fcols(df): return [c for c in df.columns if c != LABEL_COL]
def coerce(df, cols):
    X = df.loc[:, list(cols)].apply(pd.to_numeric, errors="coerce")
    return X.replace([np.inf, -np.inf], np.nan)
def filt(df, label):
    return df.loc[[norm(v) == label for v in df[LABEL_COL]]].reset_index(drop=True)

def benjamini_hochberg(pvalues: np.ndarray, alpha: float = 0.05) -> np.ndarray:
    """Return boolean array: True if feature is drifted after BH correction."""
    m = len(pvalues)
    sorted_idx = np.argsort(pvalues)
    sorted_p = pvalues[sorted_idx]
    thresholds = alpha * np.arange(1, m + 1) / m
    # Find largest k where p(k) <= threshold(k)
    rejected = np.zeros(m, dtype=bool)
    max_k = -1
    for k in range(m):
        if sorted_p[k] <= thresholds[k]:
            max_k = k
    if max_k >= 0:
        rejected[sorted_idx[:max_k + 1]] = True
    return rejected

def main():
    root = repo_root()
    data = root / "data"
    out = Path(__file__).resolve().parent / "correction_verification"
    out.mkdir(parents=True, exist_ok=True)

    train_raw = load(data / "train_2_classes.csv", MAX_TRAIN)
    ref_raw = load(data / "reference_data.csv", MAX_WIN)
    cols = fcols(train_raw)
    n_features = len(cols)
    alpha = 0.05
    bonferroni_alpha = alpha / n_features

    ref_benign = filt(ref_raw, "BENIGN").sample(frac=1.0, random_state=SEED).reset_index(drop=True)
    medians = coerce(train_raw, cols).median(numeric_only=True).fillna(0.0)
    ref_X = coerce(ref_benign, cols).fillna(medians).fillna(0.0)

    print("=" * 90)
    print(f"Multiple-Testing Correction Verification")
    print(f"Features: {n_features}, alpha={alpha}, Bonferroni alpha={bonferroni_alpha:.6f}")
    print("=" * 90)

    results = []
    for fi, (family, fname) in enumerate(ATTACKS):
        atk_raw = load(data / fname, MAX_WIN)
        atk_only = filt(atk_raw, "ATTACK").sample(frac=1.0, random_state=SEED + fi).reset_index(drop=True)
        n_trig = min(max(1, int(len(atk_only) * TRIGGER_FRAC)), len(atk_only) - 1)
        future_atk = atk_only.iloc[n_trig:].reset_index(drop=True)

        for level_name, atk_frac in LEVELS:
            n_atk = min(len(future_atk), 5000)
            n_ben = min(int(round(n_atk * (1.0 - atk_frac) / max(atk_frac, 1e-9))), len(ref_benign)) if atk_frac < 0.99 else 0
            
            atk_s = future_atk.sample(n=n_atk, random_state=SEED + fi*10 + hash(level_name) % 100).reset_index(drop=True)
            if n_ben > 0:
                ben_s = ref_benign.sample(n=n_ben, random_state=SEED + fi*10 + hash(level_name) % 200 + 1).reset_index(drop=True)
                win = pd.concat([atk_s, ben_s], ignore_index=True)
            else:
                win = atk_s
            win = win.sample(frac=1.0, random_state=SEED + fi*10 + hash(level_name) % 300 + 2).reset_index(drop=True)
            
            win_X = coerce(win, cols).fillna(medians).fillna(0.0)

            # Run KS tests
            pvalues = np.zeros(n_features)
            ks_stats = np.zeros(n_features)
            for j, feat in enumerate(cols):
                r = ref_X[feat].dropna().to_numpy()
                c = win_X[feat].dropna().to_numpy()
                if r.size == 0 or c.size == 0:
                    pvalues[j] = 1.0
                    continue
                res = ks_2samp(r, c)
                ks_stats[j] = res.statistic
                pvalues[j] = res.pvalue

            # Uncorrected
            uncorr_drifted = int(np.sum(pvalues < alpha))
            # Bonferroni
            bonf_drifted = int(np.sum(pvalues < bonferroni_alpha))
            # Benjamini-Hochberg
            bh_rejected = benjamini_hochberg(pvalues, alpha)
            bh_drifted = int(np.sum(bh_rejected))

            # Show p-value stats
            p_min = float(np.min(pvalues))
            p_max = float(np.max(pvalues))
            p_median = float(np.median(pvalues))
            n_pval_zero = int(np.sum(pvalues == 0.0))  # exact zero (< machine epsilon)

            row = {
                "Family": family, "Level": level_name,
                "Uncorrected": uncorr_drifted,
                "Bonferroni": bonf_drifted,
                "BH": bh_drifted,
                "Total": n_features,
                "p_min": p_min, "p_max": p_max, "p_median": p_median,
                "n_pval_near_zero": n_pval_zero,
                "conclusion_changed": uncorr_drifted != bonf_drifted,
            }
            results.append(row)

            changed = "** CHANGED **" if uncorr_drifted != bonf_drifted else "same"
            print(f"  {family:>10s} {level_name:>8s} | "
                  f"Uncorr={uncorr_drifted}/{n_features}  "
                  f"Bonf={bonf_drifted}/{n_features}  "
                  f"BH={bh_drifted}/{n_features}  "
                  f"p_med={p_median:.2e}  "
                  f"[{changed}]")

    df = pd.DataFrame(results)
    df.to_csv(out / "correction_comparison.csv", index=False)

    any_changed = df["conclusion_changed"].any()
    print("\n" + "=" * 90)
    print(f"VERDICT: Bonferroni correction changes any conclusion? {any_changed}")
    if not any_changed:
        print("All 9 scenarios: Bonferroni-corrected drifted count == uncorrected count.")
        print("Safe to add: 'Applying Bonferroni correction does not change any drift decision.'")
    print("=" * 90)

    # Save summary
    summary = {
        "alpha": alpha,
        "bonferroni_alpha": bonferroni_alpha,
        "n_features": n_features,
        "any_conclusion_changed": bool(any_changed),
        "results": results,
    }
    (out / "correction_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nResults saved to: {out.relative_to(repo_root())}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
