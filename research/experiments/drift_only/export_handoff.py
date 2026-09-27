"""Export frozen NIDS replay inputs. No training, resampling or service calls."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import confusion_matrix, f1_score

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BASE = HERE / "results/run_20260926"
EVID = HERE / "results/evidently_20260927"
SCENARIOS = ("S0", "S1_a85", "S2_r50", "S2_r100")
SEEDS = (42, 123, 456)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False,
                                    allow_nan=False) + "\n", encoding="utf-8")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def feature_hashes(frame):
    a = np.ascontiguousarray(frame.to_numpy(dtype="float64"), dtype="<f8")
    require(np.isfinite(a).all(), "Nonfinite features")
    a[a == 0] = 0.0
    return [hashlib.sha256(row.tobytes()).hexdigest() for row in a]


def export(output, source, with_mlflow):
    require(not output.exists(), f"Output already exists: {output}")
    dataset = json.loads((BASE / "dataset_manifest.json").read_text())
    model_meta = json.loads((BASE / "model_manifest.json").read_text())
    require(sha(source) == dataset["source_sha256"], "Source CSV SHA-256 differs from frozen run")
    require(sha(BASE / "baseline.ubj") == model_meta["model_sha256"], "Model SHA-256 mismatch")
    evid_meta = json.loads((EVID / "manifest.json").read_text())
    require(evid_meta["baseline_membership_sha256"] == sha(BASE / "window_membership.csv.gz"),
            "Evidently replay used different membership")
    for key in ("source_sha256", "model_sha256"):
        expected = dataset[key] if key in dataset else model_meta[key]
        require(evid_meta[key] == expected, f"Evidently {key} mismatch")
    cols = model_meta["features"]
    raw = pd.read_csv(source)
    raw.columns = raw.columns.str.strip()
    if "Label" not in raw and "Attack Type" in raw:
        raw = raw.rename(columns={"Attack Type": "Label"})
    raw["Label"] = raw.Label.astype(str).str.strip()
    require(len(raw) == dataset["raw_rows"], "Raw row count mismatch")
    raw[cols] = raw[cols].astype("float64")
    splits = pd.read_csv(BASE / "split_manifest.csv.gz").set_index("row_id")
    ref = pd.read_csv(BASE / "reference_manifest.csv")
    memberships = pd.read_csv(BASE / "window_membership.csv.gz")
    metrics = pd.read_csv(BASE / "window_metrics.csv").set_index("window_id")
    comparison = pd.read_csv(EVID / "window_comparison.csv").set_index("window_id")
    booster = xgb.Booster()
    booster.load_model(BASE / "baseline.ubj")
    require(booster.feature_names == cols, "Model feature order mismatch")

    def select(ids, split):
        ids = list(map(int, ids))
        require(len(ids) == len(set(ids)), "Duplicate row IDs inside a window")
        frame = raw.iloc[ids][cols].reset_index(drop=True)
        meta = splits.loc[ids]
        require(meta.split.eq(split).all(), f"Unexpected split: expected {split}")
        hashes = feature_hashes(frame)
        require(hashes == meta.feature_sha256.tolist(), "Canonical feature hashes differ")
        require(raw.iloc[ids].Label.tolist() == meta.Label.tolist(), "Labels differ from split manifest")
        return frame, hashes

    reference, ref_hashes = select(ref.row_id, "reference")
    require(len(reference) == 5000, "Reference must have 5000 rows")
    require(ref_hashes == ref.feature_sha256.tolist(), "Reference membership hash mismatch")
    require(raw.iloc[ref.row_id].Label.tolist() == ref.Label.tolist(), "Reference labels mismatch")
    output.mkdir(parents=True)
    for directory in ("model", "reference", "windows", "scoring", "expected", "provenance"):
        (output / directory).mkdir()
    reference.to_csv(output / "reference/features.csv", index=False)
    ref.assign(replay_index=range(len(ref))).to_csv(output / "scoring/reference_labels.csv", index=False)
    shutil.copy2(BASE / "baseline.ubj", output / "model/baseline.ubj")
    dump(output / "model/features.json", cols)
    records, summaries, expected_rows, family_rows = [], [], [], []
    frames = []
    for seed in SEEDS:
        for scenario in SCENARIOS:
            wid = f"{scenario}_n1000_s{seed}"
            ids = memberships.loc[memberships.window_id.eq(wid), "row_id"].tolist()
            require(len(ids) == 1000, f"Wrong count: {wid}")
            frame, hashes = select(ids, "evaluation")
            require(not set(hashes) & set(ref_hashes), f"Reference overlap: {wid}")
            probability = booster.predict(xgb.DMatrix(frame))
            prediction = (probability >= 0.5).astype(int)
            labels = raw.iloc[ids].Label.reset_index(drop=True)
            y = labels.ne("BENIGN").astype(int)
            tn, fp, fn, tp = map(int, confusion_matrix(y, prediction, labels=[0, 1]).ravel())
            observed = dict(tn=tn, fp=fp, fn=fn, tp=tp,
                            attack_recall=tp / (tp + fn), benign_fpr=fp / (fp + tn),
                            macro_f1=float(f1_score(y, prediction, average="macro")))
            old = metrics.loc[wid]
            for key, value in observed.items():
                require(abs(value - float(old[key])) < 1e-12, f"Frozen metric mismatch: {wid} {key}")
            for family in ("BENIGN", "DDoS", "PortScan", "BruteForce", "WebAttacks"):
                mask = labels.eq(family).to_numpy()
                require(int(mask.sum()) == int(old[f"n_{family}"]), f"Family count mismatch: {wid}")
                family_rows.append(dict(window_id=wid, family=family, support=int(mask.sum()),
                                        predicted_attack=int(prediction[mask].sum()),
                                        missed_attack=int((1 - prediction[mask]).sum()) if family != "BENIGN" else None))
            dest = output / "windows" / wid
            dest.mkdir()
            frame.to_csv(dest / "features.csv", index=False)
            # Request identity stays outside HTTP body and outside detector features.
            with (dest / "requests.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
                for i, features in enumerate(frame.to_dict("records")):
                    request = dict(replay_index=i, source_row_id=ids[i],
                                   request_id=f"{wid}-{i:04d}", body={"features": features})
                    stream.write(json.dumps(request, allow_nan=False, separators=(",", ":")) + "\n")
            sidecar = pd.DataFrame(dict(window_id=wid, replay_index=range(1000), source_row_id=ids,
                                        feature_sha256=hashes, family=labels, y_binary=y,
                                        expected_pred_binary=prediction, expected_prob_attack=probability))
            sidecar.to_csv(output / "scoring" / f"{wid}.csv", index=False)
            summaries.append(dict(window_id=wid, scenario=scenario, seed=seed, n=1000, **observed))
            records.append(dict(window_id=wid, scenario=scenario, seed=seed, n=1000,
                                phase="pilot" if seed == 42 else "extension",
                                inputs=f"windows/{wid}/features.csv", requests=f"windows/{wid}/requests.jsonl",
                                labels=f"scoring/{wid}.csv", counts=labels.value_counts().to_dict()))
            expected_rows.append(comparison.loc[[wid]])
            frames.append((wid, frame, prediction))
    pd.DataFrame(summaries).to_csv(output / "expected/window_metrics.csv", index=False)
    pd.DataFrame(family_rows).to_csv(output / "expected/family_counts.csv", index=False)
    pd.concat(expected_rows).to_csv(output / "expected/evidently_windows.csv")
    feature_comparison = pd.read_csv(EVID / "feature_comparison.csv")
    feature_comparison[feature_comparison.window_id.isin([r["window_id"] for r in records])].to_csv(
        output / "expected/evidently_features.csv", index=False)
    mlflow_version = None
    if with_mlflow:
        import mlflow
        from mlflow.models import ModelSignature
        from mlflow.types import ColSpec, Schema
        mlflow_version = mlflow.__version__
        package = output / "model/mlflow"
        mlflow.pyfunc.save_model(
            path=str(package), python_model=str(HERE / "handoff_model.py"),
            artifacts={"baseline": str(BASE / "baseline.ubj")},
            signature=ModelSignature(inputs=Schema([ColSpec("double", c) for c in cols]),
                                     outputs=Schema([ColSpec("long")])),
            pip_requirements=[f"mlflow=={mlflow_version}", f"numpy=={np.__version__}",
                              f"pandas=={pd.__version__}", f"xgboost=={xgb.__version__}"],
        )
        packaged = mlflow.pyfunc.load_model(str(package))
        for wid, frame, predicted in frames:
            require(np.array_equal(packaged.predict(frame), predicted), f"MLflow prediction mismatch: {wid}")
        require(sha(package / "artifacts/baseline.ubj") == model_meta["model_sha256"], "Packaged model changed")
    for filename in ("config.json", "dataset_manifest.json", "model_manifest.json", "environment.json"):
        shutil.copy2(BASE / filename, output / "provenance" / filename)
    shutil.copy2(EVID / "manifest.json", output / "provenance/evidently_manifest.json")
    shutil.copy2(EVID / "environment.lock.txt", output / "provenance/evidently_environment.lock.txt")
    shutil.copy2(HERE / "handoff_tools.py", output / "handoff_tools.py")
    shutil.copy2(HERE / "HANDOFF_VI.md", output / "README_VI.md")
    dump(output / "manifest.json", dict(
        schema_version=1, scope="Frozen offline replay inputs; no service experiment performed",
        source_sha256=dataset["source_sha256"], model_sha256=model_meta["model_sha256"],
        source_row_id="zero-based data row in original source CSV (header excluded)",
        replay_index="zero-based position within exported features.csv",
        reference="reference/features.csv", reference_rows=5000, features=cols,
        prediction_threshold=0.5, evidently_version="0.4.15", dataset_drift_threshold=0.6,
        exploratory_drift_threshold=0.3, windows=records,
        input_files={"reference_manifest": sha(BASE / "reference_manifest.csv"),
                     "window_membership": sha(BASE / "window_membership.csv.gz"),
                     "split_manifest": sha(BASE / "split_manifest.csv.gz")},
        generator_sha256=sha(Path(__file__)),
        environment=dict(python=platform.python_version(), pandas=pd.__version__,
                         numpy=np.__version__, xgboost=xgb.__version__, mlflow=mlflow_version),
        model_packaging="MLflow included and 12000 predictions checked" if with_mlflow else "UBJ only; package before serving",
        sampling="No resampling. Windows may overlap each other; reference is disjoint.",
    ))
    checksums = {p.relative_to(output).as_posix(): sha(p) for p in sorted(output.rglob("*"))
                 if p.is_file() and "__pycache__" not in p.parts}
    dump(output / "checksums.json", checksums)
    subprocess.run([__import__("sys").executable, str(output / "handoff_tools.py"), "verify",
                    "--bundle", str(output)], check=True)
    print(f"Export complete: {output}; 5000 reference rows, 12 windows, 12000 predictions checked")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "data/reference_data.csv")
    parser.add_argument("--output", type=Path, default=HERE / "handoff_exports/nids_replay")
    parser.add_argument("--with-mlflow", action="store_true", help="Package and verify an MLflow model for the serving worker")
    args = parser.parse_args()
    export(args.output.resolve(), args.source.resolve(), args.with_mlflow)
