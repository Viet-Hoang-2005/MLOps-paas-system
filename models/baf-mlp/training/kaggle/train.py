"""Baseline PyTorch MLP training script for Bank Account Fraud (BAF).

This script implements the graduation thesis training contract for the primary
BAF workload:
  - Loads Base.csv, partitions strictly by month:
      * Months 0-3: Training partition
      * Month 4: Validation & threshold tuning partition
      * Month 5: Reference baseline partition
      * Months 6-7: EXCLUDED (preserved for Continuous Training replay evaluation)
  - Fits preprocessing (imputation + scaling + ordinal encoding) ONLY on train partition
  - Trains a pure torch.nn.Sequential MLP with BCEWithLogitsLoss (weighted for class imbalance)
  - Early stops based on validation PR-AUC (Average Precision)
  - Optimizes decision threshold on Month 4 to maximize F1 score
  - Evaluates baseline performance on Month 5 reference partition
  - Exports a standard artifact archive (model.tar.gz) recognized by Model Packager
"""

import argparse
import copy
import hashlib
import json
import os
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
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder, StandardScaler

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

CATEGORICAL_COLUMNS = [
    "payment_type",
    "employment_status",
    "housing_status",
    "source",
    "device_os",
]

TARGET_COLUMN = "fraud_bool"
SPLIT_COLUMN = "month"
RESERVED_CT_MONTHS = [6, 7]


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
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False


def select_device(requested_device: str) -> torch.device:
    """Resolve the computing device."""
    if requested_device.lower() == "auto":
        device_str = "cuda" if torch.cuda.is_available() else "cpu"
    else:
        device_str = requested_device
    device = torch.device(device_str)
    print(f"[Device] Using computing device: {device}")
    return device


def parse_month_list(months_str: str) -> list[int]:
    """Parse comma-separated month strings."""
    return [int(item.strip()) for item in months_str.split(",") if item.strip()]


def build_preprocessor(
    numeric_cols: list[str], categorical_cols: list[str]
) -> ColumnTransformer:
    """Build sklearn ColumnTransformer for tabular preprocessing."""
    numeric_pipe = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )

    categorical_pipe = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="constant", fill_value="missing")),
            (
                "encoder",
                OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1),
            ),
        ]
    )

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_pipe, numeric_cols),
            ("cat", categorical_pipe, categorical_cols),
        ],
        remainder="drop",
    )
    return preprocessor


def build_mlp_model(
    input_dim: int, hidden_dim_1: int, hidden_dim_2: int, dropout: float
) -> nn.Sequential:
    """Construct pure nn.Sequential MLP.

    Using standard built-in PyTorch modules ensures torch.save/torch.load
    unpickles cleanly in Model Packager without requiring custom class code.
    """
    return nn.Sequential(
        nn.Linear(input_dim, hidden_dim_1),
        nn.ReLU(),
        nn.Dropout(dropout),
        nn.Linear(hidden_dim_1, hidden_dim_2),
        nn.ReLU(),
        nn.Dropout(dropout),
        nn.Linear(hidden_dim_2, 1),
    )


def evaluate_model(
    model: nn.Module,
    dataloader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
) -> tuple[float, np.ndarray, np.ndarray]:
    """Run model inference over a DataLoader and return loss, probabilities, and labels."""
    model.eval()
    total_loss = 0.0
    total_samples = 0
    all_probs = []
    all_labels = []

    with torch.no_grad():
        for features, targets in dataloader:
            features = features.to(device)
            targets = targets.to(device)
            logits = model(features)
            loss = criterion(logits, targets)

            batch_size = targets.size(0)
            total_loss += loss.item() * batch_size
            total_samples += batch_size

            probs = torch.sigmoid(logits).cpu().numpy().ravel()
            all_probs.append(probs)
            all_labels.append(targets.cpu().numpy().ravel())

    avg_loss = total_loss / max(total_samples, 1)
    y_probs = np.concatenate(all_probs)
    y_true = np.concatenate(all_labels)
    return avg_loss, y_probs, y_true


