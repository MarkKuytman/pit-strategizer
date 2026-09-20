"""The deterministic ground-truth lap-time simulator (ADR-0001).

The simulator scores a scenario's candidate set by total race time over one
hard-coded circuit profile. It is deliberately small and deterministic: the
constants are invented, so absolute lap times are not real-world predictions and
only relative comparisons between strategy options are meaningful.

The model, in full
------------------

A race runs from lap 1 to ``RaceContext.total_laps`` inclusive. Every option
starts on the subject car's compound but on fresh tyres: the subject's current
``tyre_age`` and ``RaceContext.lap`` describe the decision moment for rendering
and enumeration, not the simulation start.

A stint's ``tyre_age`` on a lap is the number of laps completed on that set:
1 on a stint's first lap, 2 on its second, and so on. A stop on lap ``L`` ends
the outgoing stint on lap ``L`` (which is still driven on its old tyres), costs
the pit loss once, and the new compound is first used on lap ``L + 1``. A
no-stop option is therefore a single stint from lap 1.

The lap time on lap ``lap``, on a tyre of ``tyre_age``, with ``laps_remaining``
laps still to run (including the current one) is::

    lap_time = BASE_LAP_S
             + DEGRADATION_S_PER_LAP[compound] * tyre_age
             + FUEL_BURN_S_PER_LAP * laps_remaining
             + cliff_penalty(tyre_age, compound)

where the cliff penalty is zero up to and including the compound's cliff age and
grows quadratically beyond it::

    cliff_penalty = CLIFF_PENALTY_S * max(0, tyre_age - CLIFF_TYRE_AGE[compound]) ** 2

The quadratic makes the fall-off sharp rather than a slightly steeper slope: the
first lap past the cliff adds ``CLIFF_PENALTY_S`` (1.0 s), the next 4.0 s, then
9.0 s. The fuel term falls as the race runs down, so early laps are slower; the
simulator passes ``laps_remaining = total_laps - lap + 1``.

The total race time of an option is the sum of its lap times plus the pit loss
for each stop::

    total = pit_loss_s * len(stops)
          + sum(lap_time(lap, age(lap), compound(lap), total_laps - lap + 1)
                for lap in 1..total_laps)
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from pit_strategizer.domain import (
    CandidateSet,
    Compound,
    RaceState,
    Stop,
    StrategyOption,
)

__all__ = [
    "BASE_LAP_S",
    "CLIFF_PENALTY_S",
    "CLIFF_TYRE_AGE",
    "DEGRADATION_S_PER_LAP",
    "FUEL_BURN_S_PER_LAP",
    "SimResult",
    "lap_time",
    "simulate",
]

BASE_LAP_S: Final[float] = 90.0
"""Seconds for a fresh-tyre lap with no fuel and no degradation."""

DEGRADATION_S_PER_LAP: Final[Mapping[Compound, float]] = MappingProxyType(
    {
        Compound.SOFT: 0.12,
        Compound.MEDIUM: 0.08,
        Compound.HARD: 0.05,
    }
)
"""Seconds added per lap of tyre age, by compound."""

CLIFF_TYRE_AGE: Final[Mapping[Compound, int]] = MappingProxyType(
    {
        Compound.SOFT: 18,
        Compound.MEDIUM: 26,
        Compound.HARD: 34,
    }
)
"""Tyre age beyond which lap times fall away sharply, by compound."""

FUEL_BURN_S_PER_LAP: Final[float] = 0.03
"""Seconds per lap of fuel carried; the fuel load falls as the race runs down."""

CLIFF_PENALTY_S: Final[float] = 1.0
"""Seconds per squared lap beyond the cliff; makes the fall-off sharp."""


def _cliff_penalty(tyre_age: int, compound: Compound) -> float:
    """Quadratic penalty for running a tyre past its cliff; zero up to the cliff."""
    laps_past = max(0, tyre_age - CLIFF_TYRE_AGE[compound])
    return CLIFF_PENALTY_S * laps_past**2


def lap_time(lap: int, tyre_age: int, compound: Compound, laps_remaining: int) -> float:
    """Return the seconds for one lap under the ground-truth model.

    ``lap`` is the 1-indexed lap number the time is for and ``laps_remaining``
    counts the laps still to run including this one; together they position the
    lap in the race. ``tyre_age`` is the laps completed on ``compound``.
    """
    if lap < 1:
        raise ValueError(f"lap must be >= 1, got {lap}")
    return (
        BASE_LAP_S
        + DEGRADATION_S_PER_LAP[compound] * tyre_age
        + FUEL_BURN_S_PER_LAP * laps_remaining
        + _cliff_penalty(tyre_age, compound)
    )


def _tyre_age_and_compound(
    lap: int,
    stops: tuple[Stop, ...],
    start_compound: Compound,
) -> tuple[int, Compound]:
    """Return the tyre age and compound in use on ``lap``.

    A stop on lap ``L`` only takes effect from lap ``L + 1``: the stop lap itself
    is still run on the outgoing stint's tyres.
    """
    compound = start_compound
    reset_lap = 0
    for stop in stops:
        if stop.lap < lap:
            compound = stop.compound
            reset_lap = stop.lap
        else:
            break
    return lap - reset_lap, compound


def _option_total_time(
    option: StrategyOption,
    start_compound: Compound,
    total_laps: int,
    pit_loss_s: float,
) -> float:
    """Return one option's total race time in seconds."""
    total = pit_loss_s * option.stop_count
    for lap in range(1, total_laps + 1):
        tyre_age, compound = _tyre_age_and_compound(lap, option.stops, start_compound)
        total += lap_time(lap, tyre_age, compound, total_laps - lap + 1)
    return total


