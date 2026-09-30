"""Match version-scoped production records to one frozen replay window.

The UI replay does not expose prediction IDs, so this audit joins records by
the exact IEEE-754 feature values. It rejects ambiguous or incomplete windows.
"""

import argparse
import csv
import json
import math
from pathlib import Path


def feature_key(features, names):
    if set(features) != set(names):
        raise ValueError("Record feature set differs from the frozen 52-feature schema")
    values = []
    for name in names:
        value = float(features[name])
        if not math.isfinite(value):
            raise ValueError(f"Non-finite feature: {name}")
        values.append(value.hex())
    return tuple(values)


def audit(bundle, window, records_path, version_id, ui_predictions_hex=None):
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    entry = next((w for w in manifest["windows"] if w["window_id"] == window), None)
    if entry is None:
        raise ValueError(f"Unknown window: {window}")
    names = manifest["features"]
    with (bundle / entry["inputs"]).open(newline="", encoding="utf-8") as stream:
        inputs = list(csv.DictReader(stream))
    if len(inputs) != entry["n"]:
        raise ValueError("Input row count differs from manifest")
    index = {}
    for i, row in enumerate(inputs):
        key = feature_key(row, names)
        if key in index:
            raise ValueError("Duplicate input feature vector; ID mapping is ambiguous")
        index[key] = i

    records = [json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines() if line]
    if len(records) != len(inputs):
        raise ValueError(f"Expected {len(inputs)} version-scoped records, got {len(records)}")
    ui_predictions = None
    if ui_predictions_hex is not None:
        packed = bytes.fromhex(ui_predictions_hex.read_text(encoding="ascii").strip())
        if len(packed) != (len(inputs) + 7) // 8:
            raise ValueError("UI prediction bitstream length differs from input rows")
        bits = [(byte >> shift) & 1 for byte in packed for shift in range(7, -1, -1)]
        if any(bits[len(inputs):]):
            raise ValueError("Nonzero padding in UI prediction bitstream")
        ui_predictions = bits[:len(inputs)]
    matched = {}
    ids = set()
    request_ids = set()
    for record in records:
        if record.get("version_id") != version_id:
            raise ValueError("Record belongs to a different model version")
        prediction_id = str(record.get("prediction_id", ""))
        if not prediction_id or prediction_id in ids:
            raise ValueError("Missing or duplicate prediction ID")
        ids.add(prediction_id)
        request_id = str(record.get("request_id", ""))
        if not request_id or request_id in request_ids:
            raise ValueError("Missing or duplicate request ID")
        request_ids.add(request_id)
        key = feature_key(record["features"], names)
        if key not in index:
            raise ValueError("Production record does not belong to this window")
        i = index[key]
        if i in matched:
            raise ValueError("Duplicate production feature vector")
        prediction = str(record["prediction"])
        if ui_predictions is not None:
            ui_prediction = str(ui_predictions[i])
            if prediction != ui_prediction and not (prediction == "" and ui_prediction == "0"):
                raise ValueError("UI and stored prediction disagree")
            record["audited_prediction"] = ui_prediction
        elif prediction in {"0", "1"}:
            record["audited_prediction"] = prediction
        else:
            raise ValueError("Production prediction is not binary 0/1")
        matched[i] = record
    if set(matched) != set(range(len(inputs))):
        raise ValueError("Incomplete replay-index coverage")

    output = [
        {"window_id": window, "replay_index": i,
         "prediction_id": matched[i]["prediction_id"],
         "pred_binary": matched[i]["audited_prediction"]}
        for i in range(len(inputs))
    ]
    summary = {
        "window_id": window,
        "version_id": version_id,
        "input_rows": len(inputs),
        "matched_records": len(records),
        "unique_prediction_ids": len(ids),
        "unique_request_ids": len(request_ids),
        "mapping_method": "exact IEEE-754 feature-vector match; browser UI does not send handoff request_id",
        "prediction_source": "UI console with DB cross-check" if ui_predictions is not None else "DB production_predictionrecord",
        "legacy_blank_zero_records": sum(item["prediction"] == "" for item in records),
        "observed_first": min(item["observed_at"] for item in records),
        "observed_last": max(item["observed_at"] for item in records),
    }
    return output, summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--window", required=True)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--version-id", required=True)
    parser.add_argument("--ui-predictions-hex", type=Path)
    parser.add_argument("--responses", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    responses, summary = audit(args.bundle, args.window, args.records, args.version_id, args.ui_predictions_hex)
    if args.responses.exists() or args.audit.exists():
        raise FileExistsError("Refusing to overwrite an existing audit artifact")
    with args.responses.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["window_id", "replay_index", "prediction_id", "pred_binary"])
        writer.writeheader()
        writer.writerows(responses)
    args.audit.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
