"""Behaviour tests for the scenario loader.

These exercise the module's public surface: constructing a ``Scenario`` from a
JSON file, loading a directory deterministically, and failing precisely on
malformed input. They do not reach into private helpers.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from pit_strategizer.domain import (
    Compound,
    Enumeration,
    RaceContext,
    RaceState,
    Rival,
    Scenario,
    SubjectCar,
)
from pit_strategizer.scenarios import (
    ScenarioError,
    default_scenarios_directory,
    load_scenario,
    load_scenarios,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
AUTHORED_SCENARIO = REPO_ROOT / "scenarios" / "undercut-threat.json"


def scenario_data() -> dict[str, Any]:
    """The authored scenario as plain JSON data, for mutation in failure tests."""
    return {
        "id": "mid-stint-undercut",
        "archetype": "undercut-threat",
        "race_state": {
            "subject": {
                "driver": "VER",
                "position": 2,
                "compound": "medium",
                "tyre_age": 12,
                "last_lap_times_s": [91.2, 91.4, 91.7],
                "gap_ahead_s": 3.4,
                "gap_behind_s": 1.1,
            },
            "rivals": [
                {"driver": "NOR", "compound": "soft", "tyre_age": 9, "gap_s": 3.4, "position": 1},
                {"driver": "LEC", "compound": "hard", "tyre_age": 15, "gap_s": -1.1, "position": 3},
            ],
            "context": {
                "lap": 32,
                "total_laps": 58,
                "track_temp_c": 41.0,
                "pit_loss_s": 22.0,
                "safety_car": False,
            },
        },
        "enumeration": {"max_stops": 2, "pit_lap_grid": 3},
    }


def write_scenario(directory: Path, data: Any, name: str = "scenario.json") -> Path:
    path = directory / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def expected_authored_scenario() -> Scenario:
    """The domain value the authored file must load into (mirrors test_domain)."""
    return Scenario(
        id="mid-stint-undercut",
        archetype="undercut-threat",
        race_state=RaceState(
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
                Rival(driver="NOR", compound=Compound.SOFT, tyre_age=9, gap_s=3.4, position=1),
                Rival(driver="LEC", compound=Compound.HARD, tyre_age=15, gap_s=-1.1, position=3),
            ),
            context=RaceContext(
                lap=32,
                total_laps=58,
                track_temp_c=41.0,
                pit_loss_s=22.0,
                safety_car=False,
            ),
        ),
        enumeration=Enumeration(max_stops=2, pit_lap_grid=3),
    )


# --- loading a valid scenario -------------------------------------------------


def test_load_scenario_maps_every_field_into_the_domain() -> None:
    assert load_scenario(AUTHORED_SCENARIO) == expected_authored_scenario()


def test_race_state_carries_subject_rivals_and_context() -> None:
    scenario = load_scenario(AUTHORED_SCENARIO)
    race_state = scenario.race_state

    assert race_state.subject == SubjectCar(
        driver="VER",
        position=2,
        compound=Compound.MEDIUM,
        tyre_age=12,
        last_lap_times_s=(91.2, 91.4, 91.7),
        gap_ahead_s=3.4,
        gap_behind_s=1.1,
    )
    assert [rival.driver for rival in race_state.rivals] == ["NOR", "LEC"]
    assert race_state.context.lap == 32
    assert race_state.context.total_laps == 58
    assert race_state.context.track_temp_c == pytest.approx(41.0)
    assert race_state.context.pit_loss_s == pytest.approx(22.0)
    assert race_state.context.safety_car is False


def test_compound_values_map_to_the_compound_enum() -> None:
    scenario = load_scenario(AUTHORED_SCENARIO)
    assert scenario.race_state.subject.compound is Compound.MEDIUM
    assert [rival.compound for rival in scenario.race_state.rivals] == [
        Compound.SOFT,
        Compound.HARD,
    ]


def test_missing_optional_fields_fall_back_to_domain_defaults(tmp_path: Path) -> None:
    data = scenario_data()
    del data["race_state"]["subject"]["last_lap_times_s"]
    del data["race_state"]["subject"]["gap_ahead_s"]
    del data["race_state"]["subject"]["gap_behind_s"]
    del data["race_state"]["context"]["safety_car"]
    del data["race_state"]["rivals"][1]["position"]

    scenario = load_scenario(write_scenario(tmp_path, data))

    assert scenario.race_state.subject.last_lap_times_s == ()
    assert scenario.race_state.subject.gap_ahead_s is None
    assert scenario.race_state.subject.gap_behind_s is None
    assert scenario.race_state.context.safety_car is False
    assert scenario.race_state.rivals[1].position is None


# --- loading a directory ------------------------------------------------------


def test_default_scenarios_directory_points_at_repo_root_scenarios() -> None:
    directory = default_scenarios_directory()
    assert directory.name == "scenarios"
    assert directory.is_dir()
    assert load_scenario(directory / "undercut-threat.json") == expected_authored_scenario()


def test_load_scenarios_returns_a_tuple_sorted_by_id(tmp_path: Path) -> None:
    write_scenario(tmp_path, scenario_data(), name="zeta.json")
    later = copy.deepcopy(scenario_data())
    later["id"] = "alpha-scenario"
    write_scenario(tmp_path, later, name="alpha.json")

    scenarios = load_scenarios(tmp_path)

    assert isinstance(scenarios, tuple)
    assert [scenario.id for scenario in scenarios] == ["alpha-scenario", "mid-stint-undercut"]


def test_load_scenarios_loads_the_authored_directory() -> None:
    scenarios = load_scenarios(default_scenarios_directory())
    assert any(scenario.id == "mid-stint-undercut" for scenario in scenarios)


def test_empty_directory_loads_as_an_empty_tuple(tmp_path: Path) -> None:
    assert load_scenarios(tmp_path) == ()


def test_missing_directory_fails_clearly(tmp_path: Path) -> None:
    missing = tmp_path / "no-such-directory"
    with pytest.raises(ScenarioError, match="no-such-directory"):
        load_scenarios(missing)


# --- malformed input ----------------------------------------------------------


def test_missing_file_fails_clearly(tmp_path: Path) -> None:
    with pytest.raises(ScenarioError, match="missing.json"):
        load_scenario(tmp_path / "missing.json")


def test_scenario_error_is_a_value_error() -> None:
    assert issubclass(ScenarioError, ValueError)


def test_bad_json_names_the_file(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text('{"id": "broken", ', encoding="utf-8")

    with pytest.raises(ScenarioError) as error:
        load_scenario(path)

    assert "broken.json" in str(error.value)
    assert "JSON" in str(error.value)


def test_empty_file_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "empty.json"
    path.write_text("   \n", encoding="utf-8")

    with pytest.raises(ScenarioError, match="empty"):
        load_scenario(path)


def test_non_object_root_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ScenarioError, match="object"):
        load_scenario(write_scenario(tmp_path, ["not", "an", "object"]))


def test_missing_required_field_names_the_field(tmp_path: Path) -> None:
    data = scenario_data()
    del data["race_state"]["subject"]["position"]

    with pytest.raises(ScenarioError) as error:
        load_scenario(write_scenario(tmp_path, data))

    message = str(error.value)
    assert "missing" in message
    assert "race_state.subject.position" in message


def test_unknown_field_is_rejected(tmp_path: Path) -> None:
    data = scenario_data()
    data["race_state"]["subject"]["tyreAge"] = 12

    with pytest.raises(ScenarioError) as error:
        load_scenario(write_scenario(tmp_path, data))

    message = str(error.value)
    assert "tyreAge" in message
    assert "race_state.subject" in message


def test_wrong_type_names_the_field(tmp_path: Path) -> None:
    data = scenario_data()
    data["race_state"]["subject"]["tyre_age"] = "twelve"

    with pytest.raises(ScenarioError) as error:
        load_scenario(write_scenario(tmp_path, data))

    message = str(error.value)
    assert "race_state.subject.tyre_age" in message
    assert "integer" in message


def test_unknown_compound_lists_the_allowed_values(tmp_path: Path) -> None:
    data = scenario_data()
    data["race_state"]["subject"]["compound"] = "ultrasoft"

    with pytest.raises(ScenarioError) as error:
        load_scenario(write_scenario(tmp_path, data))

    message = str(error.value)
    assert "race_state.subject.compound" in message
    assert "ultrasoft" in message
    assert "soft" in message and "medium" in message and "hard" in message


def test_rivals_must_be_an_array(tmp_path: Path) -> None:
    data = scenario_data()
    data["race_state"]["rivals"] = {"driver": "NOR"}

    with pytest.raises(ScenarioError) as error:
        load_scenario(write_scenario(tmp_path, data))

    assert "race_state.rivals" in str(error.value)


def test_rival_entries_must_be_objects(tmp_path: Path) -> None:
    data = scenario_data()
    data["race_state"]["rivals"] = ["NOR"]

    with pytest.raises(ScenarioError) as error:
        load_scenario(write_scenario(tmp_path, data))

    assert "race_state.rivals[0]" in str(error.value)


def test_invalid_domain_value_is_wrapped_naming_the_scenario(tmp_path: Path) -> None:
    data = scenario_data()
    data["enumeration"]["max_stops"] = 3

    path = write_scenario(tmp_path, data)
    with pytest.raises(ScenarioError) as error:
        load_scenario(path)

    message = str(error.value)
    assert "mid-stint-undercut" in message
    assert "two stops" in message


def test_error_message_identifies_the_scenario_id(tmp_path: Path) -> None:
    data = scenario_data()
    del data["enumeration"]["pit_lap_grid"]

    with pytest.raises(ScenarioError, match="mid-stint-undercut"):
        load_scenario(write_scenario(tmp_path, data))
