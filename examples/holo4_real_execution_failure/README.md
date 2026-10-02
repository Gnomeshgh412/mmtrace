# Holo4 Real Execution Failure

This example preserves an unmodified public Holo4 trajectory that contains explicit executor-reported action failures.

## Source

- Dataset: `Hcompany/trajectories`
- Dataset license: Apache-2.0
- Benchmark: OSWorld
- Model: Holo4 27B
- Trajectory ID: `libreoffice-calc-13-23ff35a8`
- Task success: `false`
- Task score: `0.0`
- Raw trajectory: unmodified
- SHA-256: `6a9d72ede4f8f12c69a52da3944156f8ac12d41428027ed68341079fb683d291`

Upstream benchmark/task visual content may remain subject to its own terms.

## Evidence Boundary

- Fault injection: none
- Synthetic execution metadata: none
- Task score used as trigger: no
- Human annotation used as trigger: no

MMTRACE007 is triggered only by normalized action-level execution results derived from raw executor/tool output.

## Current MMTrace Result

- `MMTRACE007` x 5 ERROR
- Source steps: 13, 15, 21, 22, 75

The selected display case is source step 21:

- Action: `shell`
- Raw evidence: Python `NameError`
- Execution receipt: `exit_code: 1`
- Normalized finding: `MMTRACE007 — Explicit Execution Failure`

## Screenshots

- `screenshots/image_026.webp`: current/pre-action observation for source steps 21 and 22
- `screenshots/image_028.webp`: later screenshot after subsequent interaction

The Holo4 schema records step images as observations. It does not prove that `image_028.webp` is the immediate post-error screenshot for source step 21.

## Reproduce

```bash
mmtrace check \
  examples/holo4_real_execution_failure/trajectory.json \
  --adapter holo4
```
