"""Behavioural tests for report rendering and JSON serialization.

The report is a pure value (``Report``); rendering and serialization must add no
judgement of their own. These tests assert the external shape only: every
scenario appears, the picks and their time lost are visible, the aggregates are
shown, the JSON artifact round-trips and repeated writes are byte-identical.
"""

from __future__ import annotations

import json
from pathlib import Path

from pit_strategizer.evaluator import Outcome, Report
from pit_strategizer.report import render_table, report_to_dict, write_report


def sample_report() -> Report:
    """A small hand-built report so expectations stay legible."""
    return Report(
        outcomes=(
            Outcome(
                strategist_name="perfect",
                scenario_id="mid-stint-undercut",
                option_id="2STOP-L18M-L36H",
                time_lost_s=0.0,
                confidence=1.0,
            ),
            Outcome(
                strategist_name="worst",
                scenario_id="mid-stint-undercut",
                option_id="0STOP",
                time_lost_s=12.5,
                confidence=0.75,
            ),
        ),
        strategists=("perfect", "worst"),
        scenarios=("mid-stint-undercut",),
    )


# --- table rendering ----------------------------------------------------------


def test_render_table_lists_every_scenario_and_strategist() -> None:
    report = Report(
        outcomes=(
            Outcome("perfect", "alpha", "0STOP", 0.0, 1.0),
            Outcome("worst", "alpha", "1STOP-L10M", 3.0, 1.0),
            Outcome("perfect", "beta", "0STOP", 0.0, 1.0),
            Outcome("worst", "beta", "1STOP-L12H", 4.0, 1.0),
        ),
        strategists=("perfect", "worst"),
        scenarios=("alpha", "beta"),
    )

    table = render_table(report)

    for scenario_id in ("alpha", "beta"):
        assert scenario_id in table
    assert "perfect" in table
    assert "worst" in table


def test_render_table_shows_the_picked_option_and_time_lost() -> None:
    table = render_table(sample_report())

    assert "2STOP-L18M-L36H" in table
    assert "0STOP" in table
    assert "0.000" in table
    assert "12.500" in table


def test_render_table_shows_the_aggregate_mean_per_strategist() -> None:
    table = render_table(sample_report())

    assert "Mean" in table
    # perfect: 0.0, worst: 12.5, overall: 6.25
    assert "6.250" in table
    assert "12.500" in table


def test_render_table_includes_a_scenario_with_no_outcomes() -> None:
    report = Report(outcomes=(), strategists=(), scenarios=("only-scenario",))

    table = render_table(report)

    assert "only-scenario" in table


# --- JSON serialization -------------------------------------------------------


def test_report_to_dict_contains_rows_and_aggregates() -> None:
    payload = report_to_dict(sample_report())

    assert payload["scenarios"] == ["mid-stint-undercut"]
    assert payload["strategists"] == ["perfect", "worst"]
    assert len(payload["outcomes"]) == 2

    first, second = payload["outcomes"]
    assert first["scenario_id"] == "mid-stint-undercut"
    assert first["strategist_name"] == "perfect"
    assert first["option_id"] == "2STOP-L18M-L36H"
    assert first["time_lost_s"] == 0.0
    assert first["confidence"] == 1.0
    assert first["is_optimal"] is True
    assert second["is_optimal"] is False

    assert payload["mean_time_lost_by_strategist"] == {
        "perfect": 0.0,
        "worst": 12.5,
    }
    assert payload["mean_time_lost_s"] == 6.25


def test_report_to_dict_serializes_deterministically() -> None:
    report = sample_report()

    first = json.dumps(report_to_dict(report), sort_keys=True)
    second = json.dumps(report_to_dict(report), sort_keys=True)

    assert first == second


def test_write_report_returns_the_path_and_valid_json(tmp_path: Path) -> None:
    path = tmp_path / "report.json"

    returned = write_report(sample_report(), path)

    assert returned == path
    assert path.is_file()
    assert json.loads(path.read_text(encoding="utf-8")) == report_to_dict(sample_report())


def test_write_report_is_byte_identical_across_runs(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    write_report(sample_report(), first)
    write_report(sample_report(), second)

    assert first.read_bytes() == second.read_bytes()


def test_write_report_creates_missing_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "report.json"

    write_report(sample_report(), path)

    assert path.is_file()
