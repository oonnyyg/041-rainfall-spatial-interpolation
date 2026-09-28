import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from rainfall_interp.__main__ import run

CONFIG = {
    "stations": [
        {"id": "S1", "x": 0.0, "y": 0.0},
        {"id": "S2", "x": 3.0, "y": 4.0},
    ],
    "targets": [{"id": "T1", "x": 1.0, "y": 1.0}],
    "dates": ["2024-01-01"],
    "radius": 10.0,
    "max_neighbors": 2,
}


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.config_path = self.dir / "config.json"
        self.obs_path = self.dir / "obs.csv"
        self.out_dir = self.dir / "reports"
        self.config_path.write_text(json.dumps(CONFIG), encoding="utf-8")
        self.obs_path.write_text(
            "date,station_id,rainfall\n"
            "2024-01-01,S1,10\n"
            "2024-01-01,S2,20\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_success_writes_three_reports(self):
        code = run(
            [
                "-c", str(self.config_path),
                "-o", str(self.obs_path),
                "-d", str(self.out_dir),
            ]
        )
        self.assertEqual(code, 0)
        for name in ("target_estimates.csv", "leave_one_out.csv", "summary.json"):
            self.assertTrue((self.out_dir / name).exists())

        with (self.out_dir / "leave_one_out.csv").open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["date"], "2024-01-01")
        self.assertEqual(rows[0]["id"], "S1")
        self.assertEqual(rows[0]["actual"], "10")

        summary = json.loads((self.out_dir / "summary.json").read_text("utf-8"))
        self.assertEqual(summary["overall"]["total"], 2)
        self.assertEqual(summary["overall"]["covered"], 2)
        self.assertIn("2024-01-01", summary["daily"])

    def test_invalid_input_nonzero_and_no_output_dir(self):
        bad_obs = self.dir / "bad.csv"
        bad_obs.write_text(
            "date,station_id,rainfall\n2024-01-01,S1,-5\n", encoding="utf-8"
        )
        code = run(
            [
                "-c", str(self.config_path),
                "-o", str(bad_obs),
                "-d", str(self.out_dir),
            ]
        )
        self.assertEqual(code, 2)
        self.assertFalse(self.out_dir.exists())

    def test_null_metrics_when_no_valid_records(self):
        isolated = {
            "stations": [{"id": "S1", "x": 0.0, "y": 0.0}],
            "targets": [{"id": "T1", "x": 9.0, "y": 0.0}],
            "dates": ["2024-01-01"],
            "radius": 1.0,
            "max_neighbors": 1,
        }
        isolated_path = self.dir / "isolated.json"
        isolated_path.write_text(json.dumps(isolated), encoding="utf-8")
        single_obs = self.dir / "single.csv"
        single_obs.write_text(
            "date,station_id,rainfall\n2024-01-01,S1,10\n", encoding="utf-8"
        )
        code = run(
            [
                "-c", str(isolated_path),
                "-o", str(single_obs),
                "-d", str(self.out_dir),
            ]
        )
        self.assertEqual(code, 0)
        summary = json.loads((self.out_dir / "summary.json").read_text("utf-8"))
        self.assertIsNone(summary["overall"]["mean_error"])
        self.assertIsNone(summary["overall"]["root_mean_squared_error"])
        self.assertEqual(summary["overall"]["total"], 1)
        self.assertEqual(summary["overall"]["covered"], 0)


if __name__ == "__main__":
    unittest.main()
