# MMTrace

MMTrace is a deterministic reliability checker for multimodal / computer-use agent trajectories.

It checks whether the evidence chain in an agent trace is structurally consistent:

```text
Observation -> Model Context -> Action -> Execution -> Post-State
```

MMTrace is intentionally small. It is not a general agent debugger, root-cause analysis system, semantic judge, recovery framework, or dashboard.

## Project Overview

MMTrace defines a lightweight trace schema, deterministic checks, adapters for input formats, and a CLI that produces text or JSON reports.

Current v0.1 core includes:

- Core Pydantic schema for traces, findings, and reports
- Checker engine
- Rules `MMTRACE001` through `MMTRACE006`
- Generic MMTrace JSON adapter
- Browser Use history adapter
- CLI with text and JSON output
- Real Browser Use example trajectory
- Offline regression tests, including real-trace-derived fault mutations

## Why MMTrace

Computer-use agents often fail because evidence is missing or inconsistent: an action is not tied to a screenshot, coordinates do not match a frame, a successful action has no post-action verification, or an observation was never placed in model context.

MMTrace focuses on deterministic evidence checks. When evidence is absent, rules skip instead of guessing.

## What It Checks

- `MMTRACE001` - Missing Observation
- `MMTRACE002` - Observation Not In Model Context
- `MMTRACE003` - Coordinate Out Of Frame
- `MMTRACE004` - Coordinate Space Mismatch
- `MMTRACE005` - Stale Observation
- `MMTRACE006` - Missing Post-Action Verification

Not every adapter can provide the evidence needed for every rule. For example, Browser Use history currently does not include the actual model input messages, so `MMTRACE002` is usually not evaluable for ordinary Browser Use exports.

## Quick Start

Install in editable mode:

```bash
pip install -e .
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

## Supported Adapters

### Generic JSON

Use the default adapter for JSON files already shaped as MMTrace `Trace` objects:

```bash
mmtrace check trajectory.json
```

### Browser Use

Use the Browser Use adapter for offline `AgentHistoryList.save_to_file()` exports:

```bash
mmtrace check history.json --adapter browser-use
```

The Browser Use adapter maps saved history evidence faithfully. It does not fabricate model inputs, timestamps, viewport dimensions, coordinate transforms, or success statuses.

## Rules

### MMTRACE001 - Missing Observation

Flags visual/environment-dependent actions such as `click`, `drag`, or `move` when the step has no corresponding observation.

### MMTRACE002 - Observation Not In Model Context

Flags a captured observation that is not referenced by the model input context.

### MMTRACE003 - Coordinate Out Of Frame

Flags explicit viewport/image coordinates that fall outside the applicable frame.

### MMTRACE004 - Coordinate Space Mismatch

Flags explicit coordinate-space conflicts when expected coordinate-space metadata exists and no transform is available.

### MMTRACE005 - Stale Observation

Flags an action using an older observation when a newer environment observation exists before the action timestamp.

### MMTRACE006 - Missing Post-Action Verification

Flags successful state-changing actions that lack post-action verification evidence.

## Example

A real Browser Use trajectory is included:

```bash
mmtrace check examples/browser_use_real/history.json --adapter browser-use
```

Current result:

```text
Status: PASS
Errors: 0
Warnings: 0
```

The example preserves 4 Browser Use source actions as 4 MMTrace actions.

## Evidence Limitations

Implemented does not mean evaluable.

Rules only run when the required evidence is present. No finding does not necessarily mean every rule had enough evidence to evaluate the trace.

Browser Use ordinary history currently provides:

- `MMTRACE001`: partially evaluable
- `MMTRACE002`: usually not evaluable because true model input messages are not saved
- `MMTRACE003`: evaluable only when explicit coordinates and reliable dimensions are available
- `MMTRACE004`: usually not evaluable because expected coordinate-space / transform metadata is absent
- `MMTRACE005`: not currently evaluable from Browser Use step timing because the adapter does not treat step-level timing as precise observation/action timestamps
- `MMTRACE006`: partially evaluable

## Exit Codes

```text
0  Check completed and no ERROR findings were reported.
1  Check completed and at least one ERROR finding was reported.
2  Input, argument, schema, or adapter error.
```

Warnings do not cause exit code `1`.

## Development / Tests

Run the test suite:

```bash
python3 -m pytest -q
```

Check installed package requirements:

```bash
python3 -m pip check
```

## Project Status

MMTrace is in early v0.1 development. The core deterministic pipeline is present, but evidence coverage depends on the adapter and source trace format.
