"""Unit tests for Kaggle BAF MLP training script and artifact generation."""

import importlib.util
import json
import sys
import tarfile
import tempfile
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
import torch

TORCH_AVAILABLE = True


def load_modules():
    """Dynamically import train.py and model-packager tasks.py."""
    kaggle_train_path = Path(__file__).parent / "train.py"
    spec_train = importlib.util.spec_from_file_location("baf_train", kaggle_train_path)
    baf_train = importlib.util.module_from_spec(spec_train)
    spec_train.loader.exec_module(baf_train)

    repo_root = Path(__file__).resolve().parents[4]
    packager_root = repo_root / "services" / "model-packager"
    if str(packager_root) not in sys.path:
        sys.path.insert(0, str(packager_root))

    packager_tasks_path = packager_root / "src" / "tasks.py"
    spec_packager = importlib.util.spec_from_file_location(
        "model_packager_tasks", packager_tasks_path
    )
    model_packager_tasks = importlib.util.module_from_spec(spec_packager)
    spec_packager.loader.exec_module(model_packager_tasks)

    return baf_train, model_packager_tasks


def create_synthetic_baf_csv(file_path: Path, num_rows_per_month: int = 50) -> Path:
    """Create a small synthetic CSV matching Base.csv schema for all months 0-7."""
    rng = np.random.RandomState(42)
    rows = []
    for month in range(8):
        for _ in range(num_rows_per_month):
            row = {
                "fraud_bool": int(rng.rand() < 0.1),
                "income": float(rng.uniform(0.1, 0.9)),
                "name_email_similarity": float(rng.uniform(0.0, 1.0)),
                "prev_address_months_count": int(rng.choice([-1, 10, 24, 60])),
                "current_address_months_count": int(rng.randint(0, 120)),
                "customer_age": int(rng.randint(18, 80)),
                "days_since_request": float(rng.uniform(0.0, 30.0)),
                "intended_balcon_amount": float(rng.uniform(-1.0, 100.0)),
                "payment_type": str(rng.choice(["AA", "AB", "AC", "AD", "AE"])),
                "zip_count_4w": int(rng.randint(100, 5000)),
                "velocity_6h": float(rng.uniform(0.0, 10000.0)),
                "velocity_24h": float(rng.uniform(0.0, 10000.0)),
                "velocity_4w": float(rng.uniform(0.0, 10000.0)),
                "bank_branch_count_8w": int(rng.randint(0, 100)),
                "date_of_birth_distinct_emails_4w": int(rng.randint(0, 20)),
                "employment_status": str(
                    rng.choice(["CA", "CB", "CC", "CD", "CE", "CF", "CG"])
                ),
                "credit_risk_score": int(rng.randint(50, 300)),
                "email_is_free": int(rng.choice([0, 1])),
                "housing_status": str(
                    rng.choice(["BA", "BB", "BC", "BD", "BE", "BF", "BG"])
                ),
                "phone_home_valid": int(rng.choice([0, 1])),
                "phone_mobile_valid": int(rng.choice([0, 1])),
                "bank_months_count": int(rng.choice([-1, 5, 12, 36])),
                "has_other_cards": int(rng.choice([0, 1])),
                "proposed_credit_limit": float(rng.uniform(200.0, 2000.0)),
                "foreign_request": int(rng.choice([0, 1])),
                "source": str(rng.choice(["INTERNET", "TELEAPP"])),
                "session_length_in_minutes": float(rng.uniform(1.0, 60.0)),
                "device_os": str(
                    rng.choice(["windows", "linux", "macintosh", "x11", "other"])
                ),
                "keep_alive_session": int(rng.choice([0, 1])),
                "device_distinct_emails_8w": int(rng.randint(0, 5)),
                "device_fraud_count": 0,
                "month": month,
            }
            rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(file_path, index=False)
    return file_path


