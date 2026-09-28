"""Inverse-distance-squared interpolation and leave-one-station-out logic."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from .model import Config, Point


@dataclass(frozen=True)
class Prediction:
    covered: bool
    value: float | None
    participant_ids: tuple[str, ...]


def predict_at(
    target: Point,
    config: Config,
    day_values: dict[str, float],
    exclude_station: str | None = None,
) -> Prediction:
    """Predict rainfall for ``target`` from one day's valid observations.

    Selection rules:
    * stations farther than ``radius`` are ignored;
    * stations coincident with the target (distance 0) are averaged directly,
      ignoring ``max_neighbors``;
    * otherwise candidates are ordered by distance then station id and at most
      ``max_neighbors`` are combined with inverse-squared-distance weights.

    ``exclude_station`` removes one station's observation (leave-one-out).
    Other stations sharing the same coordinates still participate.
    """
    candidates: list[tuple[float, str, float]] = []
    for station in config.stations:
        if station.id == exclude_station or station.id not in day_values:
            continue
        distance = math.hypot(station.x - target.x, station.y - target.y)
        if distance <= config.radius:
            candidates.append((distance, station.id, day_values[station.id]))

    if not candidates:
        return Prediction(False, None, ())

    coincident = [item for item in candidates if item[0] == 0.0]
    if coincident:
        coincident.sort(key=lambda item: item[1])
        ids = tuple(item[1] for item in coincident)
        value = sum(item[2] for item in coincident) / len(coincident)
        return Prediction(True, value, ids)

    candidates.sort(key=lambda item: (item[0], item[1]))
    neighbors = candidates[: config.max_neighbors]
    weight_sum = 0.0
    weighted_sum = 0.0
    for distance, _station_id, rainfall in neighbors:
        weight = 1.0 / (distance * distance)
        weight_sum += weight
        weighted_sum += weight * rainfall
    ids = tuple(item[1] for item in neighbors)
    return Prediction(True, weighted_sum / weight_sum, ids)


def values_for_day(
    observations: dict[tuple[date, str], float], day: date
) -> dict[str, float]:
    return {
        station_id: rainfall
        for (obs_date, station_id), rainfall in observations.items()
        if obs_date == day
    }


def target_predictions(
    config: Config, observations: dict[tuple[date, str], float]
) -> list[dict]:
    """Predict rainfall for every configured date x target point."""
    rows: list[dict] = []
    for day in config.dates:
        day_values = values_for_day(observations, day)
        for target in config.targets:
            result = predict_at(target, config, day_values)
            rows.append(
                {
                    "date": day,
                    "id": target.id,
                    "covered": result.covered,
                    "prediction": result.value,
                    "participants": result.participant_ids,
                }
            )
    rows.sort(key=lambda row: (row["date"], row["id"]))
    return rows


def leave_one_out(
    config: Config, observations: dict[tuple[date, str], float]
) -> list[dict]:
    """Leave-one-station-out validation for every observed station-date."""
    rows: list[dict] = []
    station_map = config.station_map
    for day, station_id in sorted(observations, key=lambda key: (key[0], key[1])):
        actual = observations[(day, station_id)]
        day_values = values_for_day(observations, day)
        held_station = station_map[station_id]
        result = predict_at(
            held_station, config, day_values, exclude_station=station_id
        )
        rows.append(
            {
                "date": day,
                "id": station_id,
                "covered": result.covered,
                "prediction": result.value,
                "participants": result.participant_ids,
                "actual": actual,
                "error": (result.value - actual) if result.covered else None,
            }
        )
    return rows
