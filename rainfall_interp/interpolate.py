"""Inverse-distance-weighted interpolation and leave-one-out validation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from .config import Config, Point


@dataclass(frozen=True)
class Estimate:
    day: date
    point_id: str
    prediction: float | None
    covered: bool
    participant_ids: tuple[str, ...]


@dataclass(frozen=True)
class ValidationRecord(Estimate):
    observed: float | None
    error: float | None


def _weighted_estimate(
    target: Point,
    day_obs: dict[str, float],
    stations_by_id: dict[str, Point],
    radius: float,
    max_neighbors: int,
    excluded_id: str | None = None,
) -> tuple[float | None, tuple[str, ...]]:
    candidates: list[tuple[float, str, float]] = []
    for station_id, rainfall in day_obs.items():
        if station_id == excluded_id:
            continue
        station = stations_by_id[station_id]
        distance = math.hypot(station.x - target.x, station.y - target.y)
        if distance <= radius:
            candidates.append((distance, station_id, rainfall))

    if not candidates:
        return None, ()

    zero_distance = [item for item in candidates if item[0] == 0.0]
    if zero_distance:
        ids = tuple(sorted(item[1] for item in zero_distance))
        mean = sum(item[2] for item in zero_distance) / len(zero_distance)
        return mean, ids

    candidates.sort(key=lambda item: (item[0], item[1]))
    neighbors = candidates[:max_neighbors]
    weighted_sum = 0.0
    weight_sum = 0.0
    for distance, station_id, rainfall in neighbors:
        weight = 1.0 / (distance * distance)
        weighted_sum += weight * rainfall
        weight_sum += weight
    ids = tuple(item[1] for item in neighbors)
    return weighted_sum / weight_sum, ids


def estimate_targets(
    config: Config,
    observations: dict[date, dict[str, float]],
) -> list[Estimate]:
    stations_by_id = {station.point_id: station for station in config.stations}
    results: list[Estimate] = []
    for day in config.dates:
        day_obs = observations.get(day, {})
        for target in config.targets:
            prediction, participant_ids = _weighted_estimate(
                target,
                day_obs,
                stations_by_id,
                config.radius,
                config.max_neighbors,
            )
            results.append(
                Estimate(
                    day=day,
                    point_id=target.point_id,
                    prediction=prediction,
                    covered=prediction is not None,
                    participant_ids=participant_ids,
                )
            )
    return results


def leave_one_out_validation(
    config: Config,
    observations: dict[date, dict[str, float]],
) -> list[ValidationRecord]:
    stations_by_id = {station.point_id: station for station in config.stations}
    results: list[ValidationRecord] = []
    for day in config.dates:
        day_obs = observations.get(day, {})
        for station in config.stations:
            observed = day_obs.get(station.point_id)
            if observed is None:
                continue
            prediction, participant_ids = _weighted_estimate(
                station,
                day_obs,
                stations_by_id,
                config.radius,
                config.max_neighbors,
                excluded_id=station.point_id,
            )
            error = (
                prediction - observed if prediction is not None else None
            )
            results.append(
                ValidationRecord(
                    day=day,
                    point_id=station.point_id,
                    prediction=prediction,
                    covered=prediction is not None,
                    participant_ids=participant_ids,
                    observed=observed,
                    error=error,
                )
            )
    results.sort(key=lambda record: (record.day, record.point_id))
    return results
