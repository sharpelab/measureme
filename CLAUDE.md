# CLAUDE.md - measureme

## What This Is

Measurement orchestration library for QCoDeS. Wraps instrument control into a `Station` that runs 0D–2D parameter sweeps, writes data to disk, and provides live plotting. Built for cryogenic transport measurements on van der Waals devices (graphene, etc.) but the code is device-agnostic.

Originally by spxtr (upstream: `spxtr/measureme`), forked to `sharpelab/measureme`. Active development on the `sharpelab` branch.

## Architecture

~1700 lines across 9 files in `sweep/`:

| File | Lines | Role |
|------|-------|------|
| `sweep.py` | 830 | Core: `Station`, `AsyncStation`, 6 sweep functions |
| `plot.py` | 236 | Live Qt5 plotter via multiprocessing subprocess |
| `db.py` | 206 | Storage: `Writer` (TSV + metadata.json + gzip), `Reader` |
| `raster.py` | 183 | Polygon rasterization for multisweep paths |
| `sweep_load.py` | 91 | Data loading: `pload` dispatches by type |
| `types.py` | 11 | Shared type aliases (`Comment`, `ParamGain`, re-exports `Parameter`) |
| `sweep_test.py` | 60 | Station tests using qcodes `DummyInstrument` |
| `db_test.py` | 91 | Reader/Writer tests |
| `__init__.py` | 1 | `from .sweep import *` |

### Data Flow

```
Station.sweep(param, setpoints)
  → for each setpoint: param(value) → sleep → measure all followed params
  → Writer.add_point([timestamp, setpoint, readings...])
  → Plotter.add_point (via subprocess pipe)
  → on completion: gzip data, save plot image, return SweepResult
```

### Sweep Functions

All follow the same pattern: set param → sleep → measure → write → check interrupt.

- `measure()` — 0D, single point
- `watch()` — 1D, time series
- `sweep()` — 1D, single param
- `multisweep()` — 1D, multiple params via rasterized polygon path
- `megasweep()` — 2D, nested slow/fast
- `multimegasweep()` — 2D, nested with multi-param fast axis

### Key Design Choices

- **`_interruptible` decorator** — installs SIGINT handler that sets a flag instead of killing mid-instrument-communication. Important for hardware safety.
- **Hook system** — `register_run_before`/`register_run_after` with `inspect.signature()`-based context injection. Hooks only receive kwargs they declare.
- **AsyncStation** — groups instrument reads by instrument, runs concurrently via ThreadPoolExecutor. Same API as Station.
- **Writer** — data lives uncompressed during sweep (readable by live plotter), gzipped on close with md5 verification.

## Development

### Commands

```bash
uv run pytest              # run tests
uv run ruff check          # lint
uv run ruff format         # format
uv run ty check            # type check
```

### Pre-commit Hooks

Ruff (lint + format) and ty (type check) run on every commit. Install with:

```bash
uv run pre-commit install
```

### Testing

Tests use `qcodes.instrument_drivers.mock_instruments.DummyInstrument` for realistic parameter mocking. Test files follow `*_test.py` naming convention.

## Coding Conventions

### Types

- All functions and methods must have full type annotations (parameters + return types).
- Use `qcodes.parameters.Parameter` (imported via `sweep.types`) instead of `Any` for QCoDeS parameter arguments.
- Named type aliases live in `sweep/types.py` for shared types, or at the top of a file for file-local types.
- Current aliases: `Comment`, `ParamGain`, `PlotSpec`, `DataMap`, `LinePlot`, `Vertices`, `DataDict`, `Metadata`.
- Use built-in generics (`list`, `dict`, `tuple`) not `typing.List` etc. — requires-python is >=3.10.
- Setpoints typing is still `Any` (pending a good solution for list/range/ndarray union).

### Style

- Ruff handles formatting and linting (configured via defaults).
- No docstrings required on private methods or obvious functions. Existing docstrings should be preserved.
- The sweep functions are intentionally copy-paste with minor variations. Self-contained readability is preferred over DRY abstraction here.

### Data

- Measurement data lives outside this repo. For RPL_19: `~/sharpelab/measureme-data/RPL_19/`.
- Each run gets a directory `data/{id}/` containing `data.tsv.gz` and `metadata.json`.
- Test notebook: `test_nb.ipynb` (uses qcodes DummyInstrument, not real hardware).