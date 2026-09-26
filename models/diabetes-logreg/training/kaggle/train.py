"""Baseline Logistic Regression training script for Diabetes 30-day Readmission.

This script implements the graduation thesis training contract for the Fairlearn-aligned
Diabetes readmission workload:
  - Ingests raw diabetic_data.csv (UCI Diabetes dataset)
  - Derives target label 'readmit_30_days' (1 if readmitted == '<30', else 0)
  - Applies clinical domain transformations:
      * Excludes gender == 'Unknown/Invalid'
      * Stores 'race_all' and merges Asian/Hispanic into 'Other' for 'race'
      * Normalizes age categories, admission source, medical specialties, primary diagnoses,
        payer codes, and emergency/inpatient/outpatient history
      * Drops non-clinical identifiers and target-leaking fields from features
  - Partitions patients using StratifiedGroupKFold(n_splits=10, shuffle=True, random_state=445)
    grouped by patient_nbr:
      * Folds 0-5: Training partition (60%)
      * Folds 6-7: Validation partition (20%)
      * Fold 8: Reference baseline partition (10%)
      * Fold 9: Strictly reserved for Continuous Training (CT) replay (10%)
  - Fits an sklearn.Pipeline with ColumnTransformer + LogisticRegression(max_iter=2000, random_state=445)
  - Computes top-level evaluation metrics and comprehensive fairness assessments across race/gender
  - Exports a standard artifact archive (model.tar.gz) recognized by Model Packager
"""

import argparse
import hashlib
import json
import platform
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

TARGET_COLUMN = "readmit_30_days"
PATIENT_ID_COLUMN = "patient_nbr"
RESERVED_CT_FOLDS = [9]

NUMERIC_FEATURES = [
    "time_in_hospital",
    "num_lab_procedures",
    "num_procedures",
    "num_medications",
    "number_diagnoses",
]

CATEGORICAL_FEATURES = [
    "gender",
    "age",
    "admission_source_id",
    "medical_specialty",
    "primary_diagnosis",
    "max_glu_serum",
    "A1Cresult",
    "insulin",
    "change",
    "diabetesMed",
    "medicare",
    "medicaid",
    "had_emergency",
    "had_inpatient_days",
    "had_outpatient_days",
]

EXCLUDED_COLUMNS = [
    "encounter_id",
    "patient_nbr",
    "race",
    "race_all",
    "discharge_disposition_id",
    "readmitted",
    "readmit_binary",
]

PINNED_REQUIREMENTS = """scikit-learn==1.7.2
pandas==2.2.1
numpy==1.26.4
joblib==1.3.2
"""


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hex digest for a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as handle:
        while chunk := handle.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def set_seed(seed: int) -> None:
    """Set global random seeds for deterministic execution."""
    np.random.seed(seed)


def parse_int_list(int_str: str) -> list[int]:
    """Parse comma-separated integers."""
    return [int(item.strip()) for item in int_str.split(",") if item.strip()]