def find_optimal_threshold(
    y_true: np.ndarray, y_probs: np.ndarray
) -> tuple[float, float]:
    """Search for the decision threshold that maximizes F1 score on validation set."""
    best_thresh = 0.5
    best_f1 = -1.0
    for thresh in np.linspace(0.01, 0.99, 99):
        preds = (y_probs >= thresh).astype(int)
        score = f1_score(y_true, preds, zero_division=0)
        if score > best_f1:
            best_f1 = float(score)
            best_thresh = float(thresh)
    return round(best_thresh, 4), round(best_f1, 6)


def compute_metrics(
    y_true: np.ndarray, y_probs: np.ndarray, threshold: float
) -> dict[str, float]:
    """Compute comprehensive classification and calibration metrics."""
    preds = (y_probs >= threshold).astype(int)
    pr_auc = float(average_precision_score(y_true, y_probs))
    try:
        roc_auc = float(roc_auc_score(y_true, y_probs))
    except ValueError:
        roc_auc = 0.5

    f1 = float(f1_score(y_true, preds, zero_division=0))
    prec = float(precision_score(y_true, preds, zero_division=0))
    rec = float(recall_score(y_true, preds, zero_division=0))
    brier = float(brier_score_loss(y_true, y_probs))

    return {
        "pr_auc": round(pr_auc, 6),
        "roc_auc": round(roc_auc, 6),
        "f1": round(f1, 6),
        "precision": round(prec, 6),
        "recall": round(rec, 6),
        "brier_score": round(brier, 6),
        "threshold": round(threshold, 4),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Train baseline BAF PyTorch MLP on Kaggle."
    )
    parser.add_argument(
        "--data-path",
        type=str,
        default="/kaggle/input/bank-account-fraud-dataset-neurips-2022/Base.csv",
        help="Path to Base.csv dataset.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="/kaggle/working/baf-mlp-artifact",
        help="Output directory for artifacts.",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        help="Execution device ('auto', 'cuda', 'cpu').",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument("--batch-size", type=int, default=2048, help="Batch size.")
    parser.add_argument("--epochs", type=int, default=20, help="Maximum epochs.")
    parser.add_argument("--lr", type=float, default=1e-3, help="Learning rate.")
    parser.add_argument(
        "--weight-decay", type=float, default=1e-4, help="AdamW weight decay."
    )
    parser.add_argument(
        "--patience", type=int, default=5, help="Early stopping patience."
    )
    parser.add_argument(
        "--hidden-dim-1", type=int, default=128, help="First hidden layer dimension."
    )
    parser.add_argument(
        "--hidden-dim-2", type=int, default=64, help="Second hidden layer dimension."
    )
    parser.add_argument(
        "--dropout", type=float, default=0.2, help="Dropout probability."
    )
    parser.add_argument(
        "--train-months", type=str, default="0,1,2,3", help="Training months."
    )
    parser.add_argument(
        "--val-months", type=str, default="4", help="Validation months."
    )
    parser.add_argument(
        "--ref-months", type=str, default="5", help="Reference manifest months."
    )
    args = parser.parse_args()

    set_seed(args.seed)
    device = select_device(args.device)

    data_path = Path(args.data_path)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    train_months = parse_month_list(args.train_months)
    val_months = parse_month_list(args.val_months)
    ref_months = parse_month_list(args.ref_months)

    print(
        f"[Config] Train months: {train_months} | Val months: {val_months} | Ref months: {ref_months}"
    )
    print(f"[Config] Reserved for Continuous Training replay: {RESERVED_CT_MONTHS}")

    # Check that reserved months are strictly excluded
    used_months = set(train_months + val_months + ref_months)
    for reserved in RESERVED_CT_MONTHS:
        if reserved in used_months:
            raise ValueError(
                f"Month {reserved} is strictly reserved for CT replay and cannot be used in baseline training!"
            )

    if not data_path.exists():
        raise FileNotFoundError(f"Dataset not found at: {data_path}")

    start_time = time.time()
    print(f"[Data] Reading dataset from {data_path}...")
    df = pd.read_csv(data_path)

    if TARGET_COLUMN not in df.columns:
        raise ValueError(f"Target column '{TARGET_COLUMN}' not found in {data_path}.")
    if SPLIT_COLUMN not in df.columns:
        raise ValueError(f"Temporal column '{SPLIT_COLUMN}' not found in {data_path}.")

    feature_cols = [
        col for col in df.columns if col not in (TARGET_COLUMN, SPLIT_COLUMN)
    ]
    cat_cols = [
        col
        for col in feature_cols
        if col in CATEGORICAL_COLUMNS or df[col].dtype == "object"
    ]
    num_cols = [col for col in feature_cols if col not in cat_cols]

    print(
        f"[Schema] Total features: {len(feature_cols)} ({len(num_cols)} numeric, {len(cat_cols)} categorical)"
    )

    train_mask = df[SPLIT_COLUMN].isin(train_months)
    val_mask = df[SPLIT_COLUMN].isin(val_months)
    ref_mask = df[SPLIT_COLUMN].isin(ref_months)

    df_train = df[train_mask]
    df_val = df[val_mask]
    df_ref = df[ref_mask]

    print(
        f"[Split] Train rows: {len(df_train)} (fraud: {df_train[TARGET_COLUMN].sum()}, rate: {df_train[TARGET_COLUMN].mean():.4f})"
    )
    print(
        f"[Split] Val rows:   {len(df_val)} (fraud: {df_val[TARGET_COLUMN].sum()}, rate: {df_val[TARGET_COLUMN].mean():.4f})"
    )
    print(
        f"[Split] Ref rows:   {len(df_ref)} (fraud: {df_ref[TARGET_COLUMN].sum()}, rate: {df_ref[TARGET_COLUMN].mean():.4f})"
    )

    # Fit Preprocessing ONLY on training data
    print("[Preprocessing] Fitting ColumnTransformer strictly on training partition...")
    preprocessor = build_preprocessor(num_cols, cat_cols)
    X_train_trans = preprocessor.fit_transform(df_train[feature_cols]).astype(
        np.float32
    )
    y_train = df_train[TARGET_COLUMN].values.astype(np.float32)

    X_val_trans = preprocessor.transform(df_val[feature_cols]).astype(np.float32)
    y_val = df_val[TARGET_COLUMN].values.astype(np.float32)

    X_ref_trans = preprocessor.transform(df_ref[feature_cols]).astype(np.float32)
    y_ref = df_ref[TARGET_COLUMN].values.astype(np.float32)

    input_dim = X_train_trans.shape[1]
    print(f"[Features] Transformed feature matrix width: {input_dim}")

    # Construct Datasets and Loaders
    train_dataset = TensorDataset(
        torch.from_numpy(X_train_trans), torch.from_numpy(y_train).unsqueeze(1)
    )
    val_dataset = TensorDataset(
        torch.from_numpy(X_val_trans), torch.from_numpy(y_val).unsqueeze(1)
    )
    ref_dataset = TensorDataset(
        torch.from_numpy(X_ref_trans), torch.from_numpy(y_ref).unsqueeze(1)
    )

    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size * 2, shuffle=False)
    ref_loader = DataLoader(ref_dataset, batch_size=args.batch_size * 2, shuffle=False)

    # Class imbalance weighting
    pos_count = int(y_train.sum())
    neg_count = len(y_train) - pos_count
    pos_weight_val = neg_count / max(pos_count, 1)
    pos_weight = torch.tensor([pos_weight_val], dtype=torch.float32).to(device)
    print(
        f"[Loss] Extreme imbalance weighting: pos_weight = {pos_weight_val:.2f} (positive cases: {pos_count})"
    )

    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    model = build_mlp_model(
        input_dim, args.hidden_dim_1, args.hidden_dim_2, args.dropout
    ).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=args.lr, weight_decay=args.weight_decay
    )

    # Training Loop
    print(
        f"[Training] Starting training for up to {args.epochs} epochs with patience {args.patience}..."
    )
    best_val_pr_auc = -1.0
    best_weights = copy.deepcopy(model.state_dict())
    patience_counter = 0
    training_history = []

    for epoch in range(1, args.epochs + 1):
        model.train()
        train_loss = 0.0
        train_samples = 0

        for batch_x, batch_y in train_loader:
            batch_x = batch_x.to(device)
            batch_y = batch_y.to(device)

            optimizer.zero_grad()
            logits = model(batch_x)
            loss = criterion(logits, batch_y)
            loss.backward()
            optimizer.step()

            batch_size = batch_y.size(0)
            train_loss += loss.item() * batch_size
            train_samples += batch_size

        epoch_train_loss = train_loss / max(train_samples, 1)
        val_loss, val_probs, val_true = evaluate_model(
            model, val_loader, criterion, device
        )
        val_pr_auc = average_precision_score(val_true, val_probs)

        print(
            f"Epoch {epoch:02d}/{args.epochs:02d} | "
            f"Train Loss: {epoch_train_loss:.4f} | "
            f"Val Loss: {val_loss:.4f} | "
            f"Val PR-AUC: {val_pr_auc:.5f}"
        )

        training_history.append(
            {
                "epoch": epoch,
                "train_loss": round(epoch_train_loss, 5),
                "val_loss": round(val_loss, 5),
                "val_pr_auc": round(float(val_pr_auc), 5),
            }
        )

        if val_pr_auc > best_val_pr_auc:
            best_val_pr_auc = float(val_pr_auc)
            best_weights = copy.deepcopy(model.state_dict())
            patience_counter = 0
            print(
                f"  --> [Saved] Best model improved to PR-AUC = {best_val_pr_auc:.5f}"
            )
        else:
            patience_counter += 1
            if patience_counter >= args.patience:
                print(
                    f"[Early Stopping] Patience of {args.patience} reached at epoch {epoch}."
                )
                break

    # Restore best weights and move model and criterion to CPU for deployment and evaluation
    model.load_state_dict(best_weights)
    model.eval()
    model.cpu()
    criterion.to(torch.device("cpu"))

    # Threshold optimization on Validation (Month 4)
    _, val_probs, val_true = evaluate_model(
        model, val_loader, criterion, torch.device("cpu")
    )
    best_threshold, best_f1 = find_optimal_threshold(val_true, val_probs)
    print(
        f"[Threshold] Optimized threshold on Month 4: {best_threshold:.4f} (Validation F1: {best_f1:.5f})"
    )

    val_metrics = compute_metrics(val_true, val_probs, best_threshold)
    print(f"[Metrics] Validation (Month 4): {val_metrics}")

    # Evaluation on Reference (Month 5)
    _, ref_probs, ref_true = evaluate_model(
        model, ref_loader, criterion, torch.device("cpu")
    )
    ref_metrics = compute_metrics(ref_true, ref_probs, best_threshold)
    print(f"[Metrics] Reference (Month 5): {ref_metrics}")

    # 1. Save model.pt
    model_pt_path = output_dir / "model.pt"
    torch.save(model, model_pt_path)
    print(f"[Artifact] Saved PyTorch model to {model_pt_path}")

    # 2. Save preprocessor.joblib
    preprocessor_path = output_dir / "preprocessor.joblib"
    joblib.dump(preprocessor, preprocessor_path)
    print(f"[Artifact] Saved preprocessor to {preprocessor_path}")

    # 3. Save training_config.json
    config_payload = {
        "workload": "bank_account_fraud_mlp",
        "flavor": "pytorch",
        "seed": args.seed,
        "device": str(device),
        "hyperparameters": {
            "batch_size": args.batch_size,
            "max_epochs": args.epochs,
            "learning_rate": args.lr,
            "weight_decay": args.weight_decay,
            "early_stopping_patience": args.patience,
            "hidden_dim_1": args.hidden_dim_1,
            "hidden_dim_2": args.hidden_dim_2,
            "dropout": args.dropout,
            "loss": "BCEWithLogitsLoss",
            "pos_weight": round(pos_weight_val, 4),
        },
        "training_history": training_history,
        "elapsed_seconds": round(time.time() - start_time, 2),
    }
    config_path = output_dir / "training_config.json"
    config_path.write_text(json.dumps(config_payload, indent=2), encoding="utf-8")

    # 4. Save data_contract.json
    contract_payload = {
        "dataset": "Base.csv",
        "target_column": TARGET_COLUMN,
        "split_column": SPLIT_COLUMN,
        "total_features": len(feature_cols),
        "transformed_features_count": input_dim,
        "numeric_features": num_cols,
        "categorical_features": cat_cols,
        "feature_order": feature_cols,
        "preprocessing_strategies": {
            "numeric": "SimpleImputer(median) -> StandardScaler",
            "categorical": "SimpleImputer('missing') -> OrdinalEncoder(unknown_value=-1)",
        },
    }
    contract_path = output_dir / "data_contract.json"
    contract_path.write_text(json.dumps(contract_payload, indent=2), encoding="utf-8")

    # 5. Save metrics.json
    metrics_payload = {
        "best_threshold": best_threshold,
        "validation_metrics": val_metrics,
        "reference_metrics": ref_metrics,
    }
    metrics_path = output_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics_payload, indent=2), encoding="utf-8")

    # 6. Save split_manifest.json
    split_payload = {
        "train_months": train_months,
        "train_samples": len(df_train),
        "train_fraud_count": int(df_train[TARGET_COLUMN].sum()),
        "train_fraud_rate": round(float(df_train[TARGET_COLUMN].mean()), 6),
        "validation_months": val_months,
        "validation_samples": len(df_val),
        "validation_fraud_count": int(df_val[TARGET_COLUMN].sum()),
        "validation_fraud_rate": round(float(df_val[TARGET_COLUMN].mean()), 6),
        "reference_months": ref_months,
        "reference_samples": len(df_ref),
        "reference_fraud_count": int(df_ref[TARGET_COLUMN].sum()),
        "reference_fraud_rate": round(float(df_ref[TARGET_COLUMN].mean()), 6),
        "excluded_continuous_training_months": RESERVED_CT_MONTHS,
    }
    split_path = output_dir / "split_manifest.json"
    split_path.write_text(json.dumps(split_payload, indent=2), encoding="utf-8")

    # 7. Save artifact_manifest.json
    files_to_index = [
        "model.pt",
        "preprocessor.joblib",
        "training_config.json",
        "data_contract.json",
        "metrics.json",
        "split_manifest.json",
    ]
    file_manifests = {}
    for name in files_to_index:
        p = output_dir / name
        file_manifests[name] = {
            "size_bytes": p.stat().st_size,
            "sha256": compute_sha256(p),
        }

    manifest_payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": file_manifests,
        "environment": {
            "python_version": sys.version,
            "platform": platform.platform(),
            "torch_version": torch.__version__,
            "pandas_version": pd.__version__,
            "numpy_version": np.__version__,
            "joblib_version": joblib.__version__,
        },
    }
    manifest_path = output_dir / "artifact_manifest.json"
    manifest_path.write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")

    # 8. Create model.tar.gz archive
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

    # Print METRIC_JSON protocol line for MLOps Training Runner
    protocol_metrics = {
        "pr_auc": val_metrics["pr_auc"],
        "roc_auc": val_metrics["roc_auc"],
        "f1": val_metrics["f1"],
        "precision": val_metrics["precision"],
        "recall": val_metrics["recall"],
        "brier_score": val_metrics["brier_score"],
        "threshold": best_threshold,
    }
    print(f"METRIC_JSON:{json.dumps(protocol_metrics)}")


if __name__ == "__main__":
    main()
