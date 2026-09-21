"""Load scenario files into the domain's :class:`~pit_strategizer.domain.Scenario`.

A scenario is a single pit-decision moment: a race state (the subject car, its
rivals and the race context) plus the enumeration parameters that bound its
candidate set. One scenario lives per JSON file at ``scenarios/<id>.json`` and
maps field-for-field onto the frozen domain dataclasses; this module is the only
place that knows the on-disk shape.

The vocabulary is defined in ``CONTEXT.md``. Malformed input raises
:class:`ScenarioError`, naming the scenario and the offending field so the file
can be fixed without guessing.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from pit_strategizer.domain import (
    Compound,
    Enumeration,
    RaceContext,
    RaceState,
    Rival,
    Scenario,
    SubjectCar,
)

__all__ = [
    "SCENARIOS_DIRNAME",
    "ScenarioError",
    "default_scenarios_directory",
    "load_scenario",
    "load_scenarios",
]

SCENARIOS_DIRNAME = "scenarios"

_MISSING = object()
_T = TypeVar("_T")

_COMPOUND_VALUES = tuple(compound.value for compound in Compound)
_COMPOUND_CHOICES = ", ".join(repr(value) for value in _COMPOUND_VALUES)

_SCENARIO_KEYS = ("id", "archetype", "race_state", "enumeration")
_RACE_STATE_KEYS = ("subject", "rivals", "context")
_SUBJECT_KEYS = (
    "driver",
    "position",
    "compound",
    "tyre_age",
    "last_lap_times_s",
    "gap_ahead_s",
    "gap_behind_s",
)
_RIVAL_KEYS = ("driver", "compound", "tyre_age", "gap_s", "position")
_CONTEXT_KEYS = ("lap", "total_laps", "track_temp_c", "pit_loss_s", "safety_car")
_ENUMERATION_KEYS = ("max_stops", "pit_lap_grid")


class ScenarioError(ValueError):
    """Raised when a scenario file cannot be parsed into a :class:`Scenario`."""


def default_scenarios_directory() -> Path:
    """The repo-root ``scenarios/`` directory that ships with the prototype."""
    return Path(__file__).resolve().parents[2] / SCENARIOS_DIRNAME


def load_scenario(path: str | Path) -> Scenario:
    """Load one scenario JSON file into a :class:`Scenario`.

    Raises :class:`ScenarioError` if the file is missing, empty, not valid JSON,
    or does not match the scenario shape.
    """
    path = Path(path)
    root = _read_object(_read_json(path), "<root>", _label(path, None))

    scenario_id = root.get("id")
    label = _label(path, scenario_id if isinstance(scenario_id, str) else None)
    _reject_unknown(root, _SCENARIO_KEYS, "<root>", label)

    return Scenario(
        id=_take_non_empty_str(root, "<root>", "id", label),
        archetype=_take_non_empty_str(root, "<root>", "archetype", label),
        race_state=_parse_race_state(_take_object(root, "<root>", "race_state", label), label),
        enumeration=_parse_enumeration(
            _take_object(root, "<root>", "enumeration", label), label
        ),
    )


def load_scenarios(directory: str | Path) -> tuple[Scenario, ...]:
    """Load every ``*.json`` scenario in ``directory``, sorted by scenario id.

    Loading is deterministic: files are read in filename order and the result is
    sorted by ``Scenario.id``. An empty directory yields an empty tuple.
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise ScenarioError(
            f"scenarios directory {directory} does not exist or is not a directory"
        )

    scenarios = [
        load_scenario(path) for path in sorted(directory.glob("*.json"), key=lambda p: p.name)
    ]
    return tuple(sorted(scenarios, key=lambda scenario: scenario.id))


# --- scenario sections --------------------------------------------------------


