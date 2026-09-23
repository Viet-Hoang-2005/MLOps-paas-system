"""Unit tests for Kaggle Diabetes Logistic Regression training script and artifact generation."""

import importlib.util
import json
import sys
import tarfile
import tempfile
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

try:
    import mlflow
    import mlflow.pyfunc
    import mlflow.sklearn

    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False


def load_modules():
    """Dynamically import train.py and model-packager modules."""
    train_path = Path(__file__).parent / "train.py"
    spec_train = importlib.util.spec_from_file_location("diabetes_train", train_path)
    diabetes_train = importlib.util.module_from_spec(spec_train)
    spec_train.loader.exec_module(diabetes_train)

    repo_root = Path(__file__).resolve().parents[4]
    packager_root = repo_root / "services" / "model-packager"
    if str(packager_root) not in sys.path:
        sys.path.insert(0, str(packager_root))

    packager_tasks_path = packager_root / "src" / "tasks.py"
    spec_tasks = importlib.util.spec_from_file_location(
        "model_packager_tasks", packager_tasks_path
    )
    model_packager_tasks = importlib.util.module_from_spec(spec_tasks)
    spec_tasks.loader.exec_module(model_packager_tasks)

    packager_core_path = packager_root / "src" / "core.py"
    spec_core = importlib.util.spec_from_file_location(
        "model_packager_core", packager_core_path
    )
    model_packager_core = importlib.util.module_from_spec(spec_core)
    spec_core.loader.exec_module(model_packager_core)

    return diabetes_train, model_packager_tasks, model_packager_core


def create_synthetic_diabetes_csv(output_path: Path, num_patients: int = 120) -> None:
    """Generate realistic synthetic diabetic_data.csv for unit testing."""
    np.random.seed(445)
    records = []
    encounter_counter = 1000

    races = ["Caucasian", "AfricanAmerican", "Asian", "Hispanic", "Other", "?"]
    genders = ["Female", "Male", "Unknown/Invalid"]
    ages = [
        "[0-10)",
        "[10-20)",
        "[20-30)",
        "[30-40)",
        "[40-50)",
        "[50-60)",
        "[60-70)",
        "[70-80)",
        "[80-90)",
        "[90-100)",
    ]
    admission_sources = [1, 2, 7, 4, 17, 20]
    specialties = [
        "InternalMedicine",
        "Emergency/Trauma",
        "Family/GeneralPractice",
        "Cardiology",
        "Surgery",
        "?",
        "Pediatrics",
    ]
    diagnoses = ["250.01", "250.4", "715.9", "486", "599.0", "786.5", "414.0", "V58.61"]
    readmit_options = ["NO", ">30", "<30"]

    for patient_id in range(1001, 1001 + num_patients):
        patient_race = np.random.choice(races, p=[0.70, 0.18, 0.02, 0.04, 0.03, 0.03])
        # Only inject Unknown/Invalid for 1 specific patient to test filter
        if patient_id == 1001:
            patient_gender = "Unknown/Invalid"
        else:
            patient_gender = np.random.choice(["Female", "Male"])

        num_encounters = np.random.choice([1, 2, 3], p=[0.7, 0.2, 0.1])
        for _ in range(num_encounters):
            encounter_counter += 1
            readmit_val = np.random.choice(readmit_options, p=[0.55, 0.33, 0.12])

            records.append(
                {
                    "encounter_id": encounter_counter,
                    "patient_nbr": patient_id,
                    "race": patient_race,
                    "gender": patient_gender,
                    "age": np.random.choice(ages),
                    "weight": "?",
                    "admission_type_id": np.random.choice([1, 2, 3]),
                    "discharge_disposition_id": np.random.choice([1, 2, 3, 6]),
                    "admission_source_id": np.random.choice(admission_sources),
                    "time_in_hospital": np.random.randint(1, 14),
                    "payer_code": np.random.choice(["MC", "MD", "BC", "SP", "?"]),
                    "medical_specialty": np.random.choice(specialties),
                    "num_lab_procedures": np.random.randint(1, 100),
                    "num_procedures": np.random.randint(0, 6),
                    "num_medications": np.random.randint(1, 40),
                    "number_outpatient": np.random.randint(0, 5),
                    "number_emergency": np.random.randint(0, 3),
                    "number_inpatient": np.random.randint(0, 4),
                    "diag_1": np.random.choice(diagnoses),
                    "diag_2": "250.0",
                    "diag_3": "401.9",
                    "number_diagnoses": np.random.randint(1, 10),
                    "max_glu_serum": np.random.choice(["None", "Norm", ">200", ">300"]),
                    "A1Cresult": np.random.choice(["None", "Norm", ">7", ">8"]),
                    "metformin": np.random.choice(["No", "Steady"]),
                    "repaglinide": "No",
                    "nateglinide": "No",
                    "chlorpropamide": "No",
                    "glimepiride": "No",
                    "acetohexamide": "No",
                    "glipizide": "No",
                    "glyburide": "No",
                    "tolbutamide": "No",
                    "pioglitazone": "No",
                    "rosiglitazone": "No",
                    "acarbose": "No",
                    "miglitol": "No",
                    "troglitazone": "No",
                    "tolazamide": "No",
                    "examide": "No",
                    "citoglipton": "No",
                    "insulin": np.random.choice(["No", "Steady", "Up", "Down"]),
                    "glyburide-metformin": "No",
                    "glipizide-metformin": "No",
                    "glimepiride-pioglitazone": "No",
                    "metformin-rosiglitazone": "No",
                    "metformin-pioglitazone": "No",
                    "change": np.random.choice(["Ch", "No"]),
                    "diabetesMed": np.random.choice(["Yes", "No"]),
                    "readmitted": readmit_val,
                }
            )

    df = pd.DataFrame(records)
    df.to_csv(output_path, index=False)


