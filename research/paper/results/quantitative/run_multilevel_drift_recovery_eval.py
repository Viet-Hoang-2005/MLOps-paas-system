#!/usr/bin/env python3
"""Multi-level offline NIDS drift/retraining recovery evaluation.

For each attack family (PortScan, BruteForce, WebAttacks), creates drift windows
at three attack-injection fractions:
  Mild     ~15% ATTACK + 85% BENIGN
  Moderate ~40% ATTACK + 60% BENIGN
  Severe   ~85% ATTACK + 15% BENIGN

Produces a 9-row table showing how drift_share and model recovery vary with
distribution shift intensity, which is more objective than a single window.

Usage:
    python paper/results/quantitative/run_multilevel_drift_recovery_eval.py --binary
"""
from __future__ import annotations
import argparse, hashlib, json, sys, warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

sys.dont_write_bytecode = True
import numpy as np
import pandas as pd

try:
    from sklearn.metrics import accuracy_score, f1_score
except ImportError as e:
    raise SystemExit("pip install scikit-learn") from e
try:
    from xgboost import XGBClassifier
except ImportError as e:
    raise SystemExit("pip install xgboost") from e
try:
    from scipy.stats import ks_2samp
except ImportError:
    ks_2samp = None

warnings.filterwarnings("ignore")

LABEL_COL    = "Label"
CLASS_NAMES  = ["BENIGN", "ATTACK"]
CLASS_TO_ID  = {"BENIGN": 0, "ATTACK": 1}
BENIGN_ALIASES = {"BENIGN","Benign","benign","Normal","NORMAL","normal"}
DRIFT_LEVELS = [("Mild", 0.15), ("Moderate", 0.40), ("Severe", 0.85)]

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--binary",              action="store_true", required=True)
    p.add_argument("--random-seed",         type=int,   default=42)
    p.add_argument("--drift-threshold",     type=float, default=0.30,
                   help="drift_share threshold to trigger alert (default 0.30).")
    p.add_argument("--pvalue-threshold",    type=float, default=0.05)
    p.add_argument("--max-train-rows",      type=int,   default=100_000)
    p.add_argument("--max-window-rows",     type=int,   default=50_000)
    p.add_argument("--attack-trigger-fraction", type=float, default=0.60)
    return p.parse_args()

def repo_root(): return Path(__file__).resolve().parents[3]
def out_dir():   return Path(__file__).resolve().parent / "multilevel"
def write_json(path, data): path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
def norm_label(v): return "BENIGN" if str(v).strip() in BENIGN_ALIASES else "ATTACK"

def load_csv(path, max_rows, seed):
    df = pd.read_csv(path)
    if max_rows > 0 and len(df) > max_rows:
        df = df.sample(n=max_rows, random_state=seed).reset_index(drop=True)
    return df.reset_index(drop=True)

def feat_cols(df): return [c for c in df.columns if c != LABEL_COL]

def coerce(df, cols):
    X = df[cols].apply(pd.to_numeric, errors="coerce")
    return X.replace([np.inf, -np.inf], np.nan)

def row_hashes(df, cols):
    X = coerce(df, cols).copy()
    X["__l__"] = [norm_label(v) for v in df[LABEL_COL]]
    h = pd.util.hash_pandas_object(X, index=False).astype("uint64")
    return [hashlib.sha256(str(int(v)).encode()).hexdigest() for v in h.to_numpy()]

def decontam(df, cols, blocked):
    keep = [h not in blocked for h in row_hashes(df, cols)]
    return df.loc[keep].reset_index(drop=True)

def shuffled(df, seed):
    return df.sample(frac=1.0, random_state=seed).reset_index(drop=True) if not df.empty else df.copy()

def filter_label(df, lbl):
    return df.loc[[norm_label(v)==lbl for v in df[LABEL_COL]]].reset_index(drop=True)

def prep_X(df, cols, medians):
    return coerce(df, cols).fillna(medians).fillna(0.0)

def prep_y(df):
    return np.array([CLASS_TO_ID[norm_label(v)] for v in df[LABEL_COL]], dtype=np.int64)

def train_xgb(X, y, seed):
    cnts = np.bincount(y, minlength=2)
    if cnts[0]==0 or cnts[1]==0: raise ValueError("Need both classes.")
    clf = XGBClassifier(
        objective="binary:logistic", eval_metric="logloss",
        n_estimators=160, max_depth=6, learning_rate=0.08,
        subsample=0.9, colsample_bytree=0.9, min_child_weight=1,
        reg_lambda=1.0, random_state=seed, n_jobs=1, tree_method="hist",
        scale_pos_weight=float(cnts[0]/cnts[1]) if cnts[1] else 1.0,
    )
    clf.fit(X, y)
    return clf

