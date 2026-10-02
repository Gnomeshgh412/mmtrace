"""Holo4 trajectory adapter for Hcompany/trajectories JSON exports."""

from __future__ import annotations

import json
import re
import struct
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from mmtrace.adapters.base import AdapterError, BaseAdapter
from mmtrace.schema.trace import Action, ExecutionResult, Observation, PostState, Step, Trace

ACTION_TYPE_MAP = {
    "click_desktop": "click",
    "double_click_desktop": "click",
    "move_to_desktop": "move",
    "drag_desktop": "drag",
    "write_at_desktop": "click",
    "write_desktop": "type",
    "hotkey_desktop": "keypress",
    "scroll_desktop": "scroll",
}
EXECUTION_RECEIPT_RE = re.compile(
    r"\[Execution receipt\].*?exit_code:\s*(-?\d+)",
    re.IGNORECASE | re.DOTALL,
)
MAX_ERROR_TEXT_CHARS = 1500


class Holo4Adapter(BaseAdapter):
    """Load public Holo4 trajectory JSON files without depending on Holo4 code."""

    name = "holo4"

    def can_load(self, path: str | Path) -> bool:
        return Path(path).suffix.lower() == ".json"

    def load(self, path: str | Path) -> Trace:
        input_path = Path(path)

        try:
            raw_data = input_path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise AdapterError(f"file not found: {input_path}") from exc
        except OSError as exc:
            raise AdapterError(f"failed to read {input_path}: {exc}") from exc

        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            raise AdapterError(
                f"failed to parse {input_path}: invalid JSON at line {exc.lineno}, column {exc.colno}"
            ) from exc

        if not isinstance(data, dict):
            raise AdapterError(f"failed to load Holo4 trajectory {input_path}: expected a JSON object")

        try:
            return Trace(
                trace_id=str(data["id"]) if data.get("id") is not None else input_path.stem,
                task=_task_text(data),
                agent=str(data["model"]) if data.get("model") is not None else None,
                metadata=_trace_metadata(data),
                steps=_steps_from_holo4(data, input_path.parent),
            )
        except (TypeError, ValueError, ValidationError) as exc:
            raise AdapterError(f"failed to load Holo4 trajectory {input_path}: {exc}") from exc


def _steps_from_holo4(data: dict[str, Any], base_dir: Path) -> list[Step]:
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list):
        raise ValueError("expected steps to be a list")

    trace_id = str(data.get("id") or "unknown")
    benchmark = str(data.get("benchmark") or "")
    steps: list[Step] = []

    for source_step_index, raw_step in enumerate(raw_steps):
        if not isinstance(raw_step, dict):
            continue

        calls = raw_step.get("calls")
        results = raw_step.get("results")
        call_items = calls if isinstance(calls, list) else []
        result_items = results if isinstance(results, list) else []
        observation = _observation_from_step(raw_step, base_dir, trace_id, source_step_index)

        if not call_items:
            steps.append(
                Step(
                    step_id=str(len(steps) + 1),
                    observation=observation,
                    model_input=None,
                    action=None,
                    execution=None,
                    post_state=_post_state(None, source_step_index, None),
                )
            )
            continue

        aligned_results = len(call_items) == len(result_items)
        for source_call_index, raw_call in enumerate(call_items):
            result = result_items[source_call_index] if aligned_results else None
            steps.append(
                Step(
                    step_id=str(len(steps) + 1),
                    observation=observation,
                    model_input=None,
                    action=_action_from_call(raw_call, trace_id, source_step_index, source_call_index),
                    execution=_execution_from_result(result, benchmark),
                    post_state=_post_state(
                        _next_observation(raw_steps, source_step_index, base_dir, trace_id)
                        if source_call_index == len(call_items) - 1
                        else None,
                        source_step_index,
                        source_call_index,
                    ),
                )
            )

    return steps


def _action_from_call(
    raw_call: Any,
    trace_id: str,
    source_step_index: int,
    source_call_index: int,
) -> Action:
    if isinstance(raw_call, dict):
        raw_name = raw_call.get("name")
        action_name = str(raw_name) if raw_name is not None else "unknown"
        x, y = _coordinates_from_args(raw_call.get("args"))
    else:
        action_name = str(raw_call)
        x, y = None, None

    return Action(
        action_id=f"holo4-{trace_id}-step-{source_step_index}-call-{source_call_index}",
        type=ACTION_TYPE_MAP.get(action_name, action_name),
        x=x,
        y=y,
        target=action_name,
        coordinate_space=None,
        timestamp=None,
    )


def _coordinates_from_args(args: Any) -> tuple[int | float | None, int | float | None]:
    arg_items = args if isinstance(args, list) else [args]
    for arg in arg_items:
        if not isinstance(arg, dict):
            continue
        x = _number_value(arg.get("x"))
        y = _number_value(arg.get("y"))
        if x is not None and y is not None:
            return x, y
        coordinate = arg.get("coordinate")
        if isinstance(coordinate, list) and len(coordinate) >= 2:
            x = _number_value(coordinate[0])
            y = _number_value(coordinate[1])
            if x is not None and y is not None:
                return x, y
    return None, None


