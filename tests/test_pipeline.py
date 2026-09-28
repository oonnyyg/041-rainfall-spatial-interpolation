from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from rainfall_interp.cli import run
from rainfall_interp.config import load_config
from rainfall_interp.errors import InputError
from rainfall_interp.interpolate import (
    estimate_targets,
    leave_one_out_validation,
)
from rainfall_interp.observations import load_observations
from rainfall_interp.reports import build_summary

ROOT = Path(__file__).resolve().parents[1]


def write_files(tmp: Path, config_text: str, csv_text: str) -> tuple[Path, Path]:
    config_path = tmp / "config.json"
    csv_path = tmp / "obs.csv"
    config_path.write_text(config_text, encoding="utf-8")
    csv_path.write_text(csv_text, encoding="utf-8")
    return config_path, csv_path


BASE_CONFIG = """{
  "stations": [
    {"id": "S1", "x": 0.0, "y": 0.0},
    {"id": "S2", "x": 4.0, "y": 0.0},
    {"id": "S3", "x": 0.0, "y": 3.0}
  ],
  "targets": [
    {"id": "T1", "x": 0.0, "y": 0.0},
    {"id": "T2", "x": 2.0, "y": 0.0}
  ],
  "dates": ["2024-01-01"],
  "radius": 5.0,
  "max_neighbors": 2
}"""

BASE_CSV = (
    "date,station_id,rainfall\n"
    "2024-01-01,S1,10.0\n"
    "2024-01-01,S2,20.0\n"
    "2024-01-01,S3,\n"
)


class InterpolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.config_path, self.csv_path = write_files(
            self.tmp, BASE_CONFIG, BASE_CSV
        )
        self.config = load_config(self.config_path)
        self.observations = load_observations(self.csv_path, self.config)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_zero_distance_average_ignores_neighbor_cap(self) -> None:
        sub_dir = self.tmp / "c2"
        sub_dir.mkdir()
        config_path = sub_dir / "config.json"
        config_text = BASE_CONFIG.replace(
            '"S3", "x": 0.0, "y": 3.0', '"S3", "x": 0.0, "y": 0.0'
        )
        config_path.write_text(config_text, encoding="utf-8")
        csv_text = BASE_CSV.replace("2024-01-01,S3,\n", "2024-01-01,S3,40.0\n")
        self.csv_path.write_text(csv_text, encoding="utf-8")
        config = load_config(config_path)
        observations = load_observations(self.csv_path, config)
        estimates = {
            item.point_id: item
            for item in estimate_targets(config, observations)
        }
        self.assertAlmostEqual(estimates["T1"].prediction, 25.0)
        self.assertEqual(
            sorted(estimates["T1"].participant_ids), ["S1", "S3"]
        )

    def test_inverse_distance_weighting_and_tie_break(self) -> None:
        estimates = {
            item.point_id: item
            for item in estimate_targets(self.config, self.observations)
        }
        estimate = estimates["T2"]
        self.assertTrue(estimate.covered)
        self.assertEqual(estimate.participant_ids, ("S1", "S2"))
        self.assertAlmostEqual(estimate.prediction, 15.0)

    def test_missing_and_zero_rainfall(self) -> None:
        from datetime import date

        self.assertEqual(
            self.observations[date(2024, 1, 1)],
            {"S1": 10.0, "S2": 20.0},
        )
        csv_text = BASE_CSV.replace("S1,10.0", "S1,0").replace(
            "2024-01-01,S3,\n", ""
        )
        self.csv_path.write_text(csv_text, encoding="utf-8")
        observations = load_observations(self.csv_path, self.config)
        self.assertEqual(observations[date(2024, 1, 1)]["S1"], 0.0)

    def test_no_coverage(self) -> None:
        config_text = BASE_CONFIG.replace('"radius": 5.0', '"radius": 2.0')
        self.config_path.write_text(config_text, encoding="utf-8")
        self.config = load_config(self.config_path)
        csv_text = "date,station_id,rainfall\n2024-01-01,S3,5.0\n"
        self.csv_path.write_text(csv_text, encoding="utf-8")
        observations = load_observations(self.csv_path, self.config)
        estimates = estimate_targets(self.config, observations)
        for item in estimates:
            self.assertFalse(item.covered)
            self.assertIsNone(item.prediction)
            self.assertEqual(item.participant_ids, ())

    def test_leave_one_out_excludes_target_station(self) -> None:
        records = leave_one_out_validation(
            self.config, self.observations
        )
        by_station = {record.point_id: record for record in records}
        self.assertEqual(set(by_station), {"S1", "S2"})
        s2 = by_station["S2"]
        self.assertEqual(s2.participant_ids, ("S1",))
        self.assertAlmostEqual(s2.prediction, 10.0)
        self.assertAlmostEqual(s2.error, -10.0)

    def test_summary_metrics(self) -> None:
        records = leave_one_out_validation(
            self.config, self.observations
        )
        summary = build_summary(records)
        overall = summary["overall"]
        self.assertEqual(overall["total"], 2)
        self.assertEqual(overall["covered"], 2)
        self.assertAlmostEqual(overall["mean_error"], 0.0)
        self.assertAlmostEqual(overall["mean_absolute_error"], 10.0)
        self.assertAlmostEqual(
            overall["root_mean_squared_error"], 10.0
        )


class ValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _expect_error(self, config_text: str, csv_text: str) -> str:
        config_path, csv_path = write_files(
            self.tmp, config_text, csv_text
        )
        with self.assertRaises(InputError) as context:
            load_observations(
                csv_path, load_config(config_path)
            )
        return str(context.exception)

    def test_duplicate_station_id(self) -> None:
        message = self._expect_error(
            BASE_CONFIG.replace(
                '"S3", "x": 0.0, "y": 3.0',
                '"S1", "x": 1.0, "y": 1.0',
            ),
            BASE_CSV,
        )
        self.assertIn("stations[2]", message)

    def test_bad_radius_and_neighbors(self) -> None:
        config_path, _ = write_files(
            self.tmp, BASE_CONFIG.replace("5.0", "-1.0"), BASE_CSV
        )
        with self.assertRaises(InputError) as context:
            load_config(config_path)
        self.assertIn("radius", str(context.exception))

        config_path, _ = write_files(
            self.tmp, BASE_CONFIG.replace('"max_neighbors": 2',
                                         '"max_neighbors": 0'),
            BASE_CSV,
        )
        with self.assertRaises(InputError):
            load_config(config_path)

    def test_unknown_station_and_out_of_config_date(self) -> None:
        message = self._expect_error(
            BASE_CONFIG, BASE_CSV.replace("S1", "SX")
        )
        self.assertIn("unknown station_id", message)
        message = self._expect_error(
            BASE_CONFIG,
            BASE_CSV.replace("2024-01-01", "2024-01-02"),
        )
        self.assertIn("not listed", message)

    def test_duplicate_record_and_negative_rain(self) -> None:
        message = self._expect_error(
            BASE_CONFIG, BASE_CSV + "2024-01-01,S1,1.0\n"
        )
        self.assertIn("duplicate record", message)
        message = self._expect_error(
            BASE_CONFIG, BASE_CSV.replace("10.0", "-1.0")
        )
        self.assertIn("non-negative", message)


class CliTests(unittest.TestCase):
    def test_end_to_end_and_no_output_before_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            config_path, csv_path = write_files(
                tmp, BASE_CONFIG, BASE_CSV
            )
            out_dir = tmp / "out"
            code = run([str(config_path), str(csv_path), str(out_dir)])
            self.assertEqual(code, 0)
            self.assertTrue(
                (out_dir / "target_estimates.csv").exists()
            )
            self.assertTrue(
                (out_dir / "leave_one_out_validation.csv").exists()
            )
            summary = json.loads(
                (out_dir / "summary.json").read_text(encoding="utf-8")
            )
            self.assertIn("daily", summary)

            bad_csv = tmp / "bad.csv"
            bad_csv.write_text(
                "date,station_id,rainfall\n2024-01-01,NOPE,1.0\n",
                encoding="utf-8",
            )
            stale = out_dir / "target_estimates.csv"
            before = stale.read_text(encoding="utf-8")
            code = run([str(config_path), str(bad_csv), str(out_dir)])
            self.assertEqual(code, 1)
            self.assertEqual(
                stale.read_text(encoding="utf-8"), before
            )

    def test_module_invocation(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "rainfall_interp"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("usage", result.stderr)


if __name__ == "__main__":
    unittest.main()