def evaluate(clf, X, y):
    pred = np.asarray(clf.predict(X), dtype=np.int64)
    return {
        "accuracy":    float(accuracy_score(y, pred)),
        "macro_f1":    float(f1_score(y, pred, average="macro",    zero_division=0)),
        "weighted_f1": float(f1_score(y, pred, average="weighted", zero_division=0)),
    }

def compute_drift(ref_X, cur_X, pv_thr, drift_thr):
    method = "ks_2samp" if ks_2samp else "psi_fallback"
    drifted, total, ks_stats = 0, len(ref_X.columns), []
    for col in ref_X.columns:
        rv = ref_X[col].to_numpy(dtype=float); rv = rv[np.isfinite(rv)]
        cv = cur_X[col].to_numpy(dtype=float); cv = cv[np.isfinite(cv)]
        if ks_2samp:
            if rv.size==0 or cv.size==0:
                col_drift=False; ks_stats.append(0.0)
            else:
                r = ks_2samp(rv, cv, alternative="two-sided", mode="auto")
                col_drift = bool(r.pvalue < pv_thr); ks_stats.append(float(r.statistic))
        else:
            # PSI fallback
            edges = np.unique(np.quantile(rv, np.linspace(0,1,11))) if rv.size else np.array([0,1])
            if edges.size < 2: score=0.0
            else:
                rc,_=np.histogram(rv,bins=edges); cc,_=np.histogram(cv,bins=edges)
                rp=np.maximum(rc/max(rc.sum(),1),1e-6); cp=np.maximum(cc/max(cc.sum(),1),1e-6)
                score=float(np.sum((cp-rp)*np.log(cp/rp)))
            col_drift = score >= 0.2; ks_stats.append(score)
        if col_drift: drifted += 1
    ds = drifted/total if total else 0.0
    return {
        "drifted_features": drifted, "total_features": total,
        "drift_share": round(ds, 6),
        "mean_ks_stat": round(float(np.mean(ks_stats)) if ks_stats else 0.0, 6),
        "dataset_drift": bool(ds >= drift_thr), "method": method,
    }