def _parse_race_state(obj: dict[str, Any], label: str) -> RaceState:
    _reject_unknown(obj, _RACE_STATE_KEYS, "race_state", label)

    subject = _parse_subject(
        _take_object(obj, "race_state", "subject", label), label
    )
    rivals = tuple(
        _parse_rival(value, f"race_state.rivals[{index}]", label)
        for index, value in enumerate(_take_list(obj, "race_state", "rivals", label))
    )
    context = _parse_context(
        _take_object(obj, "race_state", "context", label), label
    )
    return _wrap(
        lambda: RaceState(subject=subject, rivals=rivals, context=context),
        "race_state",
        label,
    )


def _parse_subject(obj: dict[str, Any], label: str) -> SubjectCar:
    field = "race_state.subject"
    _reject_unknown(obj, _SUBJECT_KEYS, field, label)

    laps_field = f"{field}.last_lap_times_s"
    raw_laps = obj.get("last_lap_times_s", [])
    last_lap_times_s = tuple(
        _read_float(value, f"{laps_field}[{index}]", label)
        for index, value in enumerate(_read_list(raw_laps, laps_field, label))
    )

    driver = _take_non_empty_str(obj, field, "driver", label)
    position = _take_int(obj, field, "position", label)
    compound = _take_compound(obj, field, "compound", label)
    tyre_age = _take_int(obj, field, "tyre_age", label)
    gap_ahead_s = _take_optional_float(obj, field, "gap_ahead_s", label)
    gap_behind_s = _take_optional_float(obj, field, "gap_behind_s", label)

    return _wrap(
        lambda: SubjectCar(
            driver=driver,
            position=position,
            compound=compound,
            tyre_age=tyre_age,
            last_lap_times_s=last_lap_times_s,
            gap_ahead_s=gap_ahead_s,
            gap_behind_s=gap_behind_s,
        ),
        field,
        label,
    )


def _parse_rival(value: Any, field: str, label: str) -> Rival:
    obj = _read_object(value, field, label)
    _reject_unknown(obj, _RIVAL_KEYS, field, label)

    driver = _take_non_empty_str(obj, field, "driver", label)
    compound = _take_compound(obj, field, "compound", label)
    tyre_age = _take_int(obj, field, "tyre_age", label)
    gap_s = _take_float(obj, field, "gap_s", label)
    position = _take_optional_int(obj, field, "position", label)

    return _wrap(
        lambda: Rival(
            driver=driver,
            compound=compound,
            tyre_age=tyre_age,
            gap_s=gap_s,
            position=position,
        ),
        field,
        label,
    )


def _parse_context(obj: dict[str, Any], label: str) -> RaceContext:
    field = "race_state.context"
    _reject_unknown(obj, _CONTEXT_KEYS, field, label)

    lap = _take_int(obj, field, "lap", label)
    total_laps = _take_int(obj, field, "total_laps", label)
    track_temp_c = _take_float(obj, field, "track_temp_c", label)
    pit_loss_s = _take_float(obj, field, "pit_loss_s", label)
    safety_car = _take_optional_bool(obj, field, "safety_car", label, default=False)

    return _wrap(
        lambda: RaceContext(
            lap=lap,
            total_laps=total_laps,
            track_temp_c=track_temp_c,
            pit_loss_s=pit_loss_s,
            safety_car=safety_car,
        ),
        field,
        label,
    )


def _parse_enumeration(obj: dict[str, Any], label: str) -> Enumeration:
    field = "enumeration"
    _reject_unknown(obj, _ENUMERATION_KEYS, field, label)

    max_stops = _take_int(obj, field, "max_stops", label)
    pit_lap_grid = _take_int(obj, field, "pit_lap_grid", label)

    return _wrap(
        lambda: Enumeration(max_stops=max_stops, pit_lap_grid=pit_lap_grid),
        field,
        label,
    )


# --- reading primitives -------------------------------------------------------


def _label(path: Path, scenario_id: str | None) -> str:
    if scenario_id:
        return f"scenario {scenario_id!r} ({path})"
    return f"scenario file {path}"


