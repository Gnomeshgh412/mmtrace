# OSWorld Real Failure Example

This is a partial artifact bundle from the public Hugging Face dataset
`UI-MOPD/OSWorld-Eval-Results` for task
`5d901039-a89c-4bfb-967b-bf66f4df075e`.

Source dataset: https://huggingface.co/datasets/UI-MOPD/OSWorld-Eval-Results

License: Apache-2.0

Benchmark: OSWorld

Task ID: 5d901039-a89c-4bfb-967b-bf66f4df075e

Agent: Qwen3-VL-8B-Thinking

Application: LibreOffice Impress

Task result: 0.0

Current MMTrace result:

- Status: FAIL
- Findings: 11 total
- `MMTRACE003`: 1
- `MMTRACE005`: 10

MMTrace provenance:

- The raw trajectory was not modified.
- No fault injection was applied.
- No synthetic metadata was added to the raw data.
- Findings are produced by the current formal `OSWorldAdapter` and `CheckEngine`.

Included files:

- `traj.jsonl`: raw OSWorld trajectory, unmodified.
- `instruction.txt`: raw task instruction.
- `result.txt`: raw task score.
- `step_*.png`: minimal screenshots needed for regression evidence.

This is not a complete OSWorld task directory. The raw trajectory references
additional screenshots that are intentionally not stored in this repository.

Run:

```bash
mmtrace check examples/osworld_real_failure/traj.jsonl --adapter osworld
```

The Web Trace Inspector can display the included screenshots when these PNG
files are uploaded as a temporary screenshot ZIP. Do not store that temporary ZIP
in the repository.
