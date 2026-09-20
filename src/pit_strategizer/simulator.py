"""The deterministic ground-truth lap-time simulator (ADR-0001).

The simulator scores a scenario's candidate set by total race time over one
hard-coded circuit profile. It is deliberately small and deterministic: the
constants are invented, so absolute lap times are not real-world predictions and
only relative comparisons between strategy options are meaningful.

The model, in full
------------------

The simulator scores only the part of the race still to be run at the decision
moment: from ``RaceContext.lap`` to ``RaceContext.total_laps`` inclusive. The
subject enters that remaining race on its current compound with
``SubjectCar.tyre_age`` laps already on the tyre, so the decision moment is
load-bearing rather than decorative.

A stint's ``tyre_age`` on a lap is the number of laps completed on that set: the
subject's ``tyre_age`` on ``RaceContext.lap``, one more on the next lap, and so
on. A stop on lap ``L`` ends the outgoing stint on lap ``L`` (which is still
driven on its old tyres), costs the pit loss once, and the new compound is first
used on lap ``L + 1``. A no-stop option is therefore a single stint continuing
from the decision moment.

The lap time on lap ``lap``, on a tyre of ``tyre_age``, with ``laps_remaining``
laps still to run (including the current one) is::

    lap_time = BASE_LAP_S
             + DEGRADATION_S_PER_LAP[compound] * tyre_age
             + FUEL_BURN_S_PER_LAP * laps_remaining
             + cliff_penalty(tyre_age, compound)

where the cliff penalty is zero up to and including the compound's cliff age and
grows quadratically beyond it, capped so one absurd stint cannot dominate::

    cliff_penalty = min(CLIFF_PENALTY_S * max(0, tyre_age - CLIFF_TYRE_AGE[compound]) ** 2,
                        CLIFF_CAP_S)

The quadratic makes the fall-off sharp rather than a slightly steeper slope: the
first lap past the cliff adds ``CLIFF_PENALTY_S`` (1.0 s) and the next 4.0 s.
``CLIFF_CAP_S`` truncates the tail at 5.0 s. It cannot change the optimum or the
ordering of options that stay at or near the cliff; it only reorders options
already deep in the tail, so no single absurd stint can dominate time lost. The
fuel term uses the absolute lap number, ``laps_remaining = total_laps - lap + 1``,
so fuel still falls over the remaining race.

When ``RaceContext.safety_car`` is true the pit loss charged per stop is
multiplied by ``SAFETY_CAR_PIT_LOSS_FACTOR``, making a stop unusually cheap.

The total race time of an option is the sum of its lap times plus the pit loss
for each stop::

    total = effective_pit_loss * len(stops)
          + sum(lap_time(lap, age(lap), compound(lap), total_laps - lap + 1)
                for lap in context.lap..total_laps)

Only ``SubjectCar.compound``, ``SubjectCar.tyre_age`` and the ``RaceContext``
fields ``lap``, ``total_laps``, ``pit_loss_s`` and ``safety_car`` enter the
model. ``RaceContext.track_temp_c`` is rendering-only: it is carried on the race
state for the strategist's request and the report, and does not affect any lap
time. The subject's gaps and last lap times, and every rival attribute, are
likewise for rendering only.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from pit_strategizer.domain import (
    CandidateSet,
    Compound,
    RaceContext,
    RaceState,
    Stop,
    StrategyOption,
)

__all__ = [
    "BASE_LAP_S",
    "CLIFF_CAP_S",
    "CLIFF_PENALTY_S",
    "CLIFF_TYRE_AGE",
    "DEGRADATION_S_PER_LAP",
    "FUEL_BURN_S_PER_LAP",
    "SAFETY_CAR_PIT_LOSS_FACTOR",
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

CLIFF_CAP_S: Final[float] = 5.0
"""Cap on the per-lap cliff penalty; truncates the tail so no stint dominates."""

SAFETY_CAR_PIT_LOSS_FACTOR: Final[float] = 0.5
"""Multiplier on the pit loss when the safety car is out, making a stop cheaper."""


def _cliff_penalty(tyre_age: int, compound: Compound) -> float:
    """Quadratic penalty for running a tyre past its cliff, capped at ``CLIFF_CAP_S``.

    Zero up to and including the compound's cliff age. The cap leaves the optimum
    and the ordering of options that stay at or near the cliff untouched; it only
    truncates the tail, so no single absurd stint can dominate time lost.
    """
    laps_past = max(0, tyre_age - CLIFF_TYRE_AGE[compound])
    return min(CLIFF_PENALTY_S * laps_past**2, CLIFF_CAP_S)


def _effective_pit_loss(context: RaceContext) -> float:
    """Return the pit loss charged per stop at this decision moment.

    A safety car halves the pit loss (``SAFETY_CAR_PIT_LOSS_FACTOR``), so a stop
    under neutralisation is unusually cheap.
    """
    if context.safety_car:
        return context.pit_loss_s * SAFETY_CAR_PIT_LOSS_FACTOR
    return context.pit_loss_s


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
    race_state: RaceState,
) -> tuple[int, Compound]:
    """Return the tyre age and compound in use on ``lap``.

    The subject enters the remaining race on its current compound with
    ``SubjectCar.tyre_age`` laps on the tyre at ``RaceContext.lap``, so the
    initial stint's age is measured from ``context.lap - subject.tyre_age``. A
    stop on lap ``L`` only takes effect from lap ``L + 1``: the stop lap itself
    is still run on the outgoing stint's tyres.
    """
    subject = race_state.subject
    compound = subject.compound
    reset_lap = race_state.context.lap - subject.tyre_age
    for stop in stops:
        if stop.lap < lap:
            compound = stop.compound
            reset_lap = stop.lap
        else:
            break
    return lap - reset_lap, compound


def _option_total_time(option: StrategyOption, race_state: RaceState) -> float:
    """Return one option's total race time over the laps remaining at the decision moment."""
    context = race_state.context
    # ``RaceContext.lap`` may be 0 (before the first lap); scoring cannot start
    # before lap 1, and the first stint's age is still measured from the decision
    # moment, so a degenerate lap 0 simply gains a lap of tyre age.
    first_lap = max(1, context.lap)

    total = _effective_pit_loss(context) * option.stop_count
    for lap in range(first_lap, context.total_laps + 1):
        tyre_age, compound = _tyre_age_and_compound(lap, option.stops, race_state)
        total += lap_time(lap, tyre_age, compound, context.total_laps - lap + 1)
    return total


def _check_stops_are_within_the_race(option: StrategyOption, total_laps: int) -> None:
    for stop in option.stops:
        if stop.lap > total_laps:
            raise ValueError(
                f"option {option.id!r} pits on lap {stop.lap}, beyond the "
                f"{total_laps}-lap race"
            )


def simulate(race_state: RaceState, candidates: CandidateSet) -> SimResult:
    """Rank ``candidates`` by total race time over the laps remaining at the decision moment.

    Pure and deterministic: the result depends only on ``race_state`` and
    ``candidates``, and repeated calls are identical.
    """
    times: dict[str, float] = {}
    for option in candidates:
        _check_stops_are_within_the_race(option, race_state.context.total_laps)
        times[option.id] = _option_total_time(option, race_state)

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
