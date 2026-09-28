"""Summary statistics and CSV/JSON report writing."""

from __future__ import annotations

import csv
import json
import math
from datetime import date
from pathlib import Path


def _metrics(rows: list[dict]) -> dict:
    covered = [row for row in rows if row["covered"]]
    total = len(rows)
    if not covered:
        return {
            "total": total,
            "covered": 0,
            "mean_error": None,
            "mean_absolute_error": None,
            "root_mean_squared_error": None,
        }
    errors = [row["error"] for row in covered]
    mean_error = sum(errors) / len(errors)
    mean_abs = sum(abs(value) for value in errors) / len(errors)
    rmse = math.sqrt(sum(value * value for value in errors) / len(errors))
    return {
        "total": total,
        "covered": len(covered),
        "mean_error": mean_error,
        "mean_absolute_error": mean_abs,
        "root_mean_squared_error": rmse,
    }


def build_summary(validation_rows: list[dict], dates: list[date]) -> dict:
    """Build per-day and overall leave-one-out statistics."""
    by_day: dict[str, dict] = {}
    for day in dates:
        day_rows = [row for row in validation_rows if row["date"] == day]
        by_day[day.isoformat()] = _metrics(day_rows)
    return {
        "daily": by_day,
        "overall": _metrics(validation_rows),
    }


def _format_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_reports(
    output_dir: str | Path,
    target_rows: list[dict],
    validation_rows: list[dict],
    summary: dict,
) -> None:
    """Write the three report files into ``output_dir`` (created if needed)."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    target_csv = out / "target_estimates.csv"
    _write_csv(
        target_csv,
        ["date", "id", "prediction", "covered", "participant_ids"],
        [
            {
                "date": row["date"].isoformat(),
                "id": row["id"],
                "prediction": _format_float(row["prediction"]),
                "covered": "yes" if row["covered"] else "no",
                "participant_ids": ";".join(row["participants"]),
            }
            for row in target_rows
        ],
    )

    validation_csv = out / "leave_one_out.csv"
    _write_csv(
        validation_csv,
        [
            "date",
            "id",
            "actual",
            "prediction",
            "error",
            "covered",
            "participant_ids",
        ],
        [
            {
                "date": row["date"].isoformat(),
                "id": row["id"],
                "actual": _format_float(row["actual"]),
                "prediction": _format_float(row["prediction"]),
                "error": _format_float(row["error"]),
                "covered": "yes" if row["covered"] else "no",
                "participant_ids": ";".join(row["participants"]),
            }
            for row in validation_rows
        ],
    )

    summary_path = out / "summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
