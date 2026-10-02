# MMTrace

English | [简体中文](README.zh-CN.md)

Deterministic reliability checking and trace inspection for multimodal and computer-use agents.

MMTrace verifies whether an agent trajectory has a trustworthy evidence chain:

```text
Observation -> Model Context -> Action -> Execution -> Post-State
```

It is intentionally small. MMTrace is not a general agent debugger, semantic judge, recovery framework, dashboard platform, or agent runtime.

## Real-World Execution Failure

MMTrace analyzed an unmodified public Holo4 trajectory from the OSWorld benchmark.

![MMTrace Holo4 real execution failure](docs/assets/holo4-real-execution-failure.png)

The executor explicitly reported failures at five steps, including `xdotool`
errors and Python `NameError`, `AttributeError`, and `IndexError` exceptions.

MMTrace surfaces these machine-verifiable failures as:

- 5 × `MMTRACE007` - Explicit Execution Failure

The screenshot above shows one of these failures in the Trace Inspector.

One concrete finding occurred at source Step 21, normalized as MMTrace Step 22:

```text
NameError: name 'pyautoguiBUTTONDOWN' is not defined
```

These errors occur within a failed real-world trajectory. MMTrace does not claim
that they are proven to be the sole or direct cause of the overall task failure.

Source:

- Dataset: [`Hcompany/trajectories`](https://huggingface.co/datasets/Hcompany/trajectories)
- Benchmark: [OSWorld](https://github.com/xlang-ai/OSWorld)
- Model: Holo4 27B
- Trajectory: `libreoffice-calc-13-23ff35a8`

Reproduce the example locally:

```bash
mmtrace check \
  examples/holo4_real_execution_failure/trajectory.json \
  --adapter holo4
```

Expected result:

```text
Status: FAIL
Errors: 5
Warnings: 0
MMTRACE007: 5
```

## Why MMTrace

Agent failure is not always reasoning failure. A trace can be hard to trust when screenshots are missing, model context does not reference the observed state, coordinates do not match the frame, actions lack execution evidence, or successful actions have no post-action verification.

MMTrace focuses on deterministic checks over recorded evidence. When required evidence is absent, rules skip instead of guessing.

## What MMTrace Does

- Normalizes agent traces into a common schema
- Runs deterministic reliability rules
- Produces evidence-backed findings
- Exposes a CLI and JSON report format
- Provides a local FastAPI backend and React Trace Inspector for visual review

## Reliability Rules

| Rule | Finding | Severity |
| --- | --- | --- |
| `MMTRACE001` | Missing Observation | ERROR |
| `MMTRACE002` | Observation Not In Model Context | ERROR |
| `MMTRACE003` | Coordinate Out Of Frame | ERROR |
| `MMTRACE004` | Coordinate Space Mismatch | ERROR |
| `MMTRACE005` | Stale Observation | WARNING |
| `MMTRACE006` | Missing Post-Action Verification | WARNING |
| `MMTRACE007` | Explicit Execution Failure | ERROR |

Not every adapter can provide the evidence needed for every rule. Implemented does not mean evaluable.

## Architecture

```text
Agent Trace
    |
    v
Adapter
    |
    v
MMTrace Core
    |-- CLI / JSON Report
    |
    `-- FastAPI
            |
            v
       Trace Inspector
```

MMTrace Core owns schema, adapters, deterministic checks, and reports. FastAPI owns HTTP transport, uploads, temporary screenshot artifacts, and serialization. React owns visualization and interaction only.

Web artifact URLs are transport-layer data and are not written into `Trace`, `Observation`, `Finding`, or `Report`.

## CLI Quick Start

Install in editable mode:

```bash
python3 -m pip install -e .
```

Check a standard MMTrace JSON file:

```bash
mmtrace check trajectory.json
```

Check a Browser Use history file:

```bash
mmtrace check history.json --adapter browser-use
```

Check an OSWorld `traj.jsonl` file:

```bash
mmtrace check traj.jsonl --adapter osworld
```

Check a Holo4 trajectory JSON file:

```bash
mmtrace check trajectory.json --adapter holo4
```

Emit machine-readable JSON:

```bash
mmtrace check history.json \
  --adapter browser-use \
  --format json
```

Run a single rule:

```bash
mmtrace check trajectory.json \
  --rule MMTRACE003
```

## Trace Inspector

The Web MVP provides a local Trace Inspector with:

- Adapter selection for `generic`, `browser-use`, `osworld`, and `holo4`
- JSON trace upload
- Optional screenshot ZIP upload
- Trace summary, trajectory list, step inspector, and findings panel
- Real screenshot viewing through `/api/artifacts/...`
- Before / After observation switching when both screenshots are available

Screenshot artifacts are optional. If no ZIP is uploaded, analysis still works and the UI reports screenshot artifacts as unavailable.

## Run Locally

Backend:

```bash
python3 -m pip install -e ".[web,test]"
python3 -m uvicorn web.backend.app:app \
  --host 127.0.0.1 \
  --port 8000
```

Frontend:

```bash
cd web/frontend
npm ci
npm run dev
```

Open the URL printed by Vite. The frontend uses a development proxy for `/api`, so it does not require CORS configuration for local development.

## Included Real Examples

| Example | Adapter | Result | Purpose |
| --- | --- | --- | --- |
| Holo4 / OSWorld | `holo4` | FAIL · 5 ERROR | Real explicit execution failure validation |
| OSWorld | `osworld` | FAIL · 1 ERROR / 10 WARNING | Coordinate and stale-observation regression |
| Browser Use | `browser-use` | PASS | Real trace / false-positive regression |

Paths:

- `examples/holo4_real_execution_failure/`
- `examples/osworld_real_failure/`
- `examples/browser_use_real/`

See each example directory for provenance and reproduction details.

## Evidence Limitations

Implemented does not mean evaluable.

Rules only run when the required evidence is present. No finding does not prove the agent was correct, safe, or fully evaluated.

Browser Use ordinary history currently has important limitations:

- It does not prove true model input messages, so `MMTRACE002` is usually not evaluable.
- Coordinates, viewport dimensions, and coordinate-space metadata may be unavailable.
- Exact observation/action timestamps may be unavailable.
- Not every implemented rule is evaluable on every trace.
- Absence of findings is not proof of agent correctness.

The Trace Inspector keeps this distinction explicit. Its PASS state means no deterministic reliability findings were found for the currently evaluable evidence.

## Exit Codes

```text
0  Check completed and no ERROR findings were reported.
1  Check completed and at least one ERROR finding was reported.
2  Input, argument, schema, or adapter error.
```

Warnings do not cause exit code `1`.

## Development

Python:

```bash
python3 -m pytest -q
python3 -m pip check
```

Frontend:

```bash
cd web/frontend
npm ci
npm run typecheck
npm run build
```

## CI

GitHub Actions currently runs:

- Python 3.11 and 3.12
- `python -m pip install -e ".[web,test]"`
- `python -m pytest -q`
- `python -m pip check`
- Node 20
- `npm ci`
- `npm run typecheck`
- `npm run build`

CI does not require secrets and does not call SiliconFlow, Browser Use, or any agent runtime.

## Packaging Boundary

The Python package is the MMTrace core package. The Web MVP is currently intended for source-checkout development from this repository.

Do not assume that a wheel-only installation includes a standalone packaged frontend application.

## Project Status

MMTrace v0.1.0 is the first public release of the Core + Trace Inspector MVP.

It is an early, local-first reliability checker and trace inspector, not a production platform.

## License

MMTrace is released under the MIT License.

Third-party datasets and benchmark artifacts remain subject to their respective licenses and terms.
