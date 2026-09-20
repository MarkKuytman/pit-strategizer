"""Construction tests for the core domain types.

These assert the shared vocabulary from CONTEXT.md is real, constructible and
typed. They deliberately do not test behaviour that belongs to later modules
(enumerator, simulator, evaluator); they pin the shapes those modules consume.
"""

from __future__ import annotations

import dataclasses

import pytest

from pit_strategizer.domain import (
    CandidateSet,
    Compound,
    Enumeration,
    RaceContext,
    RaceState,
    Recommendation,
    Rival,
    Scenario,
    Stop,
    StrategyOption,
    SubjectCar,
    TimeLost,
)


def make_race_state() -> RaceState:
    return RaceState(
        subject=SubjectCar(
            driver="VER",
            position=2,
            compound=Compound.MEDIUM,
            tyre_age=12,
            last_lap_times_s=(91.2, 91.4, 91.7),
            gap_ahead_s=3.4,
            gap_behind_s=1.1,
        ),
        rivals=(
            Rival(
                driver="NOR",
                compound=Compound.SOFT,
                tyre_age=9,
                gap_s=3.4,
                position=1,
            ),
            Rival(
                driver="LEC",
                compound=Compound.HARD,
                tyre_age=15,
                gap_s=-1.1,
                position=3,
            ),
        ),
        context=RaceContext(
            lap=32,
            total_laps=58,
            track_temp_c=41.0,
            pit_loss_s=22.0,
        ),
    )


def make_scenario() -> Scenario:
    return Scenario(
        id="mid-stint-undercut",
        archetype="undercut-threat",
        race_state=make_race_state(),
        enumeration=Enumeration(max_stops=2, pit_lap_grid=3),
    )


def make_candidate_set() -> CandidateSet:
    return CandidateSet(
        options=(
            StrategyOption(stops=(Stop(lap=18, compound=Compound.MEDIUM), Stop(lap=36, compound=Compound.HARD))),
            StrategyOption(stops=(Stop(lap=24, compound=Compound.HARD),)),
            StrategyOption(stops=()),
        )
    )


def test_every_core_type_constructs_into_a_coherent_scenario() -> None:
    scenario = make_scenario()

    assert scenario.id == "mid-stint-undercut"
    assert scenario.archetype == "undercut-threat"
    assert scenario.race_state.subject.driver == "VER"
    assert scenario.race_state.subject.tyre_age == 12
    assert [rival.driver for rival in scenario.race_state.rivals] == ["NOR", "LEC"]
    assert scenario.race_state.context.lap == 32
    assert scenario.enumeration.max_stops == 2

    candidates = make_candidate_set()
    assert len(candidates) == 3
    assert candidates.ids == (
        "2STOP-L18M-L36H",
        "1STOP-L24H",
        "0STOP",
    )
    assert candidates.by_id("1STOP-L24H") == StrategyOption(stops=(Stop(lap=24, compound=Compound.HARD),))

    recommendation = Recommendation(
        option_id="1STOP-L24H",
        confidence=0.62,
        probabilities={"2STOP-L18M-L36H": 0.13, "1STOP-L24H": 0.62, "0STOP": 0.25},
        raw={"primitive": "choice", "name": "strategy"},
    )
    assert recommendation.option_id == "1STOP-L24H"
    assert recommendation.confidence == pytest.approx(0.62)
    assert recommendation.probability_of("0STOP") == pytest.approx(0.25)
    assert recommendation.raw == {"primitive": "choice", "name": "strategy"}

    time_lost = TimeLost(seconds=0.0)
    assert time_lost.is_optimal


def test_strategy_option_has_canonical_id() -> None:
    assert StrategyOption(stops=()).id == "0STOP"
    assert StrategyOption(stops=(Stop(lap=24, compound=Compound.HARD),)).id == "1STOP-L24H"
    assert (
        StrategyOption(
            stops=(
                Stop(lap=18, compound=Compound.MEDIUM),
                Stop(lap=36, compound=Compound.HARD),
            )
        ).id
        == "2STOP-L18M-L36H"
    )


def test_compound_codes_are_single_letters() -> None:
    assert Compound.SOFT.code == "S"
    assert Compound.MEDIUM.code == "M"
    assert Compound.HARD.code == "H"


def test_core_types_are_frozen() -> None:
    scenario = make_scenario()
    with pytest.raises(dataclasses.FrozenInstanceError):
        scenario.id = "changed"  # type: ignore[misc]


def test_race_context_derives_laps_remaining() -> None:
    context = RaceContext(lap=32, total_laps=58, track_temp_c=41.0, pit_loss_s=22.0)
    assert context.laps_remaining == 26


def test_candidate_set_rejects_empty_and_duplicate_options() -> None:
    with pytest.raises(ValueError, match="at least one"):
        CandidateSet(options=())

    duplicate = StrategyOption(stops=(Stop(lap=24, compound=Compound.HARD),))
    with pytest.raises(ValueError, match="duplicate"):
        CandidateSet(options=(duplicate, duplicate))


def test_strategy_option_rejects_out_of_order_stops() -> None:
    with pytest.raises(ValueError, match="increasing"):
        StrategyOption(
            stops=(
                Stop(lap=36, compound=Compound.HARD),
                Stop(lap=18, compound=Compound.MEDIUM),
            )
        )


def test_enumeration_is_bounded_to_two_stops() -> None:
    with pytest.raises(ValueError, match="two stops"):
        Enumeration(max_stops=3, pit_lap_grid=3)

    with pytest.raises(ValueError, match="grid"):
        Enumeration(max_stops=2, pit_lap_grid=0)


def test_recommendation_validates_confidence_and_distribution() -> None:
    with pytest.raises(ValueError, match="confidence"):
        Recommendation(option_id="0STOP", confidence=1.5)

    with pytest.raises(ValueError, match="selected option"):
        Recommendation(
            option_id="0STOP",
            confidence=0.5,
            probabilities={"1STOP-L24H": 1.0},
        )


def test_time_lost_cannot_be_negative() -> None:
    with pytest.raises(ValueError, match="negative"):
        TimeLost(seconds=-0.1)
