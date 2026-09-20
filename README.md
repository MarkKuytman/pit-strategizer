# Pit Strategizer

A prototype that asks Jev (TypeSafe's System One model) for a pit strategy
decision, and measures how decision quality changes as the race state is
abstracted from raw telemetry into semantic strategy language.

The domain vocabulary is defined in [`CONTEXT.md`](CONTEXT.md); the deliberate
design constraints are recorded in [`docs/adr/`](docs/adr/).

## Scenarios

A **scenario** is one pit-decision moment, hand-authored as JSON at
[`scenarios/<id>.json`](scenarios/). The file maps field-for-field onto the
domain types; [`src/pit_strategizer/scenarios.py`](src/pit_strategizer/scenarios.py)
parses it into a `Scenario`.

```json
{
  "id": "mid-stint-undercut",
  "archetype": "undercut-threat",
  "race_state": {
    "subject": {
      "driver": "VER", "position": 2, "compound": "medium", "tyre_age": 12,
      "last_lap_times_s": [91.2, 91.4, 91.7],
      "gap_ahead_s": 3.4, "gap_behind_s": 1.1
    },
    "rivals": [
      {"driver": "NOR", "compound": "soft", "tyre_age": 9, "gap_s": 3.4, "position": 1},
      {"driver": "LEC", "compound": "hard", "tyre_age": 15, "gap_s": -1.1, "position": 3}
    ],
    "context": {
      "lap": 32, "total_laps": 58, "track_temp_c": 41.0,
      "pit_loss_s": 22.0, "safety_car": false
    }
  },
  "enumeration": { "max_stops": 2, "pit_lap_grid": 3 }
}
```

`compound` is one of `"soft"`, `"medium"` or `"hard"`, and `gap_s` is signed
(positive means the rival is ahead of the subject car). The required fields are
those shown; `last_lap_times_s`, a subject's `gap_ahead_s` / `gap_behind_s`, a
rival's `position` and `safety_car` may be omitted or `null` and fall back to
the domain defaults. Unknown fields are rejected, so a typo fails loudly rather
than being silently ignored.

```python
from pit_strategizer.scenarios import (
    default_scenarios_directory,
    load_scenario,
    load_scenarios,
)

scenario = load_scenario("scenarios/undercut-threat.json")
all_scenarios = load_scenarios(default_scenarios_directory())  # tuple, sorted by id
```

Malformed input raises `ScenarioError` (a `ValueError`) naming the scenario and
the offending field, for example:

```text
scenario 'mid-stint-undercut' (scenarios/undercut-threat.json): field
'race_state.subject.tyre_age' must be an integer, got string
```

## Setup

Requires Python 3.10+.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

## Run

```sh
pit-strategizer --help
```

## Test

```sh
pytest
```
