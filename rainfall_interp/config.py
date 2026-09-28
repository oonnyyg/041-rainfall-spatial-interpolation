"""Loading and validation of the JSON configuration."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .errors import InputError


@dataclass(frozen=True)
class Point:
    point_id: str
    x: float
    y: float


@dataclass(frozen=True)
class Config:
    stations: tuple[Point, ...]
    targets: tuple[Point, ...]
    dates: tuple[date, ...]
    radius: float
    max_neighbors: int


def _parse_day(raw: object, location: str) -> date:
    if not isinstance(raw, str):
        raise InputError("date must be a string in YYYY-MM-DD format", location)
    text = raw.strip()
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise InputError(
            f"invalid date {raw!r}; expected YYYY-MM-DD", location
        ) from exc
    if parsed.isoformat() != text:
        raise InputError(
            f"invalid date {raw!r}; expected YYYY-MM-DD", location
        )
    return parsed


def _parse_points(raw: object, key: str) -> tuple[Point, ...]:
    location = key
    if not isinstance(raw, list) or not raw:
        raise InputError("must be a non-empty list", location)
    points: list[Point] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        item_loc = f"{key}[{index}]"
        if not isinstance(item, dict):
            raise InputError("must be an object", item_loc)
        raw_id = item.get("id")
        if not isinstance(raw_id, str) or not raw_id.strip():
            raise InputError("id must be a non-empty string", f"{item_loc}.id")
        point_id = raw_id.strip()
        if point_id in seen:
            raise InputError(f"duplicate id {point_id!r}", f"{item_loc}.id")
        seen.add(point_id)
        coords: dict[str, float] = {}
        for axis in ("x", "y"):
            value = item.get(axis)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise InputError(
                    f"{axis} must be a finite number", f"{item_loc}.{axis}"
                )
            number = float(value)
            if not math.isfinite(number):
                raise InputError(
                    f"{axis} must be a finite number", f"{item_loc}.{axis}"
                )
            coords[axis] = number
        points.append(Point(point_id, coords["x"], coords["y"]))
    return tuple(points)


def load_config(path: str | Path) -> Config:
    path = Path(path)
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InputError(f"cannot read file: {exc}", str(path)) from exc
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise InputError(
            f"invalid JSON: {exc.msg} at line {exc.lineno} column {exc.colno}",
            str(path),
        ) from exc
    if not isinstance(raw, dict):
        raise InputError("top-level value must be a JSON object", str(path))

    stations = _parse_points(raw.get("stations"), "stations")
    targets = _parse_points(raw.get("targets"), "targets")

    raw_dates = raw.get("dates")
    if not isinstance(raw_dates, list) or not raw_dates:
        raise InputError("must be a non-empty list", "dates")
    days: list[date] = []
    seen_days: set[date] = set()
    for index, raw_day in enumerate(raw_dates):
        day = _parse_day(raw_day, f"dates[{index}]")
        if day in seen_days:
            raise InputError(f"duplicate date {raw_day!r}", f"dates[{index}]")
        seen_days.add(day)
        days.append(day)

    radius = raw.get("radius")
    if isinstance(radius, bool) or not isinstance(radius, (int, float)):
        raise InputError("radius must be a non-negative finite number", "radius")
    radius_value = float(radius)
    if not math.isfinite(radius_value) or radius_value < 0:
        raise InputError("radius must be a non-negative finite number", "radius")

    max_neighbors = raw.get("max_neighbors")
    if isinstance(max_neighbors, bool) or not isinstance(max_neighbors, int):
        raise InputError(
            "max_neighbors must be a positive integer", "max_neighbors"
        )
    if max_neighbors <= 0:
        raise InputError(
            "max_neighbors must be a positive integer", "max_neighbors"
        )

    return Config(
        stations=tuple(stations),
        targets=tuple(targets),
        dates=tuple(days),
        radius=radius_value,
        max_neighbors=max_neighbors,
    )
