"""Prepare clean 80/20 train and test datasets from raw UCI diabetic_data.csv.

Applies Fairlearn clinical domain preprocessing and splits patients with
StratifiedGroupKFold(n_splits=5) grouped by patient_nbr so no patient appears in
both training_data.csv (80%) and test_data.csv (20%).
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold

NUMERIC_FEATURES = [
    "time_in_hospital",
    "num_lab_procedures",
    "num_procedures",
    "num_medications",
    "number_diagnoses",
    "medicare",
    "medicaid",
    "had_emergency",
    "had_inpatient_days",
    "had_outpatient_days",
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
]

FEATURE_ORDER = [
    "time_in_hospital",
    "num_lab_procedures",
    "num_procedures",
    "num_medications",
    "number_diagnoses",
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

TARGET_COLUMN = "Label"
POSITIVE_LABEL = "Readmission within 30 Days"
NEGATIVE_LABEL = "No Readmission within 30 Days"
PATIENT_ID_COLUMN = "patient_nbr"


def preprocess_uci_diabetes_data(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Apply clinical domain standardization to raw UCI diabetic_data.csv."""
    df = raw_df.copy()

    if "readmitted" not in df.columns:
        raise ValueError("Missing required 'readmitted' column in diabetic dataset.")
    if PATIENT_ID_COLUMN not in df.columns:
        raise ValueError(f"Missing required '{PATIENT_ID_COLUMN}' column in dataset.")

    df["readmit_30_days"] = (df["readmitted"].astype(str).str.strip() == "<30").astype(int)
    df[TARGET_COLUMN] = np.where(
        df["readmit_30_days"] == 1, POSITIVE_LABEL, NEGATIVE_LABEL
    )

    if "gender" in df.columns:
        df = df[df["gender"].astype(str).str.strip() != "Unknown/Invalid"].copy()
        df["gender"] = (
            df["gender"].replace({"?": "Missing"}).fillna("Missing").astype(str).str.strip()
        )

    if "age" in df.columns:
        df["age"] = df["age"].replace({"?": "Missing"}).fillna("Missing")
        df["age"] = df["age"].replace(
            ["[0-10)", "[10-20)", "[20-30)"], "30 years or younger"
        )
        df["age"] = df["age"].replace(
            ["[30-40)", "[40-50)", "[50-60)"], "30-60 years"
        )
        df["age"] = df["age"].replace(
            ["[60-70)", "[70-80)", "[80-90)", "[90-100)"], "Over 60 years"
        )

    if "admission_source_id" in df.columns:
        df["admission_source_id"] = df["admission_source_id"].replace(
            {1: "Referral", 2: "Referral", 3: "Referral", 7: "Emergency"}
        )
        df["admission_source_id"] = df["admission_source_id"].apply(
            lambda x: x if x in ("Emergency", "Referral") else "Other"
        )

    if "medical_specialty" in df.columns:
        df["medical_specialty"] = (
            df["medical_specialty"].replace({"?": "Missing"}).fillna("Missing")
        )
        allowed_specialties = {
            "Missing",
            "InternalMedicine",
            "Emergency/Trauma",
            "Family/GeneralPractice",
            "Cardiology",
            "Surgery",
        }
        df["medical_specialty"] = df["medical_specialty"].apply(
            lambda x: x if x in allowed_specialties else "Other"
        )

    if "diag_1" in df.columns and "primary_diagnosis" not in df.columns:
        df["primary_diagnosis"] = df["diag_1"]

    if "primary_diagnosis" in df.columns:
        df["primary_diagnosis"] = (
            df["primary_diagnosis"].fillna("Other").astype(str).replace(
                regex={
                    "[7][1-3][0-9]": "Musculoskeletal Issues",
                    "250.*": "Diabetes",
                    "[4][6-9][0-9]|[5][0-1][0-9]|786": "Respiratory Issues",
                    "[5][8-9][0-9]|[6][0-2][0-9]|788": "Genitourinary Issues",
                }
            )
        )
        allowed_diagnoses = {
            "Respiratory Issues",
            "Diabetes",
            "Genitourinary Issues",
            "Musculoskeletal Issues",
        }
        df["primary_diagnosis"] = df["primary_diagnosis"].apply(
            lambda x: x if x in allowed_diagnoses else "Other"
        )

    payer_col = (
        df["payer_code"]
        if "payer_code" in df.columns
        else pd.Series(["Unknown"] * len(df), index=df.index)
    )
    df["medicare"] = (payer_col == "MC").astype(int)
    df["medicaid"] = (payer_col == "MD").astype(int)

    num_emerg = (
        pd.to_numeric(df["number_emergency"], errors="coerce").fillna(0)
        if "number_emergency" in df.columns
        else pd.Series([0] * len(df), index=df.index)
    )
    num_inpat = (
        pd.to_numeric(df["number_inpatient"], errors="coerce").fillna(0)
        if "number_inpatient" in df.columns
        else pd.Series([0] * len(df), index=df.index)
    )
    num_outpat = (
        pd.to_numeric(df["number_outpatient"], errors="coerce").fillna(0)
        if "number_outpatient" in df.columns
        else pd.Series([0] * len(df), index=df.index)
    )

    df["had_emergency"] = (num_emerg > 0).astype(int)
    df["had_inpatient_days"] = (num_inpat > 0).astype(int)
    df["had_outpatient_days"] = (num_outpat > 0).astype(int)

    for col in CATEGORICAL_FEATURES:
        if col not in df.columns:
            raise ValueError(f"Missing categorical feature '{col}' after preprocessing.")
        # Avoid literal "None"/"nan" tokens that pandas reads back as NaN while JS CSV reads as strings.
        df[col] = (
            df[col]
            .replace({"?": "Missing", "None": "Missing", "": "Missing"})
            .fillna("Missing")
            .astype(str)
            .str.strip()
        )

    for col in NUMERIC_FEATURES:
        if col not in df.columns:
            raise ValueError(f"Missing numeric feature '{col}' after preprocessing.")
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=NUMERIC_FEATURES).copy()
    for col in NUMERIC_FEATURES:
        df[col] = df[col].astype(int)

    return df


