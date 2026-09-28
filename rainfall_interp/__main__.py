"""Command line entry point: ``python -m rainfall_interp``."""

from __future__ import annotations

import argparse
import sys

from .errors import InputError
from .interpolate import leave_one_out, target_predictions
from .model import load_config, load_observations
from .report import build_summary, write_reports


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rainfall_interp",
        description=(
            "Interpolate daily rainfall at target points from local rain "
            "gauges and run leave-one-station-out validation."
        ),
    )
    parser.add_argument(
        "-c", "--config", required=True, help="Path to the JSON configuration file"
    )
    parser.add_argument(
        "-o",
        "--observations",
        required=True,
        help="Path to the observations CSV file",
    )
    parser.add_argument(
        "-d", "--output-dir", required=True, help="Directory for the report files"
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        observations = load_observations(args.observations, config)
    except InputError as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2

    targets = target_predictions(config, observations)
    validation = leave_one_out(config, observations)
    summary = build_summary(validation, config.dates)
    write_reports(args.output_dir, targets, validation, summary)
    print(
        f"Wrote {len(targets)} target estimates, {len(validation)} validation "
        f"records to {args.output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
