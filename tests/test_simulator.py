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
    Enumeration,
    RaceContext,
    RaceState,
    Stop,
    StrategyOption,
    SubjectCar,
)
from pit_strategizer.scenarios import default_scenarios_directory, load_scenarios
from pit_strategizer.enumerator import enumerate_candidates
from pit_strategizer.simulator import (
    BASE_LAP_S,
    CLIFF_CAP_S,
    CLIFF_PENALTY_S,
    CLIFF_TYRE_AGE,
    DEGRADATION_S_PER_LAP,
    FUEL_BURN_S_PER_LAP,
    SAFETY_CAR_PIT_LOSS_FACTOR,
    SimResult,
    lap_time,
    simulate,
)


def make_race_state(
    total_laps: int = 40,
    pit_loss_s: float = 22.0,
    compound: Compound = Compound.MEDIUM,
    lap: int = 20,
    tyre_age: int = 12,
    safety_car: bool = False,
) -> RaceState:
    return RaceState(
        subject=SubjectCar(
            driver="VER",
            position=2,
            compound=compound,
            tyre_age=tyre_age,
            last_lap_times_s=(91.2, 91.4),
            gap_ahead_s=3.4,
        ),
        rivals=(),
        context=RaceContext(
            lap=lap,
            total_laps=total_laps,
            track_temp_c=40.0,
            pit_loss_s=pit_loss_s,
            safety_car=safety_car,
        ),
    )


