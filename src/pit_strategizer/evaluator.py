"""Score strategists against the ground-truth simulator.

``evaluate`` is the experiment's seam. For every scenario it enumerates the
candidate set by rule — never pre-filtered or pre-ranked by the simulator
(ADR-0002) — ranks it with the deterministic simulator (ADR-0001), then asks
each strategist for a recommendation and records the time lost relative to the
simulator's optimum. The outcome is a :class:`Report`, a pure value that later
code can print without recomputing anything.

The vocabulary follows CONTEXT.md: a strategist maps a scenario to a
recommendation, and time lost is the selected option's seconds behind the
optimum, zero when optimal.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from pit_strategizer.domain import Scenario
from pit_strategizer.enumerator import enumerate_candidates
from pit_strategizer.simulator import simulate
from pit_strategizer.strategists import Strategist

__all__ = ["Outcome", "Report", "evaluate"]


@dataclass(frozen=True)
class Outcome:
    """One strategist's result on one scenario.

    ``time_lost_s`` is the selected option's seconds behind the simulator's
    optimum; ``is_optimal`` is true exactly when that is zero. ``confidence`` is
    copied from the recommendation so the report can show it without holding the
    recommendation itself.
    """

    strategist_name: str
    scenario_id: str
    option_id: str
    time_lost_s: float
    confidence: float

    def __post_init__(self) -> None:
        if self.time_lost_s < 0.0:
            raise ValueError(f"time lost cannot be negative, got {self.time_lost_s}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be within 0..1, got {self.confidence}")

    @property
    def is_optimal(self) -> bool:
        """True when the selected option is the simulator's optimum."""
        return self.time_lost_s == 0.0


@dataclass(frozen=True)
class Report:
    """The evaluator's verdict on a set of strategists over a set of scenarios.

    ``outcomes`` holds one :class:`Outcome` per (strategist, scenario) pair, in
    scenario-major order: scenarios in the order evaluated, and within each
    scenario, strategists in the order passed to :func:`evaluate`.
    ``strategists`` and ``scenarios`` hold the labels and scenario ids in that
    same order, so a table can be rendered without recomputing or re-simulating.

    ``mean_time_lost_s`` averages over every outcome, and
    ``mean_time_lost_by_strategist`` averages per strategist. Both treat an empty
    set of outcomes as ``0.0``, which is the only value the prototype's
    aggregate can take before any scenario has been evaluated.
    """

    outcomes: tuple[Outcome, ...]
    strategists: tuple[str, ...] = ()
    scenarios: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcomes", tuple(self.outcomes))
        object.__setattr__(self, "strategists", tuple(self.strategists))
        object.__setattr__(self, "scenarios", tuple(self.scenarios))

    @property
    def mean_time_lost_s(self) -> float:
        """Mean time lost over every outcome."""
        return _mean(outcome.time_lost_s for outcome in self.outcomes)

    @property
    def mean_time_lost_by_strategist(self) -> Mapping[str, float]:
        """Mean time lost per strategist, keyed by ``strategist_name``."""
        grouped: dict[str, list[float]] = {name: [] for name in self.strategists}
        for outcome in self.outcomes:
            grouped.setdefault(outcome.strategist_name, []).append(outcome.time_lost_s)
        return {name: _mean(values) for name, values in grouped.items()}

    def outcomes_for(self, strategist_name: str) -> tuple[Outcome, ...]:
        """Every outcome for ``strategist_name``, in evaluation order."""
        return tuple(
            outcome
            for outcome in self.outcomes
            if outcome.strategist_name == strategist_name
        )

    def outcome_for(self, strategist_name: str, scenario_id: str) -> Outcome:
        """The outcome for one (strategist, scenario) pair.

        Raises ``KeyError`` if the report holds no such outcome.
        """
        for outcome in self.outcomes:
            if (
                outcome.strategist_name == strategist_name
                and outcome.scenario_id == scenario_id
            ):
                return outcome
        raise KeyError(
            f"no outcome for strategist {strategist_name!r} on scenario {scenario_id!r}"
        )


def evaluate(
    strategists: Sequence[Strategist],
    scenarios: Sequence[Scenario],
) -> Report:
    """Score every strategist on every scenario and return a :class:`Report`.

    Each scenario's candidate set is enumerated by rule and ranked once with the
    ground-truth simulator; the strategists are then asked for a recommendation
    and scored against that ranking. A strategist that recommends an option
    outside the scenario's candidate set raises ``ValueError`` naming the
    strategist, the scenario and the option.
    """
    ordered_strategists = tuple(strategists)
    ordered_scenarios = tuple(scenarios)

    outcomes: list[Outcome] = []
    for scenario in ordered_scenarios:
        candidates = enumerate_candidates(scenario.race_state, scenario.enumeration)
        result = simulate(scenario.race_state, candidates)

        for strategist in ordered_strategists:
            recommendation = strategist.recommend(scenario)
            option_id = recommendation.option_id
            if option_id not in result.times:
                raise ValueError(
                    f"strategist {strategist.name!r} recommended option "
                    f"{option_id!r}, which is not in the candidate set of "
                    f"scenario {scenario.id!r}"
                )
            outcomes.append(
                Outcome(
                    strategist_name=strategist.name,
                    scenario_id=scenario.id,
                    option_id=option_id,
                    time_lost_s=result.time_lost_s(option_id),
                    confidence=recommendation.confidence,
                )
            )

    return Report(
        outcomes=tuple(outcomes),
        strategists=tuple(strategist.name for strategist in ordered_strategists),
        scenarios=tuple(scenario.id for scenario in ordered_scenarios),
    )


def _mean(values: Iterable[float]) -> float:
    """Arithmetic mean of ``values``; ``0.0`` when there are none."""
    materialised = tuple(values)
    if not materialised:
        return 0.0
    return sum(materialised) / len(materialised)
