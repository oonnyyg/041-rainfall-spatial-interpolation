"""Loading and validation of rainfall observation CSV files."""

from __future__ import annotations

import csv
import math
from datetime import date
from pathlib import Path

from .config import Config
from .errors import InputError


def load_observations(
    path: str | Path, config: Config
) -> dict[date, dict[str, float]]:
    """Return observations keyed by date then station id.

    Blank rainfall cells and missing rows are treated as missing
    measurements. Zero rainfall is a valid value.
    """
    path = Path(path)
    try:
        handle = path.open("r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise InputError(f"cannot read file: {exc}", str(path)) from exc

    observations: dict[date, dict[str, float]] = {}
    valid_days = set(config.dates)
    valid_stations = {station.point_id for station in config.stations}

    with handle:
        reader = csv.DictReader(handle)
        required = {"date", "station_id", "rainfall"}
        actual = set(reader.fieldnames or [])
        missing_columns = required - actual
        if missing_columns:
            raise InputError(
                "missing required column(s): "
                + ", ".join(sorted(missing_columns)),
                str(path),
            )
        for line_number, row in enumerate(reader, start=2):
            row_loc = f"{path} row {line_number}"
            if row.get(None):
                raise InputError("too many columns", row_loc)

            raw_day = (row.get("date") or "").strip()
            station_id = (row.get("station_id") or "").strip()
            raw_rain = (row.get("rainfall") or "").strip()
            if not raw_day:
                raise InputError("date must not be blank", f"{row_loc}.date")
            if not station_id:
                raise InputError(
                    "station_id must not be blank", f"{row_loc}.station_id"
                )
            try:
                parsed_day = date.fromisoformat(raw_day)
            except ValueError as exc:
                raise InputError(
                    f"invalid date {raw_day!r}; expected YYYY-MM-DD",
                    f"{row_loc}.date",
                ) from exc
            if parsed_day.isoformat() != raw_day:
                raise InputError(
                    f"invalid date {raw_day!r}; expected YYYY-MM-DD",
                    f"{row_loc}.date",
                )
            if parsed_day not in valid_days:
                raise InputError(
                    f"date {raw_day} is not listed in configuration dates",
                    f"{row_loc}.date",
                )
            if station_id not in valid_stations:
                raise InputError(
                    f"unknown station_id {station_id!r}",
                    f"{row_loc}.station_id",
                )

            if raw_rain == "":
                continue
            try:
                rainfall = float(raw_rain)
            except ValueError as exc:
                raise InputError(
                    f"rainfall {raw_rain!r} must be a non-negative finite number",
                    f"{row_loc}.rainfall",
                ) from exc
            if not math.isfinite(rainfall) or rainfall < 0:
                raise InputError(
                    f"rainfall {raw_rain!r} must be a non-negative finite number",
                    f"{row_loc}.rainfall",
                )

            day_map = observations.setdefault(parsed_day, {})
            if station_id in day_map:
                raise InputError(
                    f"duplicate record for station {station_id!r} on {raw_day}",
                    row_loc,
                )
            day_map[station_id] = rainfall

    return observations