def test_repeated_runs_over_the_same_candidate_set_are_identical() -> None:
    state = make_race_state()
    candidates = CandidateSet(
        options=(
            StrategyOption(stops=()),
            StrategyOption(stops=(Stop(lap=22, compound=Compound.HARD),)),
            StrategyOption(
                stops=(
                    Stop(lap=22, compound=Compound.MEDIUM),
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
            StrategyOption(stops=(Stop(lap=22, compound=Compound.HARD),)),
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
            StrategyOption(stops=(Stop(lap=22, compound=Compound.HARD),)),
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
                StrategyOption(stops=(Stop(lap=24, compound=Compound.HARD),)),
                StrategyOption(stops=(Stop(lap=28, compound=Compound.SOFT),)),
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
    # The subject is ten laps into a soft stint at lap 10, so soft tyres pass
    # their cliff (age 18) at lap 19. A stop at lap 12 fits hards before the
    # cliff; a stop at lap 22 runs the softs four laps past it.
    total_laps = 30
    early = StrategyOption(stops=(Stop(lap=12, compound=Compound.HARD),))
    late = StrategyOption(stops=(Stop(lap=22, compound=Compound.HARD),))

    result = simulate(
        make_race_state(
            total_laps=total_laps, lap=10, tyre_age=10, compound=Compound.SOFT
        ),
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


# --- the decision moment is load-bearing --------------------------------------


def test_only_the_remaining_race_is_scored() -> None:
    # Decision on the last lap: the only scored lap is that lap, run on the
    # subject's current tyre age.
    state = make_race_state(total_laps=30, lap=30, tyre_age=7, compound=Compound.HARD)

    result = simulate(state, CandidateSet(options=(StrategyOption(stops=()),)))

    assert result.times["0STOP"] == pytest.approx(lap_time(30, 7, Compound.HARD, 1))


def test_the_remaining_race_starts_from_the_subjects_current_stint() -> None:
    state = make_race_state(total_laps=30, lap=10, tyre_age=6, compound=Compound.MEDIUM)

    result = simulate(state, CandidateSet(options=(StrategyOption(stops=()),)))

    expected = sum(
        lap_time(lap, 6 + (lap - 10), Compound.MEDIUM, 30 - lap + 1)
        for lap in range(10, 31)
    )
    assert result.times["0STOP"] == pytest.approx(expected)


def test_a_stop_fits_the_new_compound_from_the_next_lap() -> None:
    state = make_race_state(total_laps=16, lap=10, tyre_age=4, compound=Compound.MEDIUM)
    option = StrategyOption(stops=(Stop(lap=12, compound=Compound.HARD),))

    result = simulate(state, CandidateSet(options=(option,)))

    expected = (
        sum(
            lap_time(lap, 4 + (lap - 10), Compound.MEDIUM, 16 - lap + 1)
            for lap in (10, 11, 12)
        )
        + sum(
            lap_time(lap, lap - 12, Compound.HARD, 16 - lap + 1)
            for lap in range(13, 17)
        )
        + state.context.pit_loss_s
    )
    assert result.times[option.id] == pytest.approx(expected)


def test_a_later_decision_moment_scores_a_shorter_remaining_race() -> None:
    option = StrategyOption(stops=())
    candidates = CandidateSet(options=(option,))

    early = simulate(make_race_state(lap=10, total_laps=40), candidates)
    late = simulate(make_race_state(lap=20, total_laps=40), candidates)

    assert early.times["0STOP"] > late.times["0STOP"]


def test_tyre_age_changes_the_total_time() -> None:
    option = StrategyOption(stops=())
    candidates = CandidateSet(options=(option,))

    fresher = simulate(make_race_state(tyre_age=2), candidates)
    older = simulate(make_race_state(tyre_age=12), candidates)

    assert older.times["0STOP"] > fresher.times["0STOP"]


def test_safety_car_reduces_the_pit_loss_for_each_stop() -> None:
    total_laps = 20
    pit_loss_s = 22.0
    no_stop = StrategyOption(stops=())
    stop = StrategyOption(stops=(Stop(lap=total_laps, compound=Compound.HARD),))
    candidates = CandidateSet(options=(no_stop, stop))

    green = simulate(
        make_race_state(total_laps=total_laps, lap=total_laps, pit_loss_s=pit_loss_s),
        candidates,
    )
    neutralised = simulate(
        make_race_state(
            total_laps=total_laps,
            lap=total_laps,
            pit_loss_s=pit_loss_s,
            safety_car=True,
        ),
        candidates,
    )

    assert green.times[stop.id] - green.times[no_stop.id] == pytest.approx(pit_loss_s)
    assert neutralised.times[stop.id] - neutralised.times[no_stop.id] == pytest.approx(
        pit_loss_s * SAFETY_CAR_PIT_LOSS_FACTOR
    )


def test_safety_car_changes_the_ranking() -> None:
    # A fresh soft stint at lap 10 is just good enough to stay out on green
    # tyres, but halving the pit loss makes an early stop the optimum.
    state = make_race_state(
        total_laps=30, lap=10, tyre_age=0, compound=Compound.SOFT, pit_loss_s=22.0
    )
    neutralised = make_race_state(
        total_laps=30,
        lap=10,
        tyre_age=0,
        compound=Compound.SOFT,
        pit_loss_s=22.0,
        safety_car=True,
    )
    candidates = CandidateSet(
        options=(
            StrategyOption(stops=()),
            StrategyOption(stops=(Stop(lap=21, compound=Compound.SOFT),)),
        )
    )

    green_result = simulate(state, candidates)
    neutralised_result = simulate(neutralised, candidates)

    assert green_result.best_option_id != neutralised_result.best_option_id
    assert neutralised_result.best_option_id == "1STOP-L21S"


def test_the_cap_is_inert_at_and_below_the_cliff_and_truncates_past_it() -> None:
    for compound in Compound:
        cliff = CLIFF_TYRE_AGE[compound]
        rate = DEGRADATION_S_PER_LAP[compound]
        times = [lap_time(1, cliff + past, compound, 1) for past in range(5)]
        deltas = [later - earlier for earlier, later in zip(times, times[1:])]

        # Uncapped: the first step past the cliff adds the penalty, the second
        # adds three more (4.0 - 1.0).
        assert deltas[0] == pytest.approx(rate + CLIFF_PENALTY_S)
        assert deltas[1] == pytest.approx(rate + 3 * CLIFF_PENALTY_S)
        # Capped at 5.0 s, so the third step only reaches the cap and the fourth
        # adds nothing beyond degradation.
        assert deltas[2] == pytest.approx(rate + CLIFF_CAP_S - 4 * CLIFF_PENALTY_S)
        assert deltas[3] == pytest.approx(rate)


def test_the_cap_does_not_reorder_plausible_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A short remaining race on medium tyres: no option reaches the medium
    # cliff (age 26), so the cap must be entirely inert for the ordering.
    state = make_race_state(
        total_laps=25, lap=10, tyre_age=0, compound=Compound.MEDIUM, pit_loss_s=22.0
    )
    candidates = enumerate_candidates(state, Enumeration(max_stops=2, pit_lap_grid=5))

    capped = simulate(state, candidates)
    monkeypatch.setattr("pit_strategizer.simulator.CLIFF_CAP_S", float("inf"))
    uncapped = simulate(state, candidates)

    assert capped.ranking() == uncapped.ranking()


def test_the_cap_does_not_change_the_optimum(monkeypatch: pytest.MonkeyPatch) -> None:
    (scenario,) = load_scenarios(default_scenarios_directory())
    candidates = enumerate_candidates(scenario.race_state, scenario.enumeration)

    capped = simulate(scenario.race_state, candidates)
    monkeypatch.setattr("pit_strategizer.simulator.CLIFF_CAP_S", float("inf"))
    uncapped = simulate(scenario.race_state, candidates)

    assert uncapped.best_option_id == capped.best_option_id


def test_the_shipped_scenario_spread_is_bounded_by_the_remaining_race() -> None:
    (scenario,) = load_scenarios(default_scenarios_directory())
    candidates = enumerate_candidates(scenario.race_state, scenario.enumeration)
    result = simulate(scenario.race_state, candidates)

    spread = max(result.time_lost_s(option_id) for option_id in candidates.ids)
    remaining_laps = (
        scenario.race_state.context.total_laps - scenario.race_state.context.lap + 1
    )

    # The cap keeps the worst case on the same order as a single remaining lap
    # rather than a multiple of the whole remaining race.
    assert spread < BASE_LAP_S * remaining_laps
    assert spread < 200.0


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
