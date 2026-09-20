"""The strategist seam and the scripted strategists that stand in for Jev.

A :class:`Strategist` maps a :class:`~pit_strategizer.domain.Scenario` to a
:class:`~pit_strategizer.domain.Recommendation`. The strategists under test
differ only in how they render the race state (ADR-0003); the scripted
strategists here differ in *what they choose*, which makes them useful fixtures:
they exercise the evaluation seam end to end before a Jev-backed strategist
exists.

Each scripted strategist still enumerates its scenario's candidate set by rule
and consults the ground-truth simulator only to pick or verify an option
(ADR-0002). The recommendation it returns is an ordinary one: a deterministic
one-hot probability distribution over the selected option, carried with
confidence 1.0, so repeated runs are identical.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pit_strategizer.domain import Recommendation, Scenario
from pit_strategizer.enumerator import enumerate_candidates
from pit_strategizer.simulator import simulate

__all__ = [
    "FixedStrategist",
    "PerfectStrategist",
    "Strategist",
    "WorstStrategist",
]


@runtime_checkable
class Strategist(Protocol):
    """Maps a scenario to a recommendation, labelled for the report.

    ``name`` labels the strategist in a
    :class:`~pit_strategizer.evaluator.Report`; ``recommend`` may use anything in
    the scenario. The protocol is deliberately minimal so Jev-backed and scripted
    strategists are interchangeable at the evaluation seam.
    """

    name: str

    def recommend(self, scenario: Scenario) -> Recommendation:
        """Return this strategist's recommendation for ``scenario``."""
        ...


def _one_hot(option_id: str) -> Recommendation:
    """Recommend ``option_id`` deterministically with confidence 1.0."""
    return Recommendation(
        option_id=option_id,
        confidence=1.0,
        probabilities={option_id: 1.0},
    )


@dataclass(frozen=True)
class PerfectStrategist:
    """Recommends the ground-truth simulator's optimum, losing no time.

    It picks ``SimResult.best_option_id`` after enumerating the candidate set, so
    ``evaluate`` scores it at zero time lost on every scenario.
    """

    name: str = "perfect"

    def recommend(self, scenario: Scenario) -> Recommendation:
        candidates = enumerate_candidates(scenario.race_state, scenario.enumeration)
        result = simulate(scenario.race_state, candidates)
        return _one_hot(result.best_option_id)


@dataclass(frozen=True)
class WorstStrategist:
    """Recommends the slowest option, losing the candidate set's full spread.

    It picks the last entry of ``SimResult.ranking()`` — the option with the
    greatest total race time — so its time lost is the largest in the candidate
    set.
    """

    name: str = "worst"

    def recommend(self, scenario: Scenario) -> Recommendation:
        candidates = enumerate_candidates(scenario.race_state, scenario.enumeration)
        result = simulate(scenario.race_state, candidates)
        slowest, _ = result.ranking()[-1]
        return _one_hot(slowest.id)


@dataclass(frozen=True)
class FixedStrategist:
    """Recommends a configured option id when the scenario offers it.

    It pins an exact expected time lost for tests. When the configured id is not
    part of the scenario's candidate set it raises ``ValueError`` naming the
    strategist, the scenario and the option, rather than returning a
    recommendation the evaluator cannot score.
    """

    option_id: str
    name: str = "fixed"

    def recommend(self, scenario: Scenario) -> Recommendation:
        candidates = enumerate_candidates(scenario.race_state, scenario.enumeration)
        if self.option_id not in candidates.ids:
            raise ValueError(
                f"fixed strategist {self.name!r} recommends option "
                f"{self.option_id!r}, which is not in the candidate set of "
                f"scenario {scenario.id!r}"
            )
        return _one_hot(self.option_id)
