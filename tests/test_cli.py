"""Smoke tests for the ``pit-strategizer`` command-line entry point."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pit_strategizer.cli import build_parser, main
from pit_strategizer.scenarios import default_scenarios_directory, load_scenarios


def test_help_lists_the_program(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])

    assert exit_info.value.code == 0
    assert "pit-strategizer" in capsys.readouterr().out


def test_bare_invocation_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "pit-strategizer" in capsys.readouterr().out


def test_parser_is_named_for_the_entry_point() -> None:
    assert build_parser().prog == "pit-strategizer"


# --- evaluate subcommand ------------------------------------------------------


def test_evaluate_prints_a_table_over_the_real_scenario(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report_path = tmp_path / "report.json"

    assert main(["evaluate", "--report", str(report_path)]) == 0

    printed = capsys.readouterr().out
    scenarios = load_scenarios(default_scenarios_directory())
    assert scenarios, "the prototype should ship at least one scenario"
    for scenario in scenarios:
        assert scenario.id in printed
    assert "perfect" in printed
    assert "worst" in printed
    assert report_path.is_file()


def test_evaluate_writes_a_parseable_json_artifact(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"

    main(["evaluate", "--report", str(report_path)])

    artifact = json.loads(report_path.read_text(encoding="utf-8"))
    assert artifact["scenarios"]
    assert artifact["outcomes"]
    assert set(artifact["mean_time_lost_by_strategist"]) == {"perfect", "worst"}


def test_evaluate_json_is_byte_identical_across_runs(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    main(["evaluate", "--report", str(first)])
    main(["evaluate", "--report", str(second)])

    assert first.read_bytes() == second.read_bytes()


def test_evaluate_report_path_defaults_to_report_json() -> None:
    args = build_parser().parse_args(["evaluate"])

    assert args.command == "evaluate"
    assert args.report == "report.json"
