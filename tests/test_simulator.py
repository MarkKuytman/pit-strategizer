"""Behavioural tests for the deterministic ground-truth simulator (ADR-0001).

These assert the simulator's external behaviour: determinism, the cost of a
stop, degradation with tyre age, the sharp cliff fall-off, and that the optimum
and every option's total time are exposed to the evaluator. Absolute lap times
are invented constants, not real-world predictions, so the tests assert
relationships between options rather than the numbers themselves.
"""

from __future__ import annotations

import dataclasses

import pytest

from pit_strategizer.domain import (
    CandidateSet,
    Compound,
    RaceContext,
    RaceState,
    Stop,
    StrategyOption,
    SubjectCar,
)
from pit_strategizer.simulator import (
    BASE_LAP_S,
    CLIFF_PENALTY_S,
    CLIFF_TYRE_AGE,
    DEGRADATION_S_PER_LAP,
    FUEL_BURN_S_PER_LAP,
    SimResult,
    lap_time,
    simulate,
)


def make_race_state(
    total_laps: int = 40,
    pit_loss_s: float = 22.0,
    compound: Compound = Compound.MEDIUM,
) -> RaceState:
    return RaceState(
        subject=SubjectCar(
            driver="VER",
            position=2,
            compound=compound,
            tyre_age=12,
            last_lap_times_s=(91.2, 91.4),
            gap_ahead_s=3.4,
        ),
        rivals=(),
        context=RaceContext(
            lap=20,
            total_laps=total_laps,
            track_temp_c=40.0,
            pit_loss_s=pit_loss_s,
        ),
    )


def test_repeated_runs_over_the_same_candidate_set_are_identical() -> None:
    state = make_race_state()
    candidates = CandidateSet(
        options=(
            StrategyOption(stops=()),
            StrategyOption(stops=(Stop(lap=15, compound=Compound.HARD),)),
            StrategyOption(
                stops=(
                    Stop(lap=12, compound=Compound.MEDIUM),
                    Stop(lap=27, compound=Compound.SOFT),
                )
            ),
        )
    )

    first = simulate(state, candidates)
    second = simulate(state, candidates)

    assert first.times == second.times
    assert first.ranking() == second.ranking()
    assert first.best_option_id == second.best_option_id


def test_optimum_and_every_total_time_are_exposed() -> None:
    state = make_race_state()
    candidates = CandidateSet(
        options=(
            StrategyOption(stops=()),
            StrategyOption(stops=(Stop(lap=15, compound=Compound.HARD),)),
        )
    )

    result = simulate(state, candidates)

    assert set(result.times) == set(candidates.ids)
    assert result.best_option_id in result.times
    assert result.best_time_s == min(result.times.values())
    assert result.best_option == candidates.by_id(result.best_option_id)
    assert result.by_id(result.best_option_id) == result.best_option


def test_time_lost_is_the_gap_to_the_optimum() -> None:
    state = make_race_state()
    candidates = CandidateSet(
        options=(
            StrategyOption(stops=()),
            StrategyOption(stops=(Stop(lap=15, compound=Compound.HARD),)),
            StrategyOption(stops=(Stop(lap=30, compound=Compound.SOFT),)),
        )
    )

    result = simulate(state, candidates)

    assert result.time_lost_s(result.best_option_id) == 0.0
    for option_id, seconds in result.times.items():
        assert result.time_lost_s(option_id) == pytest.approx(
            seconds - result.best_time_s
        )
    assert any(result.time_lost_s(option_id) > 0.0 for option_id in result.times)


def test_time_lost_raises_for_an_unknown_option_id() -> None:
    result = simulate(
        make_race_state(),
        CandidateSet(options=(StrategyOption(stops=()),)),
    )

    with pytest.raises(KeyError):
        result.time_lost_s("2STOP-L1S-L2S")


def test_ranking_is_ascending_and_agrees_with_the_optimum() -> None:
    result = simulate(
        make_race_state(),
        CandidateSet(
            options=(
                StrategyOption(stops=()),
                StrategyOption(stops=(Stop(lap=15, compound=Compound.HARD),)),
                StrategyOption(stops=(Stop(lap=8, compound=Compound.SOFT),)),
            )
        ),
    )

    ranking = result.ranking()

    assert [seconds for _, seconds in ranking] == sorted(result.times.values())
    assert ranking[0] == (result.best_option, result.best_time_s)


