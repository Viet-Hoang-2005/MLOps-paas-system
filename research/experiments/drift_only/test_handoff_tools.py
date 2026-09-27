"""Check scoring failure modes that could otherwise invalidate replay evidence."""
import contextlib
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest

from handoff_tools import score


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "manifest.json").write_text(json.dumps({"windows": [
            {"window_id": "example", "labels": "labels.csv"}]}))
        self.write_csv("labels.csv", [
            {"y_binary": y, "family": family, "expected_pred_binary": y}
            for y, family in [(0, "BENIGN"), (0, "BENIGN"), (1, "DDoS"), (1, "PortScan")]])
        # One false positive and one missed PortScan; deliberately shuffled.
        self.responses = [{"window_id": "example", "replay_index": i,
                           "prediction_id": f"prediction-{i}", "pred_binary": pred}
                          for i, pred in [(3, 0), (0, 0), (2, 1), (1, 1)]]

    def write_csv(self, name, rows):
        with (self.root / name).open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    def run_score(self):
        self.write_csv("responses.csv", self.responses)
        with contextlib.redirect_stdout(io.StringIO()):
            score(self.root, "example", self.root / "responses.csv", self.root / "score.json")
        return json.loads((self.root / "score.json").read_text())

    def test_shuffled_responses_are_joined_by_identity(self):
        result = self.run_score()
        self.assertEqual([result[k] for k in ("tn", "fp", "fn", "tp")], [1, 1, 1, 1])
        self.assertEqual(result["macro_f1"], 0.5)
        self.assertEqual(result["prediction_mismatches"], 2)
        self.assertEqual(result["families"]["PortScan"]["missed_attack"], 1)

    def test_missing_response_rejected(self):
        self.responses.pop()
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            self.run_score()

    def test_duplicate_replay_index_rejected(self):
        self.responses[1]["replay_index"] = 3
        with self.assertRaisesRegex(ValueError, "Duplicate replay_index"):
            self.run_score()

    def test_duplicate_prediction_id_rejected(self):
        self.responses[1]["prediction_id"] = "prediction-3"
        with self.assertRaisesRegex(ValueError, "prediction_id"):
            self.run_score()

    def test_other_window_rejected(self):
        self.responses[0]["window_id"] = "other"
        with self.assertRaisesRegex(ValueError, "Mixed windows"):
            self.run_score()

    def test_multiclass_label_rejected(self):
        self.responses[0]["pred_binary"] = 2
        with self.assertRaisesRegex(ValueError, "0 or 1"):
            self.run_score()

    def test_output_not_overwritten(self):
        self.run_score()
        with self.assertRaises(FileExistsError):
            self.run_score()


if __name__ == "__main__":
    unittest.main()
