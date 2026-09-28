"""Configuration model, loading and validation."""

from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .errors import InputError

_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def parse_date(value: str, location: str) -> date:
    """Strictly parse a YYYY-MM-DD date string."""
    text = value.strip()
    match = _DATE_RE.match(text)
    if not match:
        raise InputError(f"invalid date {value!r}, expected YYYY-MM-DD", location)
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError as exc:
        raise InputError(f"invalid calendar date {value!r}: {exc}", location)


def _finite_number(value, location: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"expected a number, got {value!r}", location)
    result = float(value)
    if not math.isfinite(result):
        raise InputError(f"expected a finite number, got {value!r}", location)
    return result


@dataclass(frozen=True)
class Point:
    id: str
    x: float
    y: float


@dataclass(frozen=True)
class Config:
    stations: list[Point]
    targets: list[Point]
    dates: list[date]
    radius: float
    max_neighbors: int

    @property
    def station_map(self) -> dict[str, Point]:
        return {point.id: point for point in self.stations}


def _parse_points(raw: object, key: str) -> list[Point]:
    loc = f"config: {key}"
    if not isinstance(raw, list) or not raw:
        raise InputError("must be a non-empty list", loc)
    points: list[Point] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        item_loc = f"{loc}[{index}]"
        if not isinstance(item, dict):
            raise InputError("must be an object with id, x, y", item_loc)
        point_id = item.get("id")
        if not isinstance(point_id, str) or not point_id.strip():
            raise InputError("id must be a non-empty string", f"{item_loc}.id")
        point_id = point_id.strip()
        if point_id in seen:
            raise InputError(f"duplicate id {point_id!r}", f"{item_loc}.id")
        seen.add(point_id)
        x = _finite_number(item.get("x"), f"{item_loc}.x")
        y = _finite_number(item.get("y"), f"{item_loc}.y")
        points.append(Point(point_id, x, y))
    return points


def load_config(path: str | Path) -> Config:
    """Read and fully validate the JSON configuration file."""
    config_path = Path(path)
    loc = "config"
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise InputError(f"file not found: {config_path}", loc)
    except json.JSONDecodeError as exc:
        raise InputError(f"invalid JSON: {exc}", loc)
    if not isinstance(raw, dict):
        raise InputError("top-level value must be an object", loc)

    stations = _parse_points(raw.get("stations"), "stations")
    targets = _parse_points(raw.get("targets"), "targets")

    raw_dates = raw.get("dates")
    if not isinstance(raw_dates, list) or not raw_dates:
        raise InputError("must be a non-empty list", "config: dates")
    dates: list[date] = []
    seen_dates: set[date] = set()
    for index, value in enumerate(raw_dates):
        if not isinstance(value, str):
            raise InputError("dates must be strings", f"config: dates[{index}]")
        parsed = parse_date(value, f"config: dates[{index}]")
        if parsed in seen_dates:
            raise InputError(f"duplicate date {value!r}", f"config: dates[{index}]")
        seen_dates.add(parsed)
        dates.append(parsed)

    radius = _finite_number(raw.get("radius"), "config: radius")
    if radius < 0:
        raise InputError(f"radius must be non-negative, got {radius}", "config: radius")

    max_neighbors_raw = raw.get("max_neighbors")
    if isinstance(max_neighbors_raw, bool) or not isinstance(max_neighbors_raw, int):
        raise InputError(
            f"max_neighbors must be a positive integer, got {max_neighbors_raw!r}",
            "config: max_neighbors",
        )
    if max_neighbors_raw < 1:
        raise InputError(
            f"max_neighbors must be a positive integer, got {max_neighbors_raw}",
            "config: max_neighbors",
        )

    return Config(
        stations=stations,
        targets=targets,
        dates=dates,
        radius=radius,
        max_neighbors=max_neighbors_raw,
    )


def load_observations(
    path: str | Path, config: Config
) -> dict[tuple[date, str], float]:
    """Read the observations CSV and validate every record.

    Returns a mapping ``(date, station_id) -> rainfall``. Blank rainfall
    cells (or missing records) denote missing data and are therefore absent
    from the mapping.
    """
    obs_path = Path(path)
    observations: dict[tuple[date, str], float] = {}
    station_ids = set(config.station_map)
    config_dates = set(config.dates)
    try:
        handle = obs_path.open(encoding="utf-8-sig", newline="")
    except FileNotFoundError:
        raise InputError(f"file not found: {obs_path}", "observations")
    with handle:
        reader = csv.DictReader(handle)
        required = ["date", "station_id", "rainfall"]
        if reader.fieldnames is None:
            raise InputError("empty CSV file", "observations")
        missing_columns = [name for name in required if name not in reader.fieldnames]
        if missing_columns:
            raise InputError(
                f"missing required columns: {', '.join(missing_columns)}",
                "observations: header",
            )
        seen: set[tuple[date, str]] = set()
        for row_index, row in enumerate(reader, start=2):
            row_loc = f"observations: row {row_index}"
            raw_station = (row.get("station_id") or "").strip()
            if not raw_station:
                raise InputError("station_id is empty", row_loc)
            if raw_station not in station_ids:
                raise InputError(
                    f"unknown station_id {raw_station!r}", f"{row_loc}.station_id"
                )
            obs_date = parse_date((row.get("date") or "").strip(), f"{row_loc}.date")
            if obs_date not in config_dates:
                raise InputError(
                    f"date {obs_date.isoformat()} is not in config dates",
                    f"{row_loc}.date",
                )
            key = (obs_date, raw_station)
            if key in seen:
                raise InputError(
                    f"duplicate record for station {raw_station!r}",
                    f"{row_loc}",
                )
            seen.add(key)

            raw_rain = (row.get("rainfall") or "").strip()
            if raw_rain == "":
                continue
            try:
                rainfall = float(raw_rain)
            except ValueError:
                raise InputError(
                    f"rainfall must be a non-negative finite number, got {raw_rain!r}",
                    f"{row_loc}.rainfall",
                )
            if not math.isfinite(rainfall) or rainfall < 0:
                raise InputError(
                    f"rainfall must be a non-negative finite number, got {raw_rain!r}",
                    f"{row_loc}.rainfall",
                )
            observations[key] = rainfall
    return observations