def _read_json(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ScenarioError(f"scenario file {path} could not be read: {exc}") from exc

    if not text.strip():
        raise ScenarioError(f"scenario file {path} is empty")

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ScenarioError(f"scenario file {path} is not valid JSON: {exc}") from exc


def _typename(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return type(value).__name__


def _field(parent: str, key: str) -> str:
    return key if parent == "<root>" else f"{parent}.{key}"


def _take(obj: dict[str, Any], parent: str, key: str, label: str) -> Any:
    value = obj.get(key, _MISSING)
    if value is _MISSING:
        raise ScenarioError(f"{label}: missing required field {_field(parent, key)!r}")
    return value


def _reject_unknown(
    obj: dict[str, Any], allowed: tuple[str, ...], field: str, label: str
) -> None:
    unknown = [key for key in obj if key not in allowed]
    if unknown:
        names = ", ".join(repr(key) for key in unknown)
        raise ScenarioError(f"{label}: field {field!r} has unknown key(s) {names}")


def _wrap(factory: Callable[[], _T], field: str, label: str) -> _T:
    try:
        return factory()
    except ValueError as exc:
        raise ScenarioError(f"{label}: field {field!r} is invalid: {exc}") from exc


def _read_object(value: Any, field: str, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ScenarioError(f"{label}: field {field!r} must be an object, got {_typename(value)}")
    return value


def _read_list(value: Any, field: str, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ScenarioError(f"{label}: field {field!r} must be an array, got {_typename(value)}")
    return value


def _read_str(value: Any, field: str, label: str) -> str:
    if not isinstance(value, str):
        raise ScenarioError(f"{label}: field {field!r} must be a string, got {_typename(value)}")
    return value


def _read_int(value: Any, field: str, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ScenarioError(f"{label}: field {field!r} must be an integer, got {_typename(value)}")
    return value


def _read_float(value: Any, field: str, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScenarioError(f"{label}: field {field!r} must be a number, got {_typename(value)}")
    return float(value)


def _read_bool(value: Any, field: str, label: str) -> bool:
    if not isinstance(value, bool):
        raise ScenarioError(f"{label}: field {field!r} must be a boolean, got {_typename(value)}")
    return value


def _read_compound(value: Any, field: str, label: str) -> Compound:
    if not isinstance(value, str) or value not in _COMPOUND_VALUES:
        raise ScenarioError(
            f"{label}: field {field!r} must be one of {_COMPOUND_CHOICES}, got {value!r}"
        )
    return Compound(value)


def _take_object(obj: dict[str, Any], parent: str, key: str, label: str) -> dict[str, Any]:
    return _read_object(_take(obj, parent, key, label), _field(parent, key), label)


def _take_list(obj: dict[str, Any], parent: str, key: str, label: str) -> list[Any]:
    return _read_list(_take(obj, parent, key, label), _field(parent, key), label)


def _take_non_empty_str(obj: dict[str, Any], parent: str, key: str, label: str) -> str:
    field = _field(parent, key)
    value = _read_str(_take(obj, parent, key, label), field, label)
    if not value:
        raise ScenarioError(f"{label}: field {field!r} must not be empty")
    return value


def _take_int(obj: dict[str, Any], parent: str, key: str, label: str) -> int:
    return _read_int(_take(obj, parent, key, label), _field(parent, key), label)


def _take_float(obj: dict[str, Any], parent: str, key: str, label: str) -> float:
    return _read_float(_take(obj, parent, key, label), _field(parent, key), label)


def _take_optional_float(
    obj: dict[str, Any], parent: str, key: str, label: str
) -> float | None:
    if key not in obj or obj[key] is None:
        return None
    return _take_float(obj, parent, key, label)


def _take_optional_int(
    obj: dict[str, Any], parent: str, key: str, label: str
) -> int | None:
    if key not in obj or obj[key] is None:
        return None
    return _take_int(obj, parent, key, label)


def _take_optional_bool(
    obj: dict[str, Any], parent: str, key: str, label: str, *, default: bool
) -> bool:
    if key not in obj or obj[key] is None:
        return default
    return _read_bool(obj[key], _field(parent, key), label)


def _take_compound(obj: dict[str, Any], parent: str, key: str, label: str) -> Compound:
    return _read_compound(_take(obj, parent, key, label), _field(parent, key), label)