def run_pipeline_verification(tmp_path: Path) -> None:
    """Core logic to verify training pipeline and artifact generation."""
    baf_train, model_packager_tasks = load_modules()

    csv_path = tmp_path / "synthetic_base.csv"
    create_synthetic_baf_csv(csv_path, num_rows_per_month=40)
    output_dir = tmp_path / "artifact_output"

    test_args = [
        "train.py",
        "--data-path",
        str(csv_path),
        "--output-dir",
        str(output_dir),
        "--device",
        "cpu",
        "--seed",
        "42",
        "--batch-size",
        "32",
        "--epochs",
        "2",
        "--patience",
        "2",
        "--hidden-dim-1",
        "32",
        "--hidden-dim-2",
        "16",
        "--train-months",
        "0,1,2,3",
        "--val-months",
        "4",
        "--ref-months",
        "5",
    ]
    old_argv = sys.argv
    sys.argv = test_args
    try:
        baf_train.main()
    finally:
        sys.argv = old_argv

    # Verify all expected files exist
    expected_files = [
        "model.pt",
        "preprocessor.joblib",
        "training_config.json",
        "data_contract.json",
        "metrics.json",
        "split_manifest.json",
        "artifact_manifest.json",
        "model.tar.gz",
    ]
    for file_name in expected_files:
        file_path = output_dir / file_name
        assert file_path.exists(), f"Expected artifact {file_name} missing from output!"

    # 1. Verify model.pt is loadable with standard torch.load without custom class
    loaded_model = torch.load(
        output_dir / "model.pt", map_location="cpu", weights_only=False
    )
    assert isinstance(loaded_model, torch.nn.Sequential)

    # 2. Verify preprocessor.joblib can transform new raw records
    preprocessor = joblib.load(output_dir / "preprocessor.joblib")
    test_df = pd.read_csv(csv_path, nrows=10)
    feature_cols = [c for c in test_df.columns if c not in ("fraud_bool", "month")]
    transformed_features = preprocessor.transform(test_df[feature_cols]).astype(
        np.float32
    )
    assert transformed_features.shape[0] == 10
    assert transformed_features.shape[1] == 30

    # 3. Verify forward pass of loaded model on preprocessed features
    with torch.no_grad():
        tensor_x = torch.from_numpy(transformed_features)
        logits = loaded_model(tensor_x)
        assert logits.shape == (10, 1)
        probs = torch.sigmoid(logits).numpy().ravel()
        assert np.all((probs >= 0.0) & (probs <= 1.0))

    # 4. Verify split_manifest strictly preserves months 6 and 7
    with open(output_dir / "split_manifest.json", "r", encoding="utf-8") as f:
        split_manifest = json.load(f)
    assert split_manifest["train_months"] == [0, 1, 2, 3]
    assert split_manifest["validation_months"] == [4]
    assert split_manifest["reference_months"] == [5]
    assert split_manifest["excluded_continuous_training_months"] == [6, 7]

    # 5. Verify metrics.json contains optimal threshold and valid scores
    with open(output_dir / "metrics.json", "r", encoding="utf-8") as f:
        metrics = json.load(f)
    assert "best_threshold" in metrics
    assert "validation_metrics" in metrics
    assert "pr_auc" in metrics["validation_metrics"]
    assert "f1" in metrics["validation_metrics"]
    assert "brier_score" in metrics["validation_metrics"]

    # 6. Verify model.tar.gz can be extracted and recognized by Model Packager
    extract_dir = tmp_path / "packager_extract"
    extract_dir.mkdir()
    with tarfile.open(output_dir / "model.tar.gz", "r:gz") as tar:
        tar.extractall(extract_dir)

    discovered_model = model_packager_tasks.find_supported_model_file(
        extract_dir, flavor="pytorch"
    )
    assert discovered_model.name == "model.pt"
    print(
        "\n[SUCCESS] All BAF MLP training pipeline and artifact verification tests passed!"
    )


@pytest.mark.skipif(
    not TORCH_AVAILABLE,
    reason="PyTorch DLL unavailable on host OS (supported in Docker / Kaggle)",
)
def test_baf_train_pipeline_and_artifact_generation(tmp_path):
    """Pytest entrypoint to verify end-to-end BAF MLP training and artifact packaging."""
    run_pipeline_verification(tmp_path)


if __name__ == "__main__":
    if not TORCH_AVAILABLE:
        print("[ERROR] PyTorch is not available in this Python environment.")
        sys.exit(1)
    with tempfile.TemporaryDirectory() as temp_dir:
        run_pipeline_verification(Path(temp_dir))