def preprocess_uci_diabetes_data(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Apply Fairlearn domain standardization to raw UCI diabetic_data.csv."""
    df = raw_df.copy()

    # 1. Target label and binary readmission
    if "readmitted" not in df.columns:
        raise ValueError("Missing required 'readmitted' column in diabetic dataset.")
    df[TARGET_COLUMN] = (df["readmitted"] == "<30").astype(int)
    df["readmit_binary"] = (df["readmitted"] != "NO").astype(int)

    # 2. Exclude gender == 'Unknown/Invalid'
    if "gender" in df.columns:
        df = df[df["gender"] != "Unknown/Invalid"].copy()

    # 3. Race handling: preserve race_all, merge Asian & Hispanic into Other for race
    if "race" in df.columns:
        df["race_all"] = df["race"].replace({"?": "Unknown"})
        df["race"] = df["race_all"].replace({"Asian": "Other", "Hispanic": "Other"})

    # 4. Age normalization
    if "age" in df.columns:
        df["age"] = df["age"].replace({"?": ""})
        df["age"] = df["age"].replace(
            ["[0-10)", "[10-20)", "[20-30)"], "30 years or younger"
        )
        df["age"] = df["age"].replace(["[30-40)", "[40-50)", "[50-60)"], "30-60 years")
        df["age"] = df["age"].replace(
            ["[60-70)", "[70-80)", "[80-90)", "[90-100)"], "Over 60 years"
        )

    # 5. Admission source id
    if "admission_source_id" in df.columns:
        df["admission_source_id"] = df["admission_source_id"].replace(
            {1: "Referral", 2: "Referral", 3: "Referral", 7: "Emergency"}
        )
        df["admission_source_id"] = df["admission_source_id"].apply(
            lambda x: x if x in ["Emergency", "Referral"] else "Other"
        )

    # 6. Discharge disposition id (standardized for fairness/EDA, excluded from model)
    if "discharge_disposition_id" in df.columns:
        df["discharge_disposition_id"] = df["discharge_disposition_id"].apply(
            lambda x: "Discharged to Home" if x == 1 else "Other"
        )

    # 7. Medical specialty
    if "medical_specialty" in df.columns:
        df["medical_specialty"] = df["medical_specialty"].replace({"?": "Missing"})
        allowed_specialties = [
            "Missing",
            "InternalMedicine",
            "Emergency/Trauma",
            "Family/GeneralPractice",
            "Cardiology",
            "Surgery",
        ]
        df["medical_specialty"] = df["medical_specialty"].apply(
            lambda x: x if x in allowed_specialties else "Other"
        )

    # 8. Primary diagnosis (diag_1)
    if "diag_1" in df.columns and "primary_diagnosis" not in df.columns:
        df["primary_diagnosis"] = df["diag_1"]

    if "primary_diagnosis" in df.columns:
        df["primary_diagnosis"] = df["primary_diagnosis"].replace(
            regex={
                "[7][1-3][0-9]": "Musculoskeletal Issues",
                "250.*": "Diabetes",
                "[4][6-9][0-9]|[5][0-1][0-9]|786": "Respiratory Issues",
                "[5][8-9][0-9]|[6][0-2][0-9]|788": "Genitourinary Issues",
            }
        )
        allowed_diagnoses = [
            "Respiratory Issues",
            "Diabetes",
            "Genitourinary Issues",
            "Musculoskeletal Issues",
        ]
        df["primary_diagnosis"] = df["primary_diagnosis"].apply(
            lambda x: x if x in allowed_diagnoses else "Other"
        )

    # 9. Payer code / Insurance features
    payer_col = (
        df["payer_code"]
        if "payer_code" in df.columns
        else pd.Series(["Unknown"] * len(df))
    )
    df["medicare"] = (payer_col == "MC").astype(int)
    df["medicaid"] = (payer_col == "MD").astype(int)

    # 10. Visit history indicators
    num_emerg = (
        df["number_emergency"]
        if "number_emergency" in df.columns
        else pd.Series([0] * len(df))
    )
    num_inpat = (
        df["number_inpatient"]
        if "number_inpatient" in df.columns
        else pd.Series([0] * len(df))
    )
    num_outpat = (
        df["number_outpatient"]
        if "number_outpatient" in df.columns
        else pd.Series([0] * len(df))
    )

    df["had_emergency"] = (num_emerg > 0).astype(int)
    df["had_inpatient_days"] = (num_inpat > 0).astype(int)
    df["had_outpatient_days"] = (num_outpat > 0).astype(int)

    # Ensure all required features are present
    all_features = NUMERIC_FEATURES + CATEGORICAL_FEATURES
    for col in all_features:
        if col not in df.columns:
            raise ValueError(f"Feature '{col}' missing after Fairlearn preprocessing.")

    # Cast numeric and categorical
    for col in NUMERIC_FEATURES:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in CATEGORICAL_FEATURES:
        df[col] = df[col].astype(str)

    return df


def build_pipeline(
    numeric_cols: list[str],
    categorical_cols: list[str],
    max_iter: int,
    seed: int,
    class_weight: str | None = "balanced",
) -> Pipeline:
    """Build unified sklearn Pipeline combining ColumnTransformer and LogisticRegression."""
    numeric_pipe = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )

    categorical_pipe = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="constant", fill_value="missing")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_pipe, numeric_cols),
            ("cat", categorical_pipe, categorical_cols),
        ],
        remainder="drop",
    )

    classifier = LogisticRegression(
        max_iter=max_iter,
        random_state=seed,
        C=1.0,
        solver="lbfgs",
        class_weight=class_weight,
    )

    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("classifier", classifier),
        ]
    )


def compute_classification_metrics(
    y_true: np.ndarray, y_probs: np.ndarray, threshold: float = 0.5
) -> dict[str, float]:
    """Compute standard classification and calibration metrics."""
    y_pred = (y_probs >= threshold).astype(int)

    pr_auc = float(average_precision_score(y_true, y_probs))
    try:
        roc_auc = float(roc_auc_score(y_true, y_probs))
    except ValueError:
        roc_auc = 0.5

    bal_acc = float(balanced_accuracy_score(y_true, y_pred))
    f1 = float(f1_score(y_true, y_pred, zero_division=0))
    prec = float(precision_score(y_true, y_pred, zero_division=0))
    rec = float(recall_score(y_true, y_pred, zero_division=0))
    brier = float(brier_score_loss(y_true, y_probs))

    return {
        "pr_auc": round(pr_auc, 6),
        "roc_auc": round(roc_auc, 6),
        "balanced_accuracy": round(bal_acc, 6),
        "f1": round(f1, 6),
        "precision": round(prec, 6),
        "recall": round(rec, 6),
        "brier_score": round(brier, 6),
        "threshold": round(threshold, 4),
    }


def compute_fairness_report_for_partition(
    partition_df: pd.DataFrame,
    y_true: np.ndarray,
    y_probs: np.ndarray,
    threshold: float = 0.5,
) -> dict[str, Any]:
    """Calculate demographic and subgroup fairness metrics and disparities."""
    y_pred = (y_probs >= threshold).astype(int)
    eval_df = partition_df.copy()
    eval_df["y_true"] = y_true
    eval_df["y_pred"] = y_pred

    def analyze_attribute(col_name: str) -> dict[str, Any]:
        if col_name not in eval_df.columns:
            return {}

        groups = sorted(eval_df[col_name].unique().tolist())
        subgroup_metrics = {}
        selection_rates = []
        recalls = []
        fnrs = []
        precisions = []

        for group in groups:
            sub = eval_df[eval_df[col_name] == group]
            count = len(sub)
            if count == 0:
                continue

            sub_true = sub["y_true"].values
            sub_pred = sub["y_pred"].values

            base_rate = float(np.mean(sub_true))
            sel_rate = float(np.mean(sub_pred))
            rec = float(recall_score(sub_true, sub_pred, zero_division=0))
            fnr = float(1.0 - rec) if np.sum(sub_true) > 0 else 0.0
            prec = float(precision_score(sub_true, sub_pred, zero_division=0))

            subgroup_metrics[str(group)] = {
                "sample_count": count,
                "base_rate": round(base_rate, 5),
                "selection_rate": round(sel_rate, 5),
                "recall": round(rec, 5),
                "false_negative_rate": round(fnr, 5),
                "precision": round(prec, 5),
            }

            selection_rates.append(sel_rate)
            recalls.append(rec)
            fnrs.append(fnr)
            precisions.append(prec)

        disparities = {}
        if selection_rates:
            max_sel = max(selection_rates)
            min_sel = min(selection_rates)
            disparities["selection_rate_difference"] = round(max_sel - min_sel, 5)
            disparities["selection_rate_ratio"] = round(min_sel / max(max_sel, 1e-6), 5)

        if recalls:
            disparities["recall_difference"] = round(max(recalls) - min(recalls), 5)
        if fnrs:
            disparities["false_negative_rate_difference"] = round(
                max(fnrs) - min(fnrs), 5
            )
        if precisions:
            disparities["precision_difference"] = round(
                max(precisions) - min(precisions), 5
            )

        return {
            "subgroups": subgroup_metrics,
            "disparities": disparities,
        }

    overall_metrics = {
        "sample_count": len(eval_df),
        "base_rate": round(float(np.mean(y_true)), 5),
        "selection_rate": round(float(np.mean(y_pred)), 5),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 5),
        "false_negative_rate": round(
            float(1.0 - recall_score(y_true, y_pred, zero_division=0)), 5
        ),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 5),
    }

    return {
        "overall": overall_metrics,
        "by_race": analyze_attribute("race"),
        "by_gender": analyze_attribute("gender"),
    }


def extract_model_insights(
    pipeline: Pipeline, numeric_cols: list[str], categorical_cols: list[str]
) -> dict[str, Any]:
    """Extract model feature coefficients, odds ratios, and top clinical risk factors."""
    preprocessor = pipeline.named_steps["preprocessor"]
    classifier = pipeline.named_steps["classifier"]

    cat_encoder = preprocessor.named_transformers_["cat"].named_steps["onehot"]
    cat_feature_names = cat_encoder.get_feature_names_out(categorical_cols).tolist()
    all_feature_names = numeric_cols + cat_feature_names

    coefficients = classifier.coef_[0].tolist()
    intercept = float(classifier.intercept_[0])

    coef_pairs = [
        {
            "feature": name,
            "coefficient": round(coef, 5),
            "odds_ratio": round(float(np.exp(coef)), 5),
        }
        for name, coef in zip(all_feature_names, coefficients)
    ]

    sorted_by_odds = sorted(coef_pairs, key=lambda x: x["odds_ratio"], reverse=True)
    top_positive = sorted_by_odds[:10]
    top_negative = sorted_by_odds[-10:][::-1]

    return {
        "intercept": round(intercept, 5),
        "total_coefficients_count": len(coefficients),
        "top_positive_risk_factors": top_positive,
        "top_protective_factors": top_negative,
        "all_coefficients": coef_pairs,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Train baseline Diabetes Readmission Logistic Regression."
    )
    parser.add_argument(
        "--data-path",
        type=str,
        default="/kaggle/input/diabetes-130-us-hospitals-for-years-1999-2008/diabetic_data.csv",
        help="Path to raw diabetic_data.csv dataset.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="/kaggle/working/diabetes-logreg-artifact",
        help="Output directory for generated model artifacts.",
    )
    parser.add_argument(
        "--seed", type=int, default=445, help="Random seed for reproducibility."
    )
    parser.add_argument(
        "--max-iter", type=int, default=2000, help="Maximum solver iterations."
    )
    parser.add_argument(
        "--n-splits",
        type=int,
        default=10,
        help="Number of StratifiedGroupKFold splits.",
    )
    parser.add_argument(
        "--train-folds", type=str, default="0,1,2,3,4,5", help="Folds for training."
    )
    parser.add_argument(
        "--val-folds", type=str, default="6,7", help="Folds for validation."
    )
    parser.add_argument(
        "--ref-folds", type=str, default="8", help="Folds for reference baseline."
    )
    parser.add_argument(
        "--ct-folds",
        type=str,
        default="9",
        help="Folds reserved for Continuous Training.",
    )
    parser.add_argument(
        "--threshold", type=float, default=0.5, help="Deployment decision threshold."
    )
    parser.add_argument(
        "--class-weight",
        type=str,
        default="balanced",
        help="Class weighting strategy ('balanced' or 'none').",
    )
    args = parser.parse_args()

    set_seed(args.seed)
    start_time = time.time()

    data_path = Path(args.data_path)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    train_folds = parse_int_list(args.train_folds)
    val_folds = parse_int_list(args.val_folds)
    ref_folds = parse_int_list(args.ref_folds)
    ct_folds = parse_int_list(args.ct_folds)

    print(
        f"[Config] Train folds: {train_folds} | Val folds: {val_folds} | Ref folds: {ref_folds}"
    )
    print(f"[Config] Reserved for Continuous Training replay: {ct_folds}")

    # Ensure reserved folds are not used in training
    used_folds = set(train_folds + val_folds + ref_folds)
    for reserved in ct_folds:
        if reserved in used_folds:
            raise ValueError(
                f"Fold {reserved} is reserved for CT replay and cannot be in training/evaluation!"
            )

    if not data_path.exists():
        raise FileNotFoundError(f"Dataset not found at: {data_path}")

    print(f"[Data] Reading dataset from {data_path}...")
    raw_df = pd.read_csv(data_path)
    print(f"[Data] Loaded {len(raw_df):,} raw records from {data_path.name}")

    # Standardize data
    print("[Preprocessing] Applying Fairlearn domain transformations...")
    df = preprocess_uci_diabetes_data(raw_df)
    print(
        f"[Schema] Records after filtering: {len(df):,} ({df[TARGET_COLUMN].sum():,} readmitted <30 days)"
    )

    # StratifiedGroupKFold partitioning by patient_nbr
    print(
        f"[Split] Applying StratifiedGroupKFold(n_splits={args.n_splits}) grouped by '{PATIENT_ID_COLUMN}'..."
    )
    sgkf = StratifiedGroupKFold(
        n_splits=args.n_splits, shuffle=True, random_state=args.seed
    )
    df["fold"] = -1
    for fold_idx, (_, test_idx) in enumerate(
        sgkf.split(df, df[TARGET_COLUMN], groups=df[PATIENT_ID_COLUMN])
    ):
        df.iloc[test_idx, df.columns.get_loc("fold")] = fold_idx

    # Partition DataFrames
    df_train = df[df["fold"].isin(train_folds)].copy()
    df_val = df[df["fold"].isin(val_folds)].copy()
    df_ref = df[df["fold"].isin(ref_folds)].copy()
    df_ct = df[df["fold"].isin(ct_folds)].copy()

    # Verify zero patient overlap across partitions
    train_pts = set(df_train[PATIENT_ID_COLUMN])
    val_pts = set(df_val[PATIENT_ID_COLUMN])
    ref_pts = set(df_ref[PATIENT_ID_COLUMN])
    ct_pts = set(df_ct[PATIENT_ID_COLUMN])

    assert len(train_pts.intersection(val_pts)) == 0, (
        "Patient leakage detected between train and val!"
    )
    assert len(train_pts.intersection(ref_pts)) == 0, (
        "Patient leakage detected between train and ref!"
    )
    assert len(train_pts.intersection(ct_pts)) == 0, (
        "Patient leakage detected between train and CT!"
    )
    assert len(val_pts.intersection(ref_pts)) == 0, (
        "Patient leakage detected between val and ref!"
    )
    assert len(val_pts.intersection(ct_pts)) == 0, (
        "Patient leakage detected between val and CT!"
    )
    assert len(ref_pts.intersection(ct_pts)) == 0, (
        "Patient leakage detected between ref and CT!"
    )

    print(
        f"[Split] Train rows: {len(df_train):,} ({len(train_pts):,} patients, pos: {df_train[TARGET_COLUMN].sum():,}, rate: {df_train[TARGET_COLUMN].mean():.4f})"
    )
    print(
        f"[Split] Val rows:   {len(df_val):,} ({len(val_pts):,} patients, pos: {df_val[TARGET_COLUMN].sum():,}, rate: {df_val[TARGET_COLUMN].mean():.4f})"
    )
    print(
        f"[Split] Ref rows:   {len(df_ref):,} ({len(ref_pts):,} patients, pos: {df_ref[TARGET_COLUMN].sum():,}, rate: {df_ref[TARGET_COLUMN].mean():.4f})"
    )
    print(
        f"[Split] CT rows:    {len(df_ct):,} ({len(ct_pts):,} patients, pos: {df_ct[TARGET_COLUMN].sum():,}, rate: {df_ct[TARGET_COLUMN].mean():.4f})"
    )

    feature_cols = NUMERIC_FEATURES + CATEGORICAL_FEATURES
    print(
        f"[Features] Total model features: {len(feature_cols)} ({len(NUMERIC_FEATURES)} numeric, {len(CATEGORICAL_FEATURES)} categorical)"
    )

    X_train = df_train[feature_cols]
    y_train = df_train[TARGET_COLUMN].values

    X_val = df_val[feature_cols]
    y_val = df_val[TARGET_COLUMN].values

    X_ref = df_ref[feature_cols]
    y_ref = df_ref[TARGET_COLUMN].values

    # Build and fit pipeline
    class_weight_val = args.class_weight if args.class_weight != "none" else None
    print(
        f"[Training] Fitting LogisticRegression pipeline (max_iter={args.max_iter}, seed={args.seed}, class_weight={class_weight_val})..."
    )
    pipeline = build_pipeline(
        NUMERIC_FEATURES,
        CATEGORICAL_FEATURES,
        args.max_iter,
        args.seed,
        class_weight_val,
    )
    pipeline.fit(X_train, y_train)
    print("[Training] Model fitted successfully!")

    # Evaluate on Validation
    val_probs = pipeline.predict_proba(X_val)[:, 1]
    val_metrics = compute_classification_metrics(y_val, val_probs, args.threshold)
    print(f"[Metrics] Validation (Folds {args.val_folds}): {val_metrics}")

    # Evaluate on Reference
    ref_probs = pipeline.predict_proba(X_ref)[:, 1]
    ref_metrics = compute_classification_metrics(y_ref, ref_probs, args.threshold)
    print(f"[Metrics] Reference (Fold {args.ref_folds}): {ref_metrics}")

    # Fairness report
    val_fairness = compute_fairness_report_for_partition(
        df_val, y_val, val_probs, args.threshold
    )
    ref_fairness = compute_fairness_report_for_partition(
        df_ref, y_ref, ref_probs, args.threshold
    )
    fairness_payload = {
        "assessment_description": "Subgroup performance and disparity report across race and gender.",
        "mitigation_applied": False,
        "evaluation_threshold": args.threshold,
        "validation_fairness": val_fairness,
        "reference_fairness": ref_fairness,
    }

    # Model insights
    insights_payload = extract_model_insights(
        pipeline, NUMERIC_FEATURES, CATEGORICAL_FEATURES
    )

    # 1. Save model.joblib
    model_joblib_path = output_dir / "model.joblib"
    joblib.dump(pipeline, model_joblib_path)
    print(f"[Artifact] Saved model pipeline to {model_joblib_path}")

    # 2. Save label_mapping.json
    label_mapping = {
        "0": "No Readmission within 30 Days",
        "1": "Readmission within 30 Days",
    }
    label_path = output_dir / "label_mapping.json"
    label_path.write_text(json.dumps(label_mapping, indent=2), encoding="utf-8")

    # 3. Save data_contract.json
    contract_payload = {
        "dataset": "diabetic_data.csv",
        "recipe_version": "fairlearn_diabetes_readmission_v1",
        "target_column": TARGET_COLUMN,
        "target_classes": [0, 1],
        "total_features": len(feature_cols),
        "feature_order": feature_cols,
        "feature_types": {
            **{col: "numeric" for col in NUMERIC_FEATURES},
            **{col: "categorical" for col in CATEGORICAL_FEATURES},
        },
        "numeric_features": NUMERIC_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "preprocessing_strategies": {
            "numeric": "SimpleImputer(median) -> StandardScaler",
            "categorical": "SimpleImputer('missing') -> OneHotEncoder(handle_unknown='ignore')",
        },
        "excluded_features": EXCLUDED_COLUMNS,
    }
    contract_path = output_dir / "data_contract.json"
    contract_path.write_text(json.dumps(contract_payload, indent=2), encoding="utf-8")

    # 4. Save metrics.json (top-level numeric keys only!)
    metrics_payload = {
        "validation_pr_auc": val_metrics["pr_auc"],
        "validation_roc_auc": val_metrics["roc_auc"],
        "validation_balanced_accuracy": val_metrics["balanced_accuracy"],
        "validation_f1": val_metrics["f1"],
        "validation_precision": val_metrics["precision"],
        "validation_recall": val_metrics["recall"],
        "validation_brier_score": val_metrics["brier_score"],
        "validation_threshold": val_metrics["threshold"],
        "reference_pr_auc": ref_metrics["pr_auc"],
        "reference_roc_auc": ref_metrics["roc_auc"],
        "reference_balanced_accuracy": ref_metrics["balanced_accuracy"],
        "reference_f1": ref_metrics["f1"],
        "reference_precision": ref_metrics["precision"],
        "reference_recall": ref_metrics["recall"],
        "reference_brier_score": ref_metrics["brier_score"],
        "reference_threshold": ref_metrics["threshold"],
    }
    metrics_path = output_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics_payload, indent=2), encoding="utf-8")

    # 5. Save fairness_report.json
    fairness_path = output_dir / "fairness_report.json"
    fairness_path.write_text(json.dumps(fairness_payload, indent=2), encoding="utf-8")

    # 6. Save split_manifest.json
    split_payload = {
        "group_column": PATIENT_ID_COLUMN,
        "target_column": TARGET_COLUMN,
        "total_records": len(df),
        "total_unique_patients": df[PATIENT_ID_COLUMN].nunique(),
        "train_folds": train_folds,
        "train_samples": len(df_train),
        "train_unique_patients": len(train_pts),
        "train_positive_count": int(df_train[TARGET_COLUMN].sum()),
        "train_positive_rate": round(float(df_train[TARGET_COLUMN].mean()), 6),
        "validation_folds": val_folds,
        "validation_samples": len(df_val),
        "validation_unique_patients": len(val_pts),
        "validation_positive_count": int(df_val[TARGET_COLUMN].sum()),
        "validation_positive_rate": round(float(df_val[TARGET_COLUMN].mean()), 6),
        "reference_folds": ref_folds,
        "reference_samples": len(df_ref),
        "reference_unique_patients": len(ref_pts),
        "reference_positive_count": int(df_ref[TARGET_COLUMN].sum()),
        "reference_positive_rate": round(float(df_ref[TARGET_COLUMN].mean()), 6),
        "continuous_training_replay_folds": ct_folds,
        "continuous_training_replay_samples": len(df_ct),
        "continuous_training_replay_unique_patients": len(ct_pts),
        "continuous_training_replay_positive_count": int(df_ct[TARGET_COLUMN].sum()),
        "continuous_training_replay_positive_rate": round(
            float(df_ct[TARGET_COLUMN].mean()), 6
        ),
        "no_patient_overlap_verified": True,
    }
    split_path = output_dir / "split_manifest.json"
    split_path.write_text(json.dumps(split_payload, indent=2), encoding="utf-8")

    # 7. Save model_insights.json
    insights_path = output_dir / "model_insights.json"
    insights_path.write_text(json.dumps(insights_payload, indent=2), encoding="utf-8")

    # 8. Save training_config.json
    config_payload = {
        "workload": "diabetes_readmission_logistic_regression",
        "flavor": "sklearn",
        "seed": args.seed,
        "hyperparameters": {
            "penalty": "l2",
            "C": 1.0,
            "solver": "lbfgs",
            "class_weight": args.class_weight,
            "max_iter": args.max_iter,
            "random_state": args.seed,
            "threshold": args.threshold,
        },
        "elapsed_seconds": round(time.time() - start_time, 2),
    }
    config_path = output_dir / "training_config.json"
    config_path.write_text(json.dumps(config_payload, indent=2), encoding="utf-8")

    # 9. Save pinned requirements.txt into artifact
    req_path = output_dir / "requirements.txt"
    req_path.write_text(PINNED_REQUIREMENTS, encoding="utf-8")

    # 10. Save artifact_manifest.json
    files_to_index = [
        "model.joblib",
        "label_mapping.json",
        "data_contract.json",
        "metrics.json",
        "fairness_report.json",
        "split_manifest.json",
        "model_insights.json",
        "training_config.json",
        "requirements.txt",
    ]
    file_manifests = {}
    for name in files_to_index:
        p = output_dir / name
        file_manifests[name] = {
            "size_bytes": p.stat().st_size,
            "sha256": compute_sha256(p),
        }

    import sklearn

    manifest_payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": file_manifests,
        "environment": {
            "python_version": sys.version,
            "platform": platform.platform(),
            "scikit_learn_version": sklearn.__version__,
            "pandas_version": pd.__version__,
            "numpy_version": np.__version__,
            "joblib_version": joblib.__version__,
        },
    }
    manifest_path = output_dir / "artifact_manifest.json"
    manifest_path.write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")

    # 11. Create model.tar.gz archive
    archive_path = output_dir / "model.tar.gz"
    all_artifact_files = files_to_index + ["artifact_manifest.json"]
    print(
        f"[Archive] Creating {archive_path} containing {len(all_artifact_files)} files..."
    )
    with tarfile.open(archive_path, "w:gz") as tar:
        for file_name in all_artifact_files:
            file_to_add = output_dir / file_name
            tar.add(file_to_add, arcname=file_name)

    archive_sha256 = compute_sha256(archive_path)
    archive_size_mb = archive_path.stat().st_size / (1024 * 1024)
    print(
        f"[Done] model.tar.gz successfully generated: {archive_size_mb:.2f} MB (SHA256: {archive_sha256})"
    )

    # Print METRIC_JSON line for MLOps Training Runner callback
    protocol_metrics = {
        "pr_auc": val_metrics["pr_auc"],
        "roc_auc": val_metrics["roc_auc"],
        "balanced_accuracy": val_metrics["balanced_accuracy"],
        "f1": val_metrics["f1"],
        "precision": val_metrics["precision"],
        "recall": val_metrics["recall"],
        "brier_score": val_metrics["brier_score"],
        "threshold": args.threshold,
    }
    print(f"METRIC_JSON:{json.dumps(protocol_metrics)}")


if __name__ == "__main__":
    main()
