import json
import tempfile
import unittest
from pathlib import Path

from audit_live_window import audit


class LiveWindowAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "windows" / "example").mkdir(parents=True)
        (self.root / "manifest.json").write_text(json.dumps({
            "features": ["a", "b"],
            "windows": [{"window_id": "example", "inputs": "windows/example/features.csv", "n": 2}],
        }))
        (self.root / "windows/example/features.csv").write_text("a,b\n1.0,2.0\n3.0,4.0\n")
        self.records = self.root / "records.jsonl"
        self.rows = [
            {"version_id": "v", "prediction_id": "p2", "request_id": "r2", "observed_at": "2026-01-01T00:00:02Z", "features": {"a": 3, "b": 4.0}, "prediction": "1"},
            {"version_id": "v", "prediction_id": "p1", "request_id": "r1", "observed_at": "2026-01-01T00:00:01Z", "features": {"a": 1.0, "b": 2}, "prediction": "0"},
        ]

    def write_records(self):
        self.records.write_text("\n".join(json.dumps(row) for row in self.rows) + "\n")

    def test_matches_out_of_order_records_by_exact_features(self):
        self.write_records()
        responses, summary = audit(self.root, "example", self.records, "v")
        self.assertEqual([row["prediction_id"] for row in responses], ["p1", "p2"])
        self.assertEqual(summary["matched_records"], 2)

    def test_rejects_wrong_version(self):
        self.rows[0]["version_id"] = "other"
        self.write_records()
        with self.assertRaisesRegex(ValueError, "different model version"):
            audit(self.root, "example", self.records, "v")

    def test_rejects_missing_request_id(self):
        self.rows[0]["request_id"] = ""
        self.write_records()
        with self.assertRaisesRegex(ValueError, "request ID"):
            audit(self.root, "example", self.records, "v")

    def test_ui_predictions_recover_known_legacy_blank_zero(self):
        self.rows[1]["prediction"] = ""
        self.write_records()
        bitstream = self.root / "ui.hex"
        bitstream.write_text("40")  # UI rows 0,1 followed by zero padding.
        responses, summary = audit(self.root, "example", self.records, "v", bitstream)
        self.assertEqual([row["pred_binary"] for row in responses], ["0", "1"])
        self.assertEqual(summary["legacy_blank_zero_records"], 1)

    def test_ui_db_disagreement_is_rejected(self):
        self.write_records()
        bitstream = self.root / "ui.hex"
        bitstream.write_text("80")
        with self.assertRaisesRegex(ValueError, "UI and stored prediction disagree"):
            audit(self.root, "example", self.records, "v", bitstream)


if __name__ == "__main__":
    unittest.main()