def _execution_from_result(result: Any, benchmark: str) -> ExecutionResult | None:
    if result is None:
        return ExecutionResult(status="unknown", error=None, timestamp=None)

    receipt = _execution_receipt(result)
    if receipt is not None:
        exit_code, receipt_text = receipt
        if exit_code != 0:
            return ExecutionResult(
                status="failed",
                error=_truncate_error(f"exit_code {exit_code}: {receipt_text}"),
                timestamp=None,
            )
        return ExecutionResult(status="success", error=None, timestamp=None)

    parsed = _parse_json_string(result)
    if isinstance(parsed, dict):
        error = parsed.get("error")
        if error not in (None, "", False):
            return ExecutionResult(
                status="failed",
                error=_truncate_error(_error_text(error)),
                timestamp=None,
            )

        code = parsed.get("code")
        if _is_automation_bench(benchmark) and isinstance(code, int) and code >= 400:
            return ExecutionResult(
                status="failed",
                error=_truncate_error(_error_text(parsed)),
                timestamp=None,
            )

        if parsed.get("success") is True:
            return ExecutionResult(status="success", error=None, timestamp=None)

    return ExecutionResult(status="unknown", error=None, timestamp=None)


def _execution_receipt(result: Any) -> tuple[int, str] | None:
    if not isinstance(result, str):
        return None
    match = EXECUTION_RECEIPT_RE.search(result)
    if match is None:
        return None
    return int(match.group(1)), result


def _parse_json_string(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or stripped[0] not in "[{":
        return value
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def _observation_from_step(
    raw_step: dict[str, Any],
    base_dir: Path,
    trace_id: str,
    source_step_index: int,
) -> Observation | None:
    image = raw_step.get("image")
    if not isinstance(image, str) or not image:
        return None

    dimensions = _image_dimensions(_resolve_image_path(image, base_dir))
    width, height = dimensions if dimensions is not None else (None, None)
    return Observation(
        observation_id=f"holo4-{trace_id}-step-{source_step_index}",
        image_path=image,
        width=width,
        height=height,
        viewport_width=width,
        viewport_height=height,
        timestamp=None,
    )


def _next_observation(
    raw_steps: list[Any],
    source_step_index: int,
    base_dir: Path,
    trace_id: str,
) -> Observation | None:
    if source_step_index + 1 >= len(raw_steps):
        return None
    next_step = raw_steps[source_step_index + 1]
    if not isinstance(next_step, dict):
        return None
    return _observation_from_step(next_step, base_dir, trace_id, source_step_index + 1)


def _post_state(
    observation: Observation | None,
    source_step_index: int,
    source_call_index: int | None,
) -> PostState:
    metadata: dict[str, Any] = {"source_step": source_step_index}
    if source_call_index is not None:
        metadata["source_call_index"] = source_call_index
    return PostState(observation=observation, state_metadata=metadata, timestamp=None)


def _resolve_image_path(image_path: str, base_dir: Path) -> Path:
    direct = base_dir / image_path
    if direct.is_file():
        return direct

    parts = Path(image_path).parts
    if len(parts) >= 3 and parts[0] == "img":
        candidate = base_dir.parent.parent / image_path
        if candidate.is_file():
            return candidate

    return direct


def _image_dimensions(path: Path) -> tuple[int, int] | None:
    if not path.is_file():
        return None

    with path.open("rb") as handle:
        header = handle.read(64)

    if len(header) >= 24 and header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR":
        return struct.unpack(">II", header[16:24])

    if len(header) >= 30 and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return _webp_dimensions(header)

    return None


def _webp_dimensions(header: bytes) -> tuple[int, int] | None:
    chunk = header[12:16]
    if chunk == b"VP8X" and len(header) >= 30:
        width = int.from_bytes(header[24:27], "little") + 1
        height = int.from_bytes(header[27:30], "little") + 1
        return width, height
    if chunk == b"VP8 " and len(header) >= 30:
        width = struct.unpack("<H", header[26:28])[0] & 0x3FFF
        height = struct.unpack("<H", header[28:30])[0] & 0x3FFF
        return width, height
    if chunk == b"VP8L" and len(header) >= 25:
        bits = int.from_bytes(header[21:25], "little")
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        return width, height
    return None


def _trace_metadata(data: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "source": "holo4",
        "source_format": "Hcompany/trajectories",
    }
    for key in ("benchmark", "task", "success", "score", "run", "runs", "duration_s"):
        if key in data:
            metadata[key] = data[key]
    return metadata


def _task_text(data: dict[str, Any]) -> str | None:
    for key in ("instruction", "task"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _number_value(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _is_automation_bench(benchmark: str) -> bool:
    return benchmark.strip().lower() == "automationbench"


def _error_text(error: Any) -> str:
    if isinstance(error, str):
        return error
    try:
        return json.dumps(error, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(error)


def _truncate_error(error: str) -> str:
    if len(error) <= MAX_ERROR_TEXT_CHARS:
        return error
    return error[: MAX_ERROR_TEXT_CHARS - 3] + "..."


__all__ = ["Holo4Adapter"]
