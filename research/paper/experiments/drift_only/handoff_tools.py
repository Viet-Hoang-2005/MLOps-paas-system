"""Portable bundle verification and scoring. Python standard library only."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import struct
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def inside(root, relative):
    path = (root / relative).resolve()
    require(path.is_relative_to(root.resolve()), f"Path outside bundle: {relative}")
    return path


def row_hash(row, columns):
    values = [float(row[c]) for c in columns]
    require(all(math.isfinite(v) for v in values), "Nonfinite features")
    values = [0.0 if v == 0 else v for v in values]
    return hashlib.sha256(struct.pack("<" + "d" * len(values), *values)).hexdigest()


def verify(bundle):
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    checksums = json.loads((bundle / "checksums.json").read_text(encoding="utf-8"))
    require("manifest.json" in checksums, "Missing manifest checksum")
    for name, digest in checksums.items():
        require(sha(inside(bundle, name)) == digest, f"Checksum mismatch: {name}")
    cols = manifest["features"]
    require(len(cols) == 52 and len(set(cols)) == 52, "Expected 52 unique features")
    require(sha(bundle / "model/baseline.ubj") == manifest["model_sha256"], "Model mismatch")
    reference = read_csv(inside(bundle, manifest["reference"]))
    ref_labels = read_csv(bundle / "scoring/reference_labels.csv")
    require(len(reference) == len(ref_labels) == 5000, "Reference length mismatch")
    require(list(reference[0]) == cols, "Reference feature columns mismatch")
    reference_hashes = [row_hash(row, cols) for row in reference]
    require(reference_hashes == [r["feature_sha256"] for r in ref_labels], "Reference feature mismatch")
    require(len(set(reference_hashes)) == 5000, "Reference duplicates")
    require(len(manifest["windows"]) == 12, "Expected 12 windows")
    seen = set()
    for window in manifest["windows"]:
        wid = window["window_id"]
        require(wid not in seen, f"Duplicate window {wid}")
        seen.add(wid)
        rows = read_csv(inside(bundle, window["inputs"]))
        labels = read_csv(inside(bundle, window["labels"]))
        requests = [json.loads(line) for line in inside(bundle, window["requests"]).read_text(encoding="utf-8").splitlines()]
        require(len(rows) == len(labels) == len(requests) == window["n"] == 1000, f"Count mismatch: {wid}")
        require(list(rows[0]) == cols, f"Unexpected feature columns: {wid}")
        hashes = [row_hash(row, cols) for row in rows]
        require(len(set(hashes)) == 1000 and not set(hashes) & set(reference_hashes), f"Overlap: {wid}")
        require(hashes == [r["feature_sha256"] for r in labels], f"Feature hash mismatch: {wid}")
        require(len({r["source_row_id"] for r in labels}) == 1000, f"Duplicate source rows: {wid}")
        for i, (row, label, request) in enumerate(zip(rows, labels, requests)):
            require(int(label["replay_index"]) == i and label["window_id"] == wid, f"Label order: {wid}")
            require(int(label["y_binary"]) == int(label["family"] != "BENIGN"), f"Label mapping: {wid}")
            require(request["replay_index"] == i and request["source_row_id"] == int(label["source_row_id"]), f"Request identity: {wid}")
            require(request["request_id"] == f"{wid}-{i:04d}", f"Request ID mismatch: {wid}")
            require(set(request["body"]) == {"features"} and list(request["body"]["features"]) == cols,
                    f"Unexpected request fields: {wid}")
            require(all(float(row[c]) == request["body"]["features"][c] for c in cols), f"Request/CSV differ: {wid}")
        counts = {family: sum(r["family"] == family for r in labels) for family in window["counts"]}
        require(counts == window["counts"], f"Family counts differ: {wid}")
    print(f"PASS: {len(checksums)} checksums; 5000 reference rows; 12 windows; 12000 requests; labels separated")


def score(bundle, window_id, responses, output):
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    match = [w for w in manifest["windows"] if w["window_id"] == window_id]
    require(len(match) == 1, f"Unknown window: {window_id}")
    expected = read_csv(inside(bundle, match[0]["labels"]))
    received = read_csv(responses)
    require(len(received) == len(expected), "Incomplete or extra responses; do not score a partial window")
    needed = {"window_id", "replay_index", "prediction_id", "pred_binary"}
    require(received and needed <= set(received[0]), f"Required response columns: {sorted(needed)}")
    indexed, prediction_ids = {}, set()
    for response in received:
        require(response["window_id"] == window_id, "Mixed windows in response file")
        i = int(response["replay_index"])
        require(i not in indexed, "Duplicate replay_index (possible retry)")
        require(response["pred_binary"] in ("0", "1"), "pred_binary must be 0 or 1")
        pid = response["prediction_id"].strip()
        require(pid and pid not in prediction_ids, "Missing/duplicate prediction_id")
        prediction_ids.add(pid)
        indexed[i] = response
    require(set(indexed) == set(range(len(expected))), "Wrong replay_index coverage")
    tn = fp = fn = tp = mismatch = 0
    families = {}
    for i, label in enumerate(expected):
        pred = int(indexed[i]["pred_binary"])
        y = int(label["y_binary"])
        tn += int(y == 0 and pred == 0)
        fp += int(y == 0 and pred == 1)
        fn += int(y == 1 and pred == 0)
        tp += int(y == 1 and pred == 1)
        mismatch += int(pred != int(label["expected_pred_binary"]))
        record = families.setdefault(label["family"], {"support": 0, "predicted_attack": 0})
        record["support"] += 1
        record["predicted_attack"] += pred
    for family, record in families.items():
        record["attack_recall"] = record["predicted_attack"] / record["support"] if family != "BENIGN" else None
        record["missed_attack"] = record["support"] - record["predicted_attack"] if family != "BENIGN" else None
    result = dict(window_id=window_id, n=len(expected), tn=tn, fp=fp, fn=fn, tp=tp,
                  attack_recall=tp / (tp + fn), benign_fpr=fp / (fp + tn),
                  macro_f1=(2 * tp / (2 * tp + fp + fn) + 2 * tn / (2 * tn + fp + fn)) / 2,
                  prediction_mismatches=mismatch, families=families,
                  scope="Scores supplied predictions only; does not verify DB ingestion, detector or callbacks",
                  responses_sha256=sha(responses))
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("verify")
    check.add_argument("--bundle", type=Path, required=True)
    scoring = commands.add_parser("score")
    scoring.add_argument("--bundle", type=Path, required=True)
    scoring.add_argument("--window", required=True)
    scoring.add_argument("--responses", type=Path, required=True)
    scoring.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "verify":
        verify(args.bundle.resolve())
    else:
        verify(args.bundle.resolve())
        score(args.bundle.resolve(), args.window, args.responses, args.output)