def test_a_stop_costs_the_pit_loss() -> None:
    total_laps = 20
    pit_loss_s = 22.0
    no_stop = StrategyOption(stops=())
    stop_on_the_last_lap = StrategyOption(
        stops=(Stop(lap=total_laps, compound=Compound.HARD),)
    )

    result = simulate(
        make_race_state(total_laps=total_laps, pit_loss_s=pit_loss_s),
        CandidateSet(options=(no_stop, stop_on_the_last_lap)),
    )

    assert result.times[stop_on_the_last_lap.id] == pytest.approx(
        result.times[no_stop.id] + pit_loss_s
    )


def test_lap_times_rise_with_tyre_age_below_the_cliff() -> None:
    for compound in Compound:
        rate = DEGRADATION_S_PER_LAP[compound]
        cliff = CLIFF_TYRE_AGE[compound]
        for age in range(1, cliff):
            older = lap_time(1, age + 1, compound, 1)
            fresher = lap_time(1, age, compound, 1)
            assert older - fresher == pytest.approx(rate)


def test_lap_times_fall_away_sharply_past_the_cliff() -> None:
    for compound in Compound:
        cliff = CLIFF_TYRE_AGE[compound]
        gradual = DEGRADATION_S_PER_LAP[compound]
        at_cliff = lap_time(1, cliff, compound, 1)
        one_past = lap_time(1, cliff + 1, compound, 1)
        two_past = lap_time(1, cliff + 2, compound, 1)

        assert one_past - at_cliff >= 0.5
        assert one_past - at_cliff > gradual
        assert two_past - one_past > one_past - at_cliff
        assert one_past - at_cliff == pytest.approx(gradual + CLIFF_PENALTY_S)


def test_pitting_before_the_cliff_beats_running_past_it() -> None:
    total_laps = 30
    early = StrategyOption(stops=(Stop(lap=10, compound=Compound.HARD),))
    late = StrategyOption(stops=(Stop(lap=20, compound=Compound.HARD),))

    result = simulate(
        make_race_state(total_laps=total_laps, compound=Compound.SOFT),
        CandidateSet(options=(early, late)),
    )

    assert result.times[early.id] < result.times[late.id]
    assert result.times[late.id] - result.times[early.id] > 5.0


def test_no_stop_and_one_stop_plans_are_both_scored() -> None:
    one_stop = StrategyOption(stops=(Stop(lap=20, compound=Compound.HARD),))

    result = simulate(
        make_race_state(),
        CandidateSet(options=(StrategyOption(stops=()), one_stop)),
    )

    assert set(result.times) == {"0STOP", one_stop.id}
    assert result.best_option_id in {"0STOP", one_stop.id}


def test_fuel_makes_early_laps_slower() -> None:
    early = lap_time(1, 1, Compound.MEDIUM, 40)
    late = lap_time(40, 1, Compound.MEDIUM, 1)

    assert early > late
    assert early - late == pytest.approx(FUEL_BURN_S_PER_LAP * 39)


def test_base_lap_time_without_fuel_or_tyre_age() -> None:
    assert lap_time(1, 0, Compound.MEDIUM, 0) == pytest.approx(BASE_LAP_S)


def test_ranking_breaks_ties_in_candidate_order() -> None:
    first = StrategyOption(stops=(Stop(lap=10, compound=Compound.HARD),))
    second = StrategyOption(stops=(Stop(lap=12, compound=Compound.SOFT),))
    candidates = CandidateSet(options=(first, second))

    result = SimResult(times={first.id: 100.0, second.id: 100.0}, candidates=candidates)

    assert result.ranking() == ((first, 100.0), (second, 100.0))
    assert result.best_option_id == first.id
    assert result.time_lost_s(second.id) == 0.0


def test_a_stop_beyond_the_last_lap_is_rejected() -> None:
    option = StrategyOption(stops=(Stop(lap=21, compound=Compound.HARD),))

    with pytest.raises(ValueError, match="beyond"):
        simulate(make_race_state(total_laps=20), CandidateSet(options=(option,)))


def test_sim_result_is_frozen() -> None:
    result = simulate(
        make_race_state(),
        CandidateSet(options=(StrategyOption(stops=()),)),
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        result.times = {}  # type: ignore[misc]