def _check_stops_are_within_the_race(option: StrategyOption, total_laps: int) -> None:
    for stop in option.stops:
        if stop.lap > total_laps:
            raise ValueError(
                f"option {option.id!r} pits on lap {stop.lap}, beyond the "
                f"{total_laps}-lap race"
            )


def simulate(race_state: RaceState, candidates: CandidateSet) -> SimResult:
    """Rank ``candidates`` by total race time over the scenario's race.

    Pure and deterministic: the result depends only on ``race_state`` and
    ``candidates``, and repeated calls are identical.
    """
    context = race_state.context
    start_compound = race_state.subject.compound

    times: dict[str, float] = {}
    for option in candidates:
        _check_stops_are_within_the_race(option, context.total_laps)
        times[option.id] = _option_total_time(
            option,
            start_compound,
            context.total_laps,
            context.pit_loss_s,
        )

    return SimResult(times=times, candidates=candidates)


@dataclass(frozen=True)
class SimResult:
    """The simulator's verdict on a candidate set: every option's total race time.

    ``times`` maps option id to total race time in seconds. ``candidates`` is the
    candidate set the times were computed for, so callers can recover the whole
    ``StrategyOption`` behind an id.
    """

    times: Mapping[str, float]
    candidates: CandidateSet

    def __post_init__(self) -> None:
        object.__setattr__(self, "times", MappingProxyType(dict(self.times)))
        missing = [option.id for option in self.candidates if option.id not in self.times]
        if missing:
            raise ValueError(f"no simulated time for option ids: {missing}")

    @property
    def best_option_id(self) -> str:
        """The id of the fastest option; ties resolve to candidate order."""
        return min(self.candidates, key=lambda option: self.times[option.id]).id

    @property
    def best_time_s(self) -> float:
        """The fastest option's total race time in seconds."""
        return self.times[self.best_option_id]

    @property
    def best_option(self) -> StrategyOption:
        """The fastest option itself."""
        return self.candidates.by_id(self.best_option_id)

    def by_id(self, option_id: str) -> StrategyOption:
        """Recover the option behind ``option_id``; raises ``KeyError`` if unknown."""
        return self.candidates.by_id(option_id)

    def time_lost_s(self, option_id: str) -> float:
        """Seconds ``option_id`` loses to the optimum; 0.0 for the optimum.

        Raises ``KeyError`` if the id is not part of the candidate set.
        """
        if option_id not in self.times:
            raise KeyError(option_id)
        return self.times[option_id] - self.best_time_s

    def ranking(self) -> tuple[tuple[StrategyOption, float], ...]:
        """Options paired with their total time, ascending; ties keep candidate order."""
        ordered = sorted(
            ((option, self.times[option.id]) for option in self.candidates),
            key=lambda pair: pair[1],
        )
        return tuple(ordered)
