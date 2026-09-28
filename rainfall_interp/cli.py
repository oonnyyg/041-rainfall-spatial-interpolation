"""Command-line interface for rainfall interpolation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_config
from .errors import InputError
from .interpolate import estimate_targets, leave_one_out_validation
from .observations import load_observations
from .reports import (
    build_summary,
    write_estimates,
    write_summary,
    write_validation,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rainfall_interp",
        description=(
            "Estimate daily rainfall at target points and run "
            "leave-one-station-out validation."
        ),
    )
    parser.add_argument("config", help="path to the JSON configuration file")
    parser.add_argument(
        "observations", help="path to the rainfall observations CSV file"
    )
    parser.add_argument(
        "output_dir", help="directory where report files will be written"
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        observations = load_observations(args.observations, config)
        estimates = estimate_targets(config, observations)
        validation = leave_one_out_validation(config, observations)
        summary = build_summary(validation)

        output_path = Path(args.output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        write_estimates(output_path / "target_estimates.csv", estimates)
        write_validation(
            output_path / "leave_one_out_validation.csv", validation
        )
        write_summary(output_path / "summary.json", summary)
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    raise SystemExit(run())
