"""The ``pit-strategizer`` command-line entry point.

The ``evaluate`` subcommand scores the scripted strategists against the
ground-truth simulator over the shipped scenarios, prints a table and writes a
JSON artifact. Running the bare command prints help; the Jev-backed ``run``
subcommand belongs to a later ticket.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from pit_strategizer.evaluator import evaluate
from pit_strategizer.report import render_table, write_report
from pit_strategizer.scenarios import default_scenarios_directory, load_scenarios
from pit_strategizer.strategists import PerfectStrategist, WorstStrategist

DESCRIPTION = (
    "Get a pit strategy decision from Jev and measure how decision quality "
    "changes as the race state is abstracted."
)

DEFAULT_REPORT_PATH = "report.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pit-strategizer", description=DESCRIPTION)
    subparsers = parser.add_subparsers(dest="command")

    evaluate_parser = subparsers.add_parser(
        "evaluate",
        help="score the scripted strategists over the shipped scenarios",
        description=(
            "Score the scripted strategists against the ground-truth simulator "
            "over the shipped scenarios, print a table and write a JSON artifact."
        ),
    )
    evaluate_parser.add_argument(
        "--report",
        default=DEFAULT_REPORT_PATH,
        metavar="PATH",
        help=f"path of the JSON artifact to write (default: {DEFAULT_REPORT_PATH})",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "evaluate":
        return _run_evaluate(Path(args.report))

    parser.print_help()
    return 0


def _run_evaluate(report_path: Path) -> int:
    report = evaluate(
        [PerfectStrategist(), WorstStrategist()],
        load_scenarios(default_scenarios_directory()),
    )
    print(render_table(report))
    written = write_report(report, report_path)
    print(f"\nWrote report to {written}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
