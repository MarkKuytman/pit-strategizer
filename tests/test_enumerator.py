"""Behavioural tests for the rule-based candidate enumerator (ADR-0002).

Every assertion goes through the public ``enumerate_candidates`` surface. The
enumerator's contract is what a scenario author relies on: a finite set of
legal strategy options, ordered structurally and never scored by outcome.
"""

from __future__ import annotations

import re

from pit_strategizer.domain import (
    CandidateSet,
    Compound,
    Enumeration,
    RaceContext,
    RaceState,
    Rival,
    SubjectCar,
)
from pit_strategizer.enumerator import enumerate_candidates

CANONICAL_ID = re.compile(r"^(0STOP|[12]STOP(-L\d+[SMH])+)$")


def make_race_state(
    *,
    subject_compound: Compound = Compound.MEDIUM,
    rival_compounds: tuple[Compound, ...] = (Compound.SOFT, Compound.HARD),
    lap: int | None = None,
    total_laps: int = 58,
) -> RaceState:
    return RaceState(
        subject=SubjectCar(
            driver="VER",
            position=2,
            compound=subject_compound,
            tyre_age=12,
        ),
        rivals=tuple(
            Rival(driver=f"R{index}", compound=compound, tyre_age=10, gap_s=float(index))
            for index, compound in enumerate(rival_compounds)
        ),
        context=RaceContext(
            lap=total_laps // 2 if lap is None else lap,
            total_laps=total_laps,
            track_temp_c=41.0,
            pit_loss_s=22.0,
        ),
    )


def test_no_stop_option_is_always_included() -> None:
    result = enumerate_candidates(make_race_state(), Enumeration(max_stops=2, pit_lap_grid=3))

    assert "0STOP" in result.ids


def test_max_stops_zero_yields_only_the_no_stop_option() -> None:
    result = enumerate_candidates(make_race_state(), Enumeration(max_stops=0, pit_lap_grid=3))

    assert result.ids == ("0STOP",)


def test_options_never_exceed_max_stops() -> None:
    for max_stops in (0, 1, 2):
        result = enumerate_candidates(
            make_race_state(), Enumeration(max_stops=max_stops, pit_lap_grid=3)
        )

        assert all(option.stop_count <= max_stops for option in result)


def test_every_pit_lap_lies_on_the_grid_and_within_the_race() -> None:
    race_state = make_race_state(lap=1, total_laps=10)
    enumeration = Enumeration(max_stops=2, pit_lap_grid=3)

    result = enumerate_candidates(race_state, enumeration)

    laps = [stop.lap for option in result for stop in option.stops]
    assert set(laps) == {3, 6, 9}
    assert all(lap % enumeration.pit_lap_grid == 0 for lap in laps)
    assert all(1 <= lap <= race_state.context.total_laps for lap in laps)


def test_no_option_pits_before_the_decision_lap() -> None:
    race_state = make_race_state(lap=5, total_laps=20)

    result = enumerate_candidates(race_state, Enumeration(max_stops=2, pit_lap_grid=3))

    laps = [stop.lap for option in result for stop in option.stops]
    assert laps
    assert min(laps) >= race_state.context.lap


def test_a_stop_on_the_decision_lap_is_offered() -> None:
    race_state = make_race_state(lap=6, total_laps=20)

    result = enumerate_candidates(race_state, Enumeration(max_stops=1, pit_lap_grid=3))

    assert "1STOP-L6S" in result.ids


def test_two_decision_laps_produce_different_candidate_sets() -> None:
    enumeration = Enumeration(max_stops=2, pit_lap_grid=3)

    early = enumerate_candidates(make_race_state(lap=6, total_laps=12), enumeration)
    late = enumerate_candidates(make_race_state(lap=9, total_laps=12), enumeration)

    assert early.ids != late.ids
    assert set(late.ids) < set(early.ids)