def split_train_test(
    df: pd.DataFrame, *, n_splits: int = 5, seed: int = 42
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split preprocessed records 80/20 by patient_nbr while stratifying target labels."""
    sgkf = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    target_rate = float(df["readmit_30_days"].mean())
    target_size = len(df) / n_splits

    best_split = None
    best_score = float("inf")
    for train_idx, test_idx in sgkf.split(
        df, df["readmit_30_days"], groups=df[PATIENT_ID_COLUMN]
    ):
        fold_rate = float(df.iloc[test_idx]["readmit_30_days"].mean())
        rate_diff = abs(fold_rate - target_rate)
        size_diff = abs(len(test_idx) - target_size) / len(df)
        score = rate_diff * 10.0 + size_diff
        if score < best_score:
            best_score = score
            best_split = (train_idx, test_idx)

    assert best_split is not None
    train_idx, test_idx = best_split
    train_df = df.iloc[train_idx].sample(frac=1.0, random_state=seed).reset_index(drop=True)
    test_df = df.iloc[test_idx].sample(frac=1.0, random_state=seed).reset_index(drop=True)

    train_patients = set(train_df[PATIENT_ID_COLUMN])
    test_patients = set(test_df[PATIENT_ID_COLUMN])
    overlap = train_patients.intersection(test_patients)
    if overlap:
        raise RuntimeError(
            f"Patient leakage detected across train/test splits: {len(overlap)} shared patients."
        )

    return train_df, test_df


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    default_input = repo_root / "models" / "diabetes-logreg" / "data" / "diabetic_data.csv"
    default_output_dir = repo_root / "models" / "diabetes-logreg" / "data"

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=default_input,
        help="Path to raw diabetic_data.csv.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output_dir,
        help="Directory where training_data.csv and test_data.csv will be written.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for StratifiedGroupKFold and row shuffling.",
    )
    args = parser.parse_args()

    if not args.input.is_file():
        raise FileNotFoundError(f"Input CSV not found: {args.input}")

    print(f"[Load] Reading raw dataset from: {args.input}")
    raw_df = pd.read_csv(args.input, keep_default_na=False)
    # Restore genuine numeric NaNs only if any non-numeric tokens exist while keeping "None" as text first
    print(f"[Load] Raw rows: {len(raw_df):,} | Unique patients: {raw_df[PATIENT_ID_COLUMN].nunique():,}")

    clean_df = preprocess_uci_diabetes_data(raw_df)
    print(
        f"[Clean] Clean rows: {len(clean_df):,} | Positive rate (<30 days): {clean_df['readmit_30_days'].mean():.4%}"
    )

    train_df, test_df = split_train_test(clean_df, n_splits=5, seed=args.seed)

    output_columns = FEATURE_ORDER + [TARGET_COLUMN]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    train_out = args.output_dir / "training_data.csv"
    test_out = args.output_dir / "test_data.csv"

    train_df[output_columns].to_csv(train_out, index=False)
    test_df[output_columns].to_csv(test_out, index=False)

    total = len(train_df) + len(test_df)
    print("\n[Summary]")
    print(
        f"  training_data.csv -> {len(train_df):,} rows ({len(train_df) / total:.2%}), "
        f"{train_df[PATIENT_ID_COLUMN].nunique():,} patients, "
        f"positive rate={train_df['readmit_30_days'].mean():.4%}"
    )
    print(
        f"  test_data.csv     -> {len(test_df):,} rows ({len(test_df) / total:.2%}), "
        f"{test_df[PATIENT_ID_COLUMN].nunique():,} patients, "
        f"positive rate={test_df['readmit_30_days'].mean():.4%}"
    )
    print("  Patient overlap: 0")
    print("\n[Distribution Check - Age]")
    print(
        pd.DataFrame(
            {
                "train_%": (train_df["age"].value_counts(normalize=True) * 100).round(2),
                "test_%": (test_df["age"].value_counts(normalize=True) * 100).round(2),
            }
        )
    )
    print("\n[Distribution Check - Primary Diagnosis]")
    print(
        pd.DataFrame(
            {
                "train_%": (
                    train_df["primary_diagnosis"].value_counts(normalize=True) * 100
                ).round(2),
                "test_%": (
                    test_df["primary_diagnosis"].value_counts(normalize=True) * 100
                ).round(2),
            }
        )
    )
    print(f"\nSaved:\n  - {train_out}\n  - {test_out}")


if __name__ == "__main__":
    main()