def run_pipeline_verification(tmp_path: Path):
    """Core assertion routine verifying end-to-end diabetes training and packaging."""
    diabetes_train, model_packager_tasks, model_packager_core = load_modules()

    # 1. Prepare synthetic data and output directories
    csv_path = tmp_path / "synthetic_diabetic_data.csv"
    output_dir = tmp_path / "artifact_output"
    create_synthetic_diabetes_csv(csv_path, num_patients=120)

    # 2. Invoke train.py via main() with CLI args
    orig_argv = sys.argv
    try:
        sys.argv = [
            "train.py",
            "--data-path",
            str(csv_path),
            "--output-dir",
            str(output_dir),
            "--seed",
            "445",
            "--max-iter",
            "100",
            "--threshold",
            "0.5",
        ]
        diabetes_train.main()
    finally:
        sys.argv = orig_argv

    # 3. Verify generated artifacts on disk
    expected_files = [
        "model.joblib",
        "label_mapping.json",
        "data_contract.json",
        "metrics.json",
        "fairness_report.json",
        "split_manifest.json",
        "model_insights.json",
        "training_config.json",
        "requirements.txt",
        "artifact_manifest.json",
        "model.tar.gz",
    ]
    for filename in expected_files:
        filepath = output_dir / filename
        assert filepath.exists(), f"Missing expected artifact: {filename}"

    # 4. Verify split_manifest.json: patient group isolation and CT replay reservation
    with open(output_dir / "split_manifest.json", "r", encoding="utf-8") as f:
        split_manifest = json.load(f)
    assert split_manifest["train_folds"] == [0, 1, 2, 3, 4, 5]
    assert split_manifest["validation_folds"] == [6, 7]
    assert split_manifest["reference_folds"] == [8]
    assert split_manifest["continuous_training_replay_folds"] == [9]
    assert split_manifest["no_patient_overlap_verified"] is True
    assert split_manifest["train_samples"] > 0
    assert split_manifest["continuous_training_replay_samples"] > 0

    # 5. Verify metrics.json: top-level numeric values only
    with open(output_dir / "metrics.json", "r", encoding="utf-8") as f:
        metrics = json.load(f)
    assert isinstance(metrics, dict)
    required_metric_keys = [
        "validation_pr_auc",
        "validation_roc_auc",
        "validation_balanced_accuracy",
        "validation_f1",
        "validation_precision",
        "validation_recall",
        "validation_brier_score",
        "validation_threshold",
        "reference_pr_auc",
        "reference_roc_auc",
        "reference_balanced_accuracy",
        "reference_f1",
        "reference_precision",
        "reference_recall",
        "reference_brier_score",
        "reference_threshold",
    ]
    for k in required_metric_keys:
        assert k in metrics, f"Missing metric key {k}"
        assert isinstance(metrics[k], (int, float)), f"Metric {k} must be numeric"

    # 6. Verify fairness_report.json structure
    with open(output_dir / "fairness_report.json", "r", encoding="utf-8") as f:
        fairness = json.load(f)
    assert "validation_fairness" in fairness
    assert "reference_fairness" in fairness
    assert "by_race" in fairness["validation_fairness"]
    assert "by_gender" in fairness["validation_fairness"]
    assert "subgroups" in fairness["validation_fairness"]["by_race"]
    assert "disparities" in fairness["validation_fairness"]["by_race"]

    # 7. Verify model_insights.json
    with open(output_dir / "model_insights.json", "r", encoding="utf-8") as f:
        insights = json.load(f)
    assert "top_positive_risk_factors" in insights
    assert "top_protective_factors" in insights
    assert "intercept" in insights

    # 8. Load fitted pipeline and test single clinical record inference with unseen categories
    pipeline = joblib.load(output_dir / "model.joblib")
    clinical_record = pd.DataFrame(
        [
            {
                "time_in_hospital": 4,
                "num_lab_procedures": 45,
                "num_procedures": 1,
                "num_medications": 15,
                "number_diagnoses": 8,
                "gender": "Female",
                "age": "Over 60 years",
                "admission_source_id": "Emergency",
                "medical_specialty": "UnseenExoticSpecialty",  # Unseen category to test OHE ignore
                "primary_diagnosis": "Diabetes",
                "max_glu_serum": "None",
                "A1Cresult": ">8",
                "insulin": "Steady",
                "change": "Ch",
                "diabetesMed": "Yes",
                "medicare": 1,
                "medicaid": 0,
                "had_emergency": 0,
                "had_inpatient_days": 1,
                "had_outpatient_days": 0,
            }
        ]
    )

    pred = pipeline.predict(clinical_record)
    proba = pipeline.predict_proba(clinical_record)
    assert pred[0] in (0, 1)
    assert proba.shape == (1, 2)
    assert np.isclose(np.sum(proba[0]), 1.0)

    # 9. Test tar.gz extraction and Model Packager discovery
    extract_dir = tmp_path / "packager_extract"
    extract_dir.mkdir()
    with tarfile.open(output_dir / "model.tar.gz", "r:gz") as tar:
        tar.extractall(extract_dir)

    discovered_model = model_packager_tasks.find_supported_model_file(
        extract_dir, flavor="sklearn"
    )
    assert discovered_model.name == "model.joblib"

    # 10. Test MLflow packaging round-trip if MLflow is available
    if MLFLOW_AVAILABLE:
        loaded_model = model_packager_core.load_model(
            discovered_model, flavor="sklearn"
        )
        mlflow_output = tmp_path / "mlflow_export"
        mlflow.sklearn.save_model(sk_model=loaded_model, path=str(mlflow_output))
        pyfunc_model = mlflow.pyfunc.load_model(str(mlflow_output))
        pyfunc_pred = pyfunc_model.predict(clinical_record)
        assert len(pyfunc_pred) == 1

    print("\n[SUCCESS] All Diabetes Readmission Logistic Regression tests passed!")


def test_diabetes_train_pipeline_and_artifact_generation(tmp_path):
    """Pytest entrypoint to verify end-to-end Diabetes Logistic Regression training and artifact packaging."""
    run_pipeline_verification(tmp_path)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as temp_dir:
        run_pipeline_verification(Path(temp_dir))