def test_compounds_are_derived_as_the_union_of_those_in_use() -> None:
    race_state = make_race_state(
        subject_compound=Compound.SOFT,
        rival_compounds=(Compound.MEDIUM,),
    )

    result = enumerate_candidates(race_state, Enumeration(max_stops=2, pit_lap_grid=3))

    used = {stop.compound for option in result for stop in option.stops}
    assert used == {Compound.SOFT, Compound.MEDIUM}
    assert Compound.HARD not in used


def test_subject_compound_is_available_even_without_rivals() -> None:
    race_state = make_race_state(subject_compound=Compound.HARD, rival_compounds=())

    result = enumerate_candidates(race_state, Enumeration(max_stops=1, pit_lap_grid=3))

    used = {stop.compound for option in result for stop in option.stops}
    assert used == {Compound.HARD}


def test_ids_are_canonical_and_unique() -> None:
    result = enumerate_candidates(
        make_race_state(total_laps=10), Enumeration(max_stops=2, pit_lap_grid=3)
    )

    assert len(set(result.ids)) == len(result.ids)
    assert all(CANONICAL_ID.match(option_id) for option_id in result.ids)


def test_canonical_two_stop_id_matches_the_glossary_example() -> None:
    race_state = make_race_state(
        subject_compound=Compound.MEDIUM,
        rival_compounds=(Compound.HARD,),
        lap=1,
        total_laps=58,
    )

    result = enumerate_candidates(race_state, Enumeration(max_stops=2, pit_lap_grid=18))

    assert "2STOP-L18M-L36H" in result.ids


def test_ordering_is_fewest_stops_then_structural() -> None:
    result = enumerate_candidates(
        make_race_state(lap=1, total_laps=10), Enumeration(max_stops=2, pit_lap_grid=3)
    )

    counts = [option.stop_count for option in result]
    assert counts == sorted(counts)
    assert result.ids[0] == "0STOP"

    one_stops = [option.id for option in result if option.stop_count == 1]
    assert one_stops == [
        "1STOP-L3S",
        "1STOP-L3M",
        "1STOP-L3H",
        "1STOP-L6S",
        "1STOP-L6M",
        "1STOP-L6H",
        "1STOP-L9S",
        "1STOP-L9M",
        "1STOP-L9H",
    ]

    two_stops = [option.id for option in result if option.stop_count == 2]
    assert two_stops[0] == "2STOP-L3S-L6S"
    assert two_stops[3] == "2STOP-L3S-L9S"
    assert two_stops[-1] == "2STOP-L6H-L9H"


def test_two_stop_enumeration_is_complete() -> None:
    result = enumerate_candidates(
        make_race_state(lap=1, total_laps=10), Enumeration(max_stops=2, pit_lap_grid=3)
    )

    assert len(result) == 1 + 3 * 3 + 3 * 9


def test_grid_with_no_legal_pit_lap_yields_only_no_stop() -> None:
    result = enumerate_candidates(
        make_race_state(total_laps=2), Enumeration(max_stops=2, pit_lap_grid=5)
    )

    assert result.ids == ("0STOP",)


def test_enumeration_is_deterministic() -> None:
    race_state = make_race_state()
    enumeration = Enumeration(max_stops=2, pit_lap_grid=3)

    first = enumerate_candidates(race_state, enumeration)
    second = enumerate_candidates(race_state, enumeration)

    assert first.ids == second.ids


def test_only_legal_strategy_options_are_produced() -> None:
    race_state = make_race_state(
        subject_compound=Compound.MEDIUM,
        rival_compounds=(Compound.SOFT,),
    )
    enumeration = Enumeration(max_stops=2, pit_lap_grid=4)
    available = {Compound.MEDIUM, Compound.SOFT}

    result = enumerate_candidates(race_state, enumeration)

    assert isinstance(result, CandidateSet)
    for option in result:
        laps = [stop.lap for stop in option.stops]
        assert option.stop_count <= enumeration.max_stops
        assert laps == sorted(laps)
        assert len(set(laps)) == len(laps)
        assert all(lap % enumeration.pit_lap_grid == 0 for lap in laps)
        assert all(1 <= lap <= race_state.context.total_laps for lap in laps)
        assert all(stop.compound in available for stop in option.stops)
