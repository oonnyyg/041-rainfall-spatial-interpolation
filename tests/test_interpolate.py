import math
import unittest
from datetime import date

from rainfall_interp.interpolate import (
    leave_one_out,
    predict_at,
    target_predictions,
)
from rainfall_interp.model import Config, Point


def make_config(stations, targets, radius=100.0, max_neighbors=3, dates=("2024-01-01",)):
    return Config(
        stations=[Point(sid, x, y) for sid, x, y in stations],
        targets=[Point(tid, x, y) for tid, x, y in targets],
        dates=[date.fromisoformat(day) for day in dates],
        radius=radius,
        max_neighbors=max_neighbors,
    )


SQUARE = [("S1", 0.0, 0.0), ("S2", 4.0, 0.0), ("S3", 0.0, 4.0), ("S4", 4.0, 4.0)]


class PredictionTests(unittest.TestCase):
    def test_inverse_distance_squared_weights(self):
        config = make_config(
            [("S1", 0.0, 0.0), ("S2", 0.0, 4.0)],
            [("T1", 0.0, 3.0)],
        )
        values = {"S1": 10.0, "S2": 20.0}
        result = predict_at(config.targets[0], config, values)
        # distances 3 (S1) and 1 (S2); weights 1/9 and 1/1
        expected = (10 / 9 + 20.0) / (1 / 9 + 1.0)
        self.assertTrue(result.covered)
        self.assertAlmostEqual(result.value, expected)
        self.assertEqual(result.participant_ids, ("S2", "S1"))

    def test_radius_filters_candidates(self):
        config = make_config(
            [("S1", 0.0, 0.0), ("S2", 50.0, 0.0)],
            [("T1", 0.0, 0.0)],
            radius=10.0,
        )
        result = predict_at(config.targets[0], config, {"S1": 1.0, "S2": 9.0})
        self.assertEqual(result.participant_ids, ("S1",))
        self.assertAlmostEqual(result.value, 1.0)

    def test_boundary_distance_is_inclusive(self):
        config = make_config(
            [("S1", 10.0, 0.0)], [("T1", 0.0, 0.0)], radius=10.0
        )
        result = predict_at(config.targets[0], config, {"S1": 7.0})
        self.assertTrue(result.covered)
        self.assertEqual(result.participant_ids, ("S1",))

    def test_coincident_station_average_ignores_cap(self):
        config = make_config(
            [
                ("S1", 0.0, 0.0),
                ("S2", 0.0, 0.0),
                ("S3", 1.0, 0.0),
            ],
            [("T1", 0.0, 0.0)],
            max_neighbors=1,
        )
        result = predict_at(
            config.targets[0], config, {"S1": 2.0, "S2": 4.0, "S3": 100.0}
        )
        self.assertEqual(result.participant_ids, ("S1", "S2"))
        self.assertAlmostEqual(result.value, 3.0)

    def test_neighbor_cap_and_tie_break(self):
        stations = [(f"S{i}", float(x), 3.0) for i, x in enumerate(range(0, 9, 2), start=1)]
        config = make_config(stations, [("T1", 4.0, 0.0)], radius=100.0, max_neighbors=2)
        values = {sid: float(index * 10) for index, (sid, _x, _y) in enumerate(stations, start=1)}
        result = predict_at(config.targets[0], config, values)
        # distances to x=4: S1 x0 ->5, S2 x2 ->sqrt13, S3 x4 ->3, ...
        self.assertEqual(result.participant_ids, ("S3", "S2"))

    def test_tie_break_station_id_lexicographic(self):
        config = make_config(
            [("S10", -3.0, 0.0), ("S2", 3.0, 0.0)],
            [("T1", 0.0, 0.0)],
            max_neighbors=1,
        )
        result = predict_at(
            config.targets[0], config, {"S10": 1.0, "S2": 2.0}
        )
        self.assertEqual(result.participant_ids, ("S10",))

    def test_no_coverage(self):
        config = make_config(SQUARE, [("T1", 100.0, 100.0)], radius=1.0)
        result = predict_at(
            config.targets[0],
            config,
            {sid: 1.0 for sid, _x, _y in SQUARE},
        )
        self.assertFalse(result.covered)
        self.assertIsNone(result.value)
        self.assertEqual(result.participant_ids, ())

    def test_missing_observations_ignored(self):
        config = make_config(SQUARE, [("T1", 2.0, 2.0)])
        result = predict_at(
            config.targets[0], config, {"S1": 8.0}
        )
        self.assertEqual(result.participant_ids, ("S1",))


class LeaveOneOutTests(unittest.TestCase):
    def test_excludes_target_but_keeps_colocated_peer(self):
        config = make_config(
            [("S1", 0.0, 0.0), ("S2", 0.0, 0.0), ("S3", 5.0, 0.0)],
            [],
            radius=10.0,
        )
        observations = {
            (date(2024, 1, 1), "S1"): 2.0,
            (date(2024, 1, 1), "S2"): 4.0,
            (date(2024, 1, 1), "S3"): 8.0,
        }
        rows = leave_one_out(config, observations)
        s1 = next(row for row in rows if row["id"] == "S1")
        # coincident peer S2 is averaged directly
        self.assertEqual(s1["participants"], ("S2",))
        self.assertAlmostEqual(s1["prediction"], 4.0)
        self.assertAlmostEqual(s1["error"], 2.0)

    def test_uncovered_validation_row_has_no_error(self):
        config = make_config(
            [("S1", 0.0, 0.0)], [], radius=1.0
        )
        observations = {(date(2024, 1, 1), "S1"): 3.0}
        rows = leave_one_out(config, observations)
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["covered"])
        self.assertIsNone(rows[0]["error"])

    def test_only_observed_station_dates_validated_and_sorted(self):
        config = make_config(
            SQUARE,
            [("T1", 2.0, 2.0)],
            dates=("2024-01-01", "2024-01-02"),
        )
        observations = {
            (date(2024, 1, 2), "S2"): 1.0,
            (date(2024, 1, 1), "S1"): 2.0,
        }
        rows = leave_one_out(config, observations)
        self.assertEqual(
            [(row["date"], row["id"]) for row in rows],
            [(date(2024, 1, 1), "S1"), (date(2024, 1, 2), "S2")],
        )

    def test_target_predictions_cover_every_config_date(self):
        config = make_config(
            [("S1", 0.0, 0.0)],
            [("T1", 0.0, 0.0)],
            radius=1.0,
            dates=("2024-01-01", "2024-01-02"),
        )
        observations = {(date(2024, 1, 1), "S1"): 2.0}
        rows = target_predictions(config, observations)
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0]["covered"])
        self.assertFalse(rows[1]["covered"])


if __name__ == "__main__":
    unittest.main()
