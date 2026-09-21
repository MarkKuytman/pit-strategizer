"""Core domain types for the pit strategizer.

The vocabulary here is authoritative in CONTEXT.md; code, tests and reports use
those terms. Every type is a frozen dataclass: a decision moment is a value, not
a mutable object.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = [
    "CandidateSet",
    "Compound",
    "Enumeration",
    "RaceContext",
    "RaceState",
    "Recommendation",
    "Rival",
    "Scenario",
    "Stop",
    "StrategyOption",
    "SubjectCar",
    "TimeLost",
]


class Compound(str, Enum):
    """The tyre specification in use, trading pace against durability."""

    SOFT = "soft"
    MEDIUM = "medium"
    HARD = "hard"

    @property
    def code(self) -> str:
        """Single-letter code used in canonical option ids."""
        return self.name[0]


@dataclass(frozen=True)
class Stop:
    """A single pit stop: the lap it happens on and the compound fitted."""

    lap: int
    compound: Compound

    def __post_init__(self) -> None:
        if self.lap < 1:
            raise ValueError(f"stop lap must be >= 1, got {self.lap}")


@dataclass(frozen=True)
class StrategyOption:
    """One member of a candidate set, describing the pit stops it makes in lap order.

    With no stops the option is a no-stop option. ``id`` is the canonical handle
    used across the Jev request, the evaluator and the report, for example
    ``2STOP-L18M-L36H``.
    """

    stops: tuple[Stop, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "stops", tuple(self.stops))
        laps = [stop.lap for stop in self.stops]
        if laps != sorted(laps) or len(set(laps)) != len(laps):
            raise ValueError(f"stop laps must be strictly increasing, got {laps}")

    @property
    def stop_count(self) -> int:
        return len(self.stops)

    @property
    def id(self) -> str:
        if not self.stops:
            return "0STOP"
        stops = "".join(f"-L{stop.lap}{stop.compound.code}" for stop in self.stops)
        return f"{self.stop_count}STOP{stops}"


@dataclass(frozen=True)
class SubjectCar:
    """The car the decision is being made for."""

    driver: str
    position: int
    compound: Compound
    tyre_age: int
    last_lap_times_s: tuple[float, ...] = ()
    gap_ahead_s: float | None = None
    gap_behind_s: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "last_lap_times_s", tuple(self.last_lap_times_s))
        if self.position < 1:
            raise ValueError(f"position must be >= 1, got {self.position}")
        if self.tyre_age < 0:
            raise ValueError(f"tyre age must be >= 0, got {self.tyre_age}")


@dataclass(frozen=True)
class Rival:
    """A nearby car the strategist must consider.

    ``gap_s`` is signed: positive means the rival is ahead of the subject car.
    """

    driver: str
    compound: Compound
    tyre_age: int
    gap_s: float
    position: int | None = None

    def __post_init__(self) -> None:
        if self.tyre_age < 0:
            raise ValueError(f"tyre age must be >= 0, got {self.tyre_age}")


@dataclass(frozen=True)
class RaceContext:
    """The race circumstances around a decision moment.

    ``track_temp_c`` is rendering-only: it is carried for the strategist's
    request and the report but does not enter the ground-truth lap-time model
    (see ``pit_strategizer.simulator``).
    """

    lap: int
    total_laps: int
    track_temp_c: float
    pit_loss_s: float
    safety_car: bool = False

    def __post_init__(self) -> None:
        if self.total_laps < 1:
            raise ValueError(f"total laps must be >= 1, got {self.total_laps}")
        if not 0 <= self.lap <= self.total_laps:
            raise ValueError(f"lap must be within 0..{self.total_laps}, got {self.lap}")
        if self.pit_loss_s < 0:
            raise ValueError(f"pit loss must be >= 0, got {self.pit_loss_s}")

    @property
    def laps_remaining(self) -> int:
        return self.total_laps - self.lap


@dataclass(frozen=True)
class RaceState:
    """The facts about a decision moment a strategist may use."""

    subject: SubjectCar
    rivals: tuple[Rival, ...]
    context: RaceContext

    def __post_init__(self) -> None:
        object.__setattr__(self, "rivals", tuple(self.rivals))


@dataclass(frozen=True)
class Enumeration:
    """Rule parameters bounding a scenario's candidate set (see ADR-0002).

    ``pit_lap_grid`` is the spacing, in laps, of the allowed pit laps.
    """

    max_stops: int
    pit_lap_grid: int

    def __post_init__(self) -> None:
        if not 0 <= self.max_stops <= 2:
            raise ValueError(f"the prototype enumerates at most two stops, got {self.max_stops}")
        if self.pit_lap_grid < 1:
            raise ValueError(f"pit lap grid must be >= 1, got {self.pit_lap_grid}")


@dataclass(frozen=True)
class Scenario:
    """A single pit-decision moment: a race state and its enumeration parameters.

    The candidate set and the ground truth are not stored here: the enumerator
    derives the candidates by rule (ADR-0002) and the simulator derives the
    ranking (ADR-0001).
    """

    id: str
    archetype: str
    race_state: RaceState
    enumeration: Enumeration


@dataclass(frozen=True)
class CandidateSet:
    """The finite set of strategy options a scenario offers.

    Options are held in enumeration order and are never ranked or filtered by
    the ground-truth simulator: pre-filtering would leak the answer into the
    input (ADR-0002).
    """

    options: tuple[StrategyOption, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "options", tuple(self.options))
        if not self.options:
            raise ValueError("a candidate set must offer at least one option")
        ids = [option.id for option in self.options]
        if len(set(ids)) != len(ids):
            raise ValueError(f"candidate set contains duplicate option ids: {ids}")

    def __iter__(self) -> Iterator[StrategyOption]:
        return iter(self.options)

    def __len__(self) -> int:
        return len(self.options)

    def __contains__(self, option: object) -> bool:
        return option in self.options

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(option.id for option in self.options)

    def by_id(self, option_id: str) -> StrategyOption:
        for option in self.options:
            if option.id == option_id:
                return option
        raise KeyError(f"no option with id {option_id!r} in candidate set")


@dataclass(frozen=True)
class Recommendation:
    """What a strategist recommends: the selected option plus the distribution it reported.

    ``raw`` is the underlying Jev response, kept only for debugging and fixtures.
    """

    option_id: str
    confidence: float
    probabilities: Mapping[str, float] = field(default_factory=dict)
    raw: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be within 0..1, got {self.confidence}")
        for option_id, probability in self.probabilities.items():
            if not 0.0 <= probability <= 1.0:
                raise ValueError(f"probability for {option_id!r} must be within 0..1, got {probability}")
        if self.probabilities and self.option_id not in self.probabilities:
            raise ValueError(
                f"selected option {self.option_id!r} is missing from the probability distribution"
            )

    def probability_of(self, option_id: str) -> float:
        return self.probabilities.get(option_id, 0.0)


@dataclass(frozen=True)
class TimeLost:
    """Seconds lost by the selected option relative to the simulator's optimum.

    Zero when the optimum is chosen.
    """

    seconds: float

    def __post_init__(self) -> None:
        if self.seconds < 0:
            raise ValueError(f"time lost cannot be negative, got {self.seconds}")

    @property
    def is_optimal(self) -> bool:
        return self.seconds == 0.0
