# Pit Strategizer

A prototype that asks Jev (TypeSafe's System One model) for a pit strategy
decision, and measures how decision quality changes as the race state is
abstracted from raw telemetry into semantic strategy language.

The domain vocabulary is defined in [`CONTEXT.md`](CONTEXT.md); the deliberate
design constraints are recorded in [`docs/adr/`](docs/adr/).

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
