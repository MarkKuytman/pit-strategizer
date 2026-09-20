"""The ``pit-strategizer`` command-line entry point.

This is the walking-skeleton stub: it parses arguments and prints help. The
``run`` and ``evaluate`` subcommands are added by later tickets.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

DESCRIPTION = (
    "Get a pit strategy decision from Jev and measure how decision quality "
    "changes as the race state is abstracted."
)


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(prog="pit-strategizer", description=DESCRIPTION)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
