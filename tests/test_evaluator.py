"""Behavioural tests for the evaluator and the scripted strategists.

Every assertion goes through the public ``evaluate`` seam: the evaluator is the
only place that enumerates a scenario's candidate set by rule and ranks it with
the ground-truth simulator, and the scripted strategists exist to exercise that
seam in place of Jev. The tests assert external behaviour, not internal steps.
"""

from __future__ import annotations

import pytest

from pit_strategizer.domain import (
    Compound,
    Enumeration,
    RaceContext,
    RaceState,
    Recommendation,
    Rival,
    Scenario,
    SubjectCar,
)
from pit_strategizer.enumerator import enumerate_candidates
from pit_strategizer.evaluator import Outcome, evaluate
from pit_strategizer.scenarios import default_scenarios_directory, load_scenarios
from pit_strategizer.simulator import SimResult, simulate
from pit_strategizer.strategists import (
    FixedStrategist,
    PerfectStrategist,
    Strategist,
    WorstStrategist,
)


def real_scenario() -> Scenario:
    """The one authored scenario that ships with the prototype."""
    scenarios = load_scenarios(default_scenarios_directory())
    assert len(scenarios) == 1
    assert scenarios[0].id == "mid-stint-undercut"
    return scenarios[0]


def small_scenario() -> Scenario:
    """A small hand-built scenario so unit expectations stay legible."""
    return Scenario(
        id="small-decision",
        archetype="cliff-decision",
        race_state=RaceState(
            subject=SubjectCar(
                driver="VER",
                position=2,
                compound=Compound.MEDIUM,
                tyre_age=6,
            ),
            rivals=(Rival(driver="NOR", compound=Compound.HARD, tyre_age=4, gap_s=1.0),),
            context=RaceContext(
                lap=10,
                total_laps=20,
                track_temp_c=40.0,
                pit_loss_s=22.0,
            ),
        ),
        enumeration=Enumeration(max_stops=1, pit_lap_grid=5),
    )


def ranked(scenario: Scenario) -> tuple[tuple[str, ...], SimResult]:
    """The scenario's full candidate set and its simulator ranking."""
    candidates = enumerate_candidates(scenario.race_state, scenario.enumeration)
    return candidates.ids, simulate(scenario.race_state, candidates)


# --- perfect strategist -------------------------------------------------------


def test_perfect_strategist_loses_no_time_on_the_real_scenario() -> None:
    scenario = real_scenario()

    ids, _ = ranked(scenario)

    report = evaluate([PerfectStrategist()], [scenario])

    (outcome,) = report.outcomes
    assert outcome.strategist_name == "perfect"
    assert outcome.scenario_id == scenario.id
    assert outcome.option_id in ids
    assert outcome.time_lost_s == 0.0
    assert outcome.is_optimal


def test_perfect_strategist_is_optimal_on_every_scenario() -> None:
    report = evaluate(
        [PerfectStrategist()],
        [real_scenario(), small_scenario()],
    )

    assert [outcome.is_optimal for outcome in report.outcomes] == [True, True]
    assert report.mean_time_lost_s == 0.0


# --- worst strategist ---------------------------------------------------------


def test_worst_strategist_loses_the_full_candidate_set_spread() -> None:
    scenario = real_scenario()
    ids, result = ranked(scenario)
    expected = max(result.time_lost_s(option_id) for option_id in ids)
    assert expected > 0.0

    report = evaluate([WorstStrategist()], [scenario])

    (outcome,) = report.outcomes
    assert outcome.strategist_name == "worst"
    assert outcome.time_lost_s == pytest.approx(expected)
    assert outcome.time_lost_s == report.mean_time_lost_s
    assert not outcome.is_optimal


# --- fixed strategist ---------------------------------------------------------


def test_fixed_strategist_loses_exactly_the_options_time_lost() -> None:
    scenario = real_scenario()
    ids, result = ranked(scenario)
    option_id = result.ranking()[1][0].id
    assert option_id != result.best_option_id
    expected = result.time_lost_s(option_id)
    assert expected > 0.0

    report = evaluate([FixedStrategist(option_id=option_id)], [scenario])

    (outcome,) = report.outcomes
    assert outcome.option_id == option_id
    assert outcome.time_lost_s == pytest.approx(expected)
    assert outcome.is_optimal is False


