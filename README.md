# MMTrace

English | [简体中文](README.zh-CN.md)

Deterministic reliability checking and trace inspection for multimodal / computer-use agents.

MMTrace verifies whether an agent trajectory has a trustworthy evidence chain:

```text
Observation -> Model Context -> Action -> Execution -> Post-State
```

It is intentionally small. MMTrace is not a general agent debugger, semantic judge, recovery framework, dashboard platform, or agent runtime.

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

- `MMTRACE001` - Missing Observation
- `MMTRACE002` - Observation Not In Model Context
- `MMTRACE003` - Coordinate Out Of Frame
- `MMTRACE004` - Coordinate Space Mismatch
- `MMTRACE005` - Stale Observation
- `MMTRACE006` - Missing Post-Action Verification

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

- Adapter selection for `generic` and `browser-use`
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

## Using Browser Use Example

A real Browser Use trajectory is included:

```text
examples/browser_use_real/history.json
```

Use adapter:

```text
browser-use
```

For screenshots, create a temporary ZIP from:

```text
examples/browser_use_real/screenshots/
```

Upload that ZIP as the optional Screenshot bundle in the Trace Inspector. Do not store temporary ZIP files in the repository.

CLI:

```bash
mmtrace check examples/browser_use_real/history.json --adapter browser-use
```

Current result:

```text
Status: PASS
Errors: 0
Warnings: 0
```

The example preserves 4 Browser Use source actions as 4 MMTrace actions. Its 3 saved screenshot observations can be mapped by the Web Inspector when a screenshot ZIP is uploaded.

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

MMTrace is at v0.1 Core + Trace Inspector Web MVP. It is an early local-first reliability checker and inspector, not a production platform.
