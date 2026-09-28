import json
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from rainfall_interp.errors import InputError
from rainfall_interp.model import load_config, load_observations


VALID_CONFIG = {
    "stations": [
        {"id": "S1", "x": 0.0, "y": 0.0},
        {"id": "S2", "x": 10.0, "y": 0.0},
    ],
    "targets": [{"id": "T1", "x": 5.0, "y": 0.0}],
    "dates": ["2024-01-01"],
    "radius": 10.0,
    "max_neighbors": 2,
}


class ConfigValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write_config(self, payload):
        path = self.dir / "config.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_valid_config(self):
        config = load_config(self.write_config(VALID_CONFIG))
        self.assertEqual(config.dates, [date(2024, 1, 1)])
        self.assertEqual(config.radius, 10.0)
        self.assertEqual(config.max_neighbors, 2)

    def test_missing_file(self):
        with self.assertRaises(InputError) as ctx:
            load_config(self.dir / "nope.json")
        self.assertIn("file not found", str(ctx.exception))

    def test_duplicate_station_id(self):
        payload = json.loads(json.dumps(VALID_CONFIG))
        payload["stations"].append({"id": "S1", "x": 1, "y": 1})
        with self.assertRaises(InputError) as ctx:
            load_config(self.write_config(payload))
        self.assertIn("duplicate id", str(ctx.exception))
        self.assertIn("stations[2]", ctx.exception.location)

    def test_empty_station_id(self):
        payload = json.loads(json.dumps(VALID_CONFIG))
        payload["stations"][0]["id"] = "  "
        with self.assertRaises(InputError) as ctx:
            load_config(self.write_config(payload))
        self.assertIn("non-empty", str(ctx.exception))

    def test_non_finite_coordinate(self):
        payload = json.loads(json.dumps(VALID_CONFIG))
        payload["stations"][0]["x"] = "inf"
        path = self.write_config(payload)
        text = path.read_text(encoding="utf-8").replace('"inf"', "Infinity")
        path.write_text(text, encoding="utf-8")
        with self.assertRaises(InputError) as ctx:
            load_config(path)
        self.assertIn("finite", str(ctx.exception))

    def test_duplicate_dates_rejected(self):
        payload = json.loads(json.dumps(VALID_CONFIG))
        payload["dates"] = ["2024-01-01", "2024-01-01"]
        with self.assertRaises(InputError) as ctx:
            load_config(self.write_config(payload))
        self.assertIn("duplicate date", str(ctx.exception))

    def test_bad_calendar_date_rejected(self):
        payload = json.loads(json.dumps(VALID_CONFIG))
        payload["dates"] = ["2024-02-30"]
        with self.assertRaises(InputError):
            load_config(self.write_config(payload))

    def test_negative_radius_rejected(self):
        payload = json.loads(json.dumps(VALID_CONFIG))
        payload["radius"] = -1.0
        with self.assertRaises(InputError) as ctx:
            load_config(self.write_config(payload))
        self.assertIn("radius", ctx.exception.location)

    def test_zero_radius_allowed(self):
        payload = json.loads(json.dumps(VALID_CONFIG))
        payload["radius"] = 0
        config = load_config(self.write_config(payload))
        self.assertEqual(config.radius, 0.0)

    def test_max_neighbors_must_be_positive_integer(self):
        for bad in (0, -1, 1.5, True, "3"):
            payload = json.loads(json.dumps(VALID_CONFIG))
            payload["max_neighbors"] = bad
            with self.assertRaises(InputError):
                load_config(self.write_config(payload))

    def test_empty_lists_rejected(self):
        for key in ("stations", "targets", "dates"):
            payload = json.loads(json.dumps(VALID_CONFIG))
            payload[key] = []
            with self.assertRaises(InputError):
                load_config(self.write_config(payload))


OBS_HEADER = "date,station_id,rainfall\n"


class ObservationValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.config_path = self.dir / "config.json"
        self.config_path.write_text(json.dumps(VALID_CONFIG), encoding="utf-8")
        self.config = load_config(self.config_path)

    def tearDown(self):
        self.tmp.cleanup()

    def load(self, text):
        path = self.dir / "obs.csv"
        path.write_text(OBS_HEADER + text, encoding="utf-8")
        return load_observations(path, self.config)

    def test_valid_records_and_blank_missing(self):
        obs = self.load("2024-01-01,S1,2.5\n2024-01-01,S2,\n")
        self.assertEqual(obs[(date(2024, 1, 1), "S1")], 2.5)
        self.assertNotIn((date(2024, 1, 1), "S2"), obs)

    def test_zero_rainfall_is_valid(self):
        obs = self.load("2024-01-01,S1,0\n")
        self.assertEqual(obs[(date(2024, 1, 1), "S1")], 0.0)

    def test_unknown_station(self):
        with self.assertRaises(InputError) as ctx:
            self.load("2024-01-01,S9,1\n")
        self.assertIn("unknown station", str(ctx.exception))
        self.assertIn("row 2", ctx.exception.location)

    def test_date_outside_config(self):
        with self.assertRaises(InputError) as ctx:
            self.load("2024-01-02,S1,1\n")
        self.assertIn("not in config dates", str(ctx.exception))

    def test_duplicate_station_date(self):
        with self.assertRaises(InputError) as ctx:
            self.load("2024-01-01,S1,1\n2024-01-01,S1,2\n")
        self.assertIn("duplicate", str(ctx.exception))

    def test_negative_rainfall(self):
        with self.assertRaises(InputError):
            self.load("2024-01-01,S1,-0.1\n")

    def test_non_numeric_rainfall(self):
        with self.assertRaises(InputError):
            self.load("2024-01-01,S1,wet\n")

    def test_missing_header_column(self):
        path = self.dir / "bad.csv"
        path.write_text("date,station_id\n2024-01-01,S1\n", encoding="utf-8")
        with self.assertRaises(InputError) as ctx:
            load_observations(path, self.config)
        self.assertIn("rainfall", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