def test_fixed_strategist_rejects_an_option_outside_the_candidate_set() -> None:
    scenario = small_scenario()
    strategist = FixedStrategist(option_id="2STOP-L5M-L10H")

    with pytest.raises(ValueError) as excinfo:
        strategist.recommend(scenario)

    message = str(excinfo.value)
    assert "fixed" in message
    assert scenario.id in message
    assert "2STOP-L5M-L10H" in message


def test_evaluate_rejects_a_recommendation_outside_the_candidate_set() -> None:
    class RogueStrategist:
        name = "rogue"

        def recommend(self, scenario: Scenario) -> Recommendation:
            return Recommendation(option_id="2STOP-L5M-L10H", confidence=0.5)

    scenario = small_scenario()

    with pytest.raises(ValueError) as excinfo:
        evaluate([RogueStrategist()], [scenario])

    message = str(excinfo.value)
    assert "rogue" in message
    assert scenario.id in message
    assert "2STOP-L5M-L10H" in message


# --- strategist contract ------------------------------------------------------


def test_scripted_strategists_are_labelled_without_a_name_argument() -> None:
    assert PerfectStrategist().name == "perfect"
    assert WorstStrategist().name == "worst"
    assert FixedStrategist(option_id="0STOP").name == "fixed"


def test_scripted_strategists_satisfy_the_strategist_protocol() -> None:
    scripted = (
        PerfectStrategist(),
        WorstStrategist(),
        FixedStrategist(option_id="0STOP"),
    )

    for strategist in scripted:
        assert isinstance(strategist, Strategist)


def test_scripted_recommendations_are_deterministic_one_hot_choices() -> None:
    scenario = small_scenario()
    scripted = (
        PerfectStrategist(),
        WorstStrategist(),
        FixedStrategist(option_id="0STOP"),
    )

    for strategist in scripted:
        recommendation = strategist.recommend(scenario)

        assert recommendation.confidence == 1.0
        assert recommendation.probability_of(recommendation.option_id) == 1.0
        assert sum(recommendation.probabilities.values()) == pytest.approx(1.0)


# --- report shape and determinism --------------------------------------------


def test_report_exposes_overall_and_per_strategist_mean_time_lost() -> None:
    scenarios = [real_scenario(), small_scenario()]

    report = evaluate([PerfectStrategist(), WorstStrategist()], scenarios)

    assert report.scenarios == tuple(scenario.id for scenario in scenarios)
    assert report.strategists == ("perfect", "worst")
    assert report.mean_time_lost_by_strategist["perfect"] == 0.0
    assert report.mean_time_lost_by_strategist["worst"] > 0.0

    expected_overall = sum(outcome.time_lost_s for outcome in report.outcomes) / len(
        report.outcomes
    )
    assert report.mean_time_lost_s == pytest.approx(expected_overall)
    assert report.outcome_for("perfect", scenarios[0].id).is_optimal


def test_evaluating_the_same_scenarios_twice_gives_identical_reports() -> None:
    strategists = [
        PerfectStrategist(),
        WorstStrategist(),
        FixedStrategist(option_id="0STOP"),
    ]
    scenarios = [real_scenario(), small_scenario()]

    first = evaluate(strategists, scenarios)
    second = evaluate(strategists, scenarios)

    assert first == second
    assert first.outcomes == second.outcomes


def test_evaluating_no_scenarios_yields_an_empty_report() -> None:
    report = evaluate([PerfectStrategist()], [])

    assert report.outcomes == ()
    assert report.mean_time_lost_s == 0.0
    assert report.mean_time_lost_by_strategist == {"perfect": 0.0}


def test_outcome_rejects_a_negative_time_lost() -> None:
    with pytest.raises(ValueError, match="negative"):
        Outcome(
            strategist_name="x",
            scenario_id="s",
            option_id="0STOP",
            time_lost_s=-0.1,
            confidence=0.5,
        )
