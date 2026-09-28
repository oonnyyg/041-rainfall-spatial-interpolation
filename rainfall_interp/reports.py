"""CSV and JSON report writing."""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path

from .interpolate import Estimate, ValidationRecord


def _format_number(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}".rstrip("0").rstrip(".")


def write_estimates(path: Path, estimates: list[Estimate]) -> None:
    ordered = sorted(estimates, key=lambda item: (item.day, item.point_id))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["date", "target_id", "prediction", "covered", "station_ids"]
        )
        for item in ordered:
            writer.writerow(
                [
                    item.day.isoformat(),
                    item.point_id,
                    _format_number(item.prediction),
                    "true" if item.covered else "false",
                    ";".join(item.participant_ids),
                ]
            )


def write_validation(path: Path, records: list[ValidationRecord]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "date",
                "station_id",
                "observed",
                "prediction",
                "covered",
                "error",
                "station_ids",
            ]
        )
        for item in records:
            writer.writerow(
                [
                    item.day.isoformat(),
                    item.point_id,
                    _format_number(item.observed),
                    _format_number(item.prediction),
                    "true" if item.covered else "false",
                    _format_number(item.error),
                    ";".join(item.participant_ids),
                ]
            )


def _metrics(records: list[ValidationRecord]) -> dict[str, object]:
    covered = [item for item in records if item.covered and item.error is not None]
    total = len(records)
    covered_count = len(covered)
    if not covered:
        return {
            "total": total,
            "covered": covered_count,
            "mean_error": None,
            "mean_absolute_error": None,
            "root_mean_squared_error": None,
        }
    errors = [item.error for item in covered]
    mean_error = sum(errors) / len(errors)
    mean_absolute = sum(abs(value) for value in errors) / len(errors)
    rmse = math.sqrt(sum(value * value for value in errors) / len(errors))
    return {
        "total": total,
        "covered": covered_count,
        "mean_error": mean_error,
        "mean_absolute_error": mean_absolute,
        "root_mean_squared_error": rmse,
    }


def build_summary(
    records: list[ValidationRecord],
) -> dict[str, object]:
    by_day: dict[date, list[ValidationRecord]] = defaultdict(list)
    for item in records:
        by_day[item.day].append(item)
    daily = {
        day.isoformat(): _metrics(by_day[day]) for day in sorted(by_day)
    }
    return {"daily": daily, "overall": _metrics(records)}


def write_summary(path: Path, summary: dict[str, object]) -> None:
    path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