def main():
    args = parse_args()
    seed = args.random_seed
    root = repo_root(); data_dir = root/"data"; output = out_dir()
    output.mkdir(parents=True, exist_ok=True)

    print("="*70); print("Multi-Level Drift Recovery Evaluation"); print("="*70)

    train_raw = load_csv(data_dir/"train_2_classes.csv", args.max_train_rows, seed)
    ref_raw   = load_csv(data_dir/"reference_data.csv",  args.max_window_rows, seed)
    cols = feat_cols(train_raw)

    benign_pool = filter_label(ref_raw, "BENIGN")
    print(f"BENIGN pool: {len(benign_pool):,} rows")

    attack_sources = [
        ("S1", "PortScan",   data_dir/"drift_portscan.csv"),
        ("S2", "BruteForce", data_dir/"drift_bruteforce.csv"),
        ("S3", "WebAttacks",  data_dir/"drift_webattacks.csv"),
    ]

    all_data: Dict[str, Dict] = {}
    future_hash_union: set = set()
    for sid, family, path in attack_sources:
        atk = filter_label(load_csv(path, args.max_window_rows, seed), "ATTACK")
        atk = shuffled(atk, seed)
        n_trigger = max(1, int(len(atk)*args.attack_trigger_fraction))
        trigger_atk = atk.iloc[:n_trigger].reset_index(drop=True)
        future_atk  = atk.iloc[n_trigger:].reset_index(drop=True)
        all_data[sid] = {"family": family, "trigger_atk": trigger_atk, "future_atk": future_atk}
        future_hash_union.update(row_hashes(future_atk, cols))

    train_clean = decontam(train_raw, cols, future_hash_union)
    medians = coerce(train_clean, cols).median(numeric_only=True).fillna(0.0)

    print(f"\nTraining M0 on {len(train_clean):,} rows ...")
    model_m0 = train_xgb(prep_X(train_clean, cols, medians), prep_y(train_clean), seed)
    print("M0 trained.")

    ref_X_drift = prep_X(filter_label(ref_raw, "BENIGN"), cols, medians)

    rows: List[Dict[str, Any]] = []
    for sid, family, path in attack_sources:
        d = all_data[sid]
        trigger_atk = d["trigger_atk"]; future_atk = d["future_atk"]

        m1_df = decontam(pd.concat([train_clean, trigger_atk], ignore_index=True),
                         cols, set(row_hashes(future_atk, cols)))
        print(f"\n[{sid} {family}] Training M1 on {len(m1_df):,} rows ...")
        model_m1 = train_xgb(prep_X(m1_df, cols, medians), prep_y(m1_df), seed+hash(sid)%100)
        print(f"[{sid} {family}] M1 trained.")

        for level_name, atk_frac in DRIFT_LEVELS:
            n_atk = min(len(future_atk), 5000)
            if n_atk == 0: continue
            n_ben = 0 if atk_frac >= 1.0 else min(int(n_atk*(1-atk_frac)/atk_frac), len(benign_pool))

            atk_s = future_atk.sample(n=n_atk, random_state=seed+1, replace=False).reset_index(drop=True)
            if n_ben > 0:
                ben_s = benign_pool.sample(n=n_ben, random_state=seed+2, replace=False).reset_index(drop=True)
                win_df = shuffled(pd.concat([atk_s, ben_s], ignore_index=True), seed+3)
            else:
                win_df = atk_s

            y_win = prep_y(win_df)
            actual_atk = int((y_win==1).sum()); actual_ben = int((y_win==0).sum())
            actual_pct = actual_atk/(actual_atk+actual_ben) if (actual_atk+actual_ben) else 0.0

            win_X  = prep_X(win_df, cols, medians)
            drift  = compute_drift(ref_X_drift, win_X, args.pvalue_threshold, args.drift_threshold)
            m0_m   = evaluate(model_m0, win_X, y_win)
            m1_m   = evaluate(model_m1, win_X, y_win)
            delta  = m1_m["macro_f1"] - m0_m["macro_f1"]

            rows.append({
                "Scenario": sid, "Attack Family": family, "Drift Level": level_name,
                "Attack% in Window": round(actual_pct*100, 1),
                "BENIGN rows": actual_ben, "ATTACK rows": actual_atk,
                "Drifted Features": drift["drifted_features"],
                "Total Features":   drift["total_features"],
                "Drift Share":      drift["drift_share"],
                "Mean KS Stat":     drift["mean_ks_stat"],
                "Drift Alert":      "Yes" if drift["dataset_drift"] else "No",
                "Fixed Accuracy":   round(m0_m["accuracy"],    4),
                "Fixed Macro-F1":   round(m0_m["macro_f1"],    4),
                "Fixed Wtd-F1":     round(m0_m["weighted_f1"], 4),
                "Retrained Accuracy":   round(m1_m["accuracy"],    4),
                "Retrained Macro-F1":   round(m1_m["macro_f1"],    4),
                "Retrained Wtd-F1":     round(m1_m["weighted_f1"], 4),
                "Delta Macro-F1":   round(delta, 4),
            })
            print(f"  [{level_name:8s} {actual_pct*100:4.0f}%atk] "
                  f"drift_share={drift['drift_share']:.3f} ({drift['drifted_features']}/{drift['total_features']}f) "
                  f"ks_mean={drift['mean_ks_stat']:.3f} | "
                  f"FixedF1={m0_m['macro_f1']:.4f}  RetrainF1={m1_m['macro_f1']:.4f}  delta={delta:+.4f}")

    df = pd.DataFrame(rows)
    df.to_csv(output/"multilevel_drift_recovery_comparison.csv", index=False, float_format="%.6f")

    paper_cols = ["Scenario","Attack Family","Drift Level","Attack% in Window",
                  "Drift Share","Mean KS Stat","Drift Alert",
                  "Fixed Macro-F1","Retrained Macro-F1","Delta Macro-F1"]
    df[paper_cols].to_csv(output/"multilevel_paper_table.csv", index=False, float_format="%.4f")

    write_json(output/"multilevel_experiment_config.json", {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "command": "python " + " ".join(sys.argv),
        "random_seed": seed,
        "drift_levels": [{"name": n, "attack_fraction": f} for n, f in DRIFT_LEVELS],
        "drift_threshold": args.drift_threshold,
        "pvalue_threshold": args.pvalue_threshold,
    })

    print("\n"+"="*70); print("PAPER TABLE (compact)"); print("="*70)
    print(df[paper_cols].to_string(index=False))
    print(f"\nOutputs: {output}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
