"""Render an evaluated :class:`~pit_strategizer.evaluator.Report` for humans and machines.

Reporting is deliberately split from evaluation: ``evaluate`` produces a pure
:class:`Report` value, and this module only formats it. ``render_table`` returns
a readable Markdown table for the console; ``report_to_dict`` and
``write_report`` produce the deterministic JSON artifact. Neither recomputes
anything or consults the simulator, so a report printed twice is identical.

The vocabulary follows CONTEXT.md: time lost is the selected option's seconds
behind the optimum, zero when optimal.
"""

from __future__ import annotations

import json
from pathlib import Path

from pit_strategizer.evaluator import Outcome, Report

__all__ = ["render_table", "report_to_dict", "write_report"]

_HEADER = "| Scenario | Strategist | Option | Time lost (s) | Confidence | Optimal |"
_SEPARATOR = "| --- | --- | --- | --- | --- | --- |"
_MEAN_HEADER = "| Strategist | Mean time lost (s) |"
_MEAN_SEPARATOR = "| --- | --- |"


def render_table(report: Report) -> str:
    """Render ``report`` as a Markdown table, one row per (scenario, strategist).

    Scenarios and strategists appear in the report's evaluation order. Every
    scenario in ``report.scenarios`` gets at least one row; a scenario with no
    outcomes is shown with a placeholder row rather than silently dropped. The
    per-table aggregates close with the mean time lost per strategist and over
    all outcomes.
    """
    lines = [_HEADER, _SEPARATOR]

    outcomes_by_scenario: dict[str, list[Outcome]] = {}
    for outcome in report.outcomes:
        outcomes_by_scenario.setdefault(outcome.scenario_id, []).append(outcome)

    scenario_ids = report.scenarios or tuple(outcomes_by_scenario)
    for scenario_id in scenario_ids:
        scenario_outcomes = outcomes_by_scenario.get(scenario_id, [])
        if not scenario_outcomes:
            lines.append(_placeholder_row(scenario_id))
            continue
        for outcome in scenario_outcomes:
            lines.append(_outcome_row(outcome))

    lines.append("")
    lines.append("Mean time lost per strategist (s):")
    lines.append(_MEAN_HEADER)
    lines.append(_MEAN_SEPARATOR)
    for strategist, mean in report.mean_time_lost_by_strategist.items():
        lines.append(f"| {strategist} | {mean:.3f} |")

    lines.append("")
    lines.append(f"Mean time lost over all outcomes (s): {report.mean_time_lost_s:.3f}")
    return "\n".join(lines)


def report_to_dict(report: Report) -> dict:
    """Return ``report`` as a JSON-serializable dict with stable ordering.

    Outcomes keep the report's scenario-major order; ``strategist_name`` and
    ``scenario_id`` mirror the :class:`Outcome` fields so the artifact maps back
    onto the domain types without translation.
    """
    return {
        "scenarios": list(report.scenarios),
        "strategists": list(report.strategists),
        "outcomes": [
            {
                "scenario_id": outcome.scenario_id,
                "strategist_name": outcome.strategist_name,
                "option_id": outcome.option_id,
                "time_lost_s": outcome.time_lost_s,
                "confidence": outcome.confidence,
                "is_optimal": outcome.is_optimal,
            }
            for outcome in report.outcomes
        ],
        "mean_time_lost_s": report.mean_time_lost_s,
        "mean_time_lost_by_strategist": dict(report.mean_time_lost_by_strategist),
    }


def write_report(report: Report, path: str | Path) -> Path:
    """Write ``report`` to ``path`` as deterministic JSON and return the path.

    Keys are sorted and the outcome list keeps evaluation order, so writing the
    same report twice produces byte-identical files. Missing parent directories
    are created.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report_to_dict(report), indent=2, sort_keys=True)
    path.write_text(payload + "\n", encoding="utf-8")
    return path


def _outcome_row(outcome: Outcome) -> str:
    optimal = "yes" if outcome.is_optimal else "no"
    return (
        f"| {outcome.scenario_id} | {outcome.strategist_name} | "
        f"{outcome.option_id} | {outcome.time_lost_s:.3f} | "
        f"{outcome.confidence:.3f} | {optimal} |"
    )


def _placeholder_row(scenario_id: str) -> str:
    return f"| {scenario_id} | - | - | - | - | - |"
