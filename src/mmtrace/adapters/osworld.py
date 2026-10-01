"""OSWorld trajectory adapter for offline ``traj.jsonl`` exports."""

from __future__ import annotations

import ast
import json
import struct
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from mmtrace.adapters.base import AdapterError, BaseAdapter
from mmtrace.schema.trace import Action, ExecutionResult, Observation, PostState, Step, Trace

ACTION_TYPE_MAP = {
    "click": "click",
    "doubleClick": "click",
    "rightClick": "click",
    "moveTo": "move",
    "dragTo": "drag",
    "write": "type",
    "typewrite": "type",
    "press": "keypress",
    "hotkey": "keypress",
    "scroll": "scroll",
}


class OSWorldAdapter(BaseAdapter):
    """Load OSWorld ``traj.jsonl`` files without requiring OSWorld itself."""

    name = "osworld"

    def can_load(self, path: str | Path) -> bool:
        return Path(path).name == "traj.jsonl" or Path(path).suffix.lower() == ".jsonl"

    def load(self, path: str | Path) -> Trace:
        input_path = Path(path)

        try:
            rows = _read_jsonl(input_path)
            return Trace(
                trace_id=_trace_id(input_path),
                task=_read_optional_text(input_path.with_name("instruction.txt")),
                agent="Qwen3-VL-8B-Thinking",
                metadata=_trace_metadata(input_path),
                steps=_rows_to_steps(rows, input_path.parent),
            )
        except FileNotFoundError as exc:
            raise AdapterError(f"file not found: {input_path}") from exc
        except (OSError, TypeError, ValueError, ValidationError) as exc:
            raise AdapterError(f"failed to load OSWorld trajectory {input_path}: {exc}") from exc


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid JSONL at line {line_number}: {exc.msg}"
                ) from exc
            if not isinstance(row, dict):
                raise ValueError(f"line {line_number} must be a JSON object")
            rows.append(row)
    return rows


def _rows_to_steps(rows: list[dict[str, Any]], base_dir: Path) -> list[Step]:
    steps: list[Step] = []
    last_post_observation = _initial_observation(base_dir)
    active_source_model_step: str | None = None
    active_model_observation: Observation | None = None
    source_action_index = 0

    for row in rows:
        source_model_step = _source_model_step(row)
        if source_model_step != active_source_model_step:
            active_source_model_step = source_model_step
            active_model_observation = last_post_observation
            source_action_index = 0

        action = _action_from_row(row, source_model_step, source_action_index)
        post_observation = _post_observation_from_row(row, base_dir)
        timestamp = _timestamp(row.get("action_timestamp"))

        steps.append(
            Step(
                step_id=str(len(steps) + 1),
                observation=active_model_observation,
                model_input=None,
                action=action,
                execution=ExecutionResult(status="unknown", error=None, timestamp=timestamp),
                post_state=PostState(
                    observation=post_observation,
                    state_metadata={
                        "source_model_step": source_model_step,
                        "source_action_index": source_action_index,
                        "source_screenshot_file": row.get("screenshot_file"),
                        "reward": row.get("reward"),
                        "done": row.get("done"),
                        "info": row.get("info") if isinstance(row.get("info"), dict) else {},
                    },
                    timestamp=timestamp,
                )
                if post_observation is not None
                else None,
            )
        )

        if post_observation is not None:
            last_post_observation = post_observation
        source_action_index += 1

    return steps


def _action_from_row(row: dict[str, Any], source_model_step: str, action_index: int) -> Action:
    raw_action = row.get("action")
    function_name, x, y = _parse_pyautogui_action(raw_action)
    timestamp = _timestamp(row.get("action_timestamp"))

    return Action(
        action_id=f"osworld-step-{source_model_step}-action-{action_index}",
        type=ACTION_TYPE_MAP.get(function_name or "", function_name or "unknown"),
        x=x,
        y=y,
        target=str(raw_action) if raw_action is not None else None,
        coordinate_space="viewport" if x is not None and y is not None else None,
        timestamp=timestamp,
    )


def _parse_pyautogui_action(action: Any) -> tuple[str | None, int | float | None, int | float | None]:
    if not isinstance(action, str):
        return None, None, None

    try:
        node = ast.parse(action.strip(), mode="eval").body
    except SyntaxError:
        return None, None, None

    if not isinstance(node, ast.Call):
        return None, None, None

    function = node.func
    if not (
        isinstance(function, ast.Attribute)
        and isinstance(function.value, ast.Name)
        and function.value.id == "pyautogui"
    ):
        return None, None, None

    x = _numeric_arg(node.args[0]) if len(node.args) >= 1 else None
    y = _numeric_arg(node.args[1]) if len(node.args) >= 2 else None
    for keyword in node.keywords:
        if keyword.arg == "x":
            x = _numeric_arg(keyword.value)
        elif keyword.arg == "y":
            y = _numeric_arg(keyword.value)

    return function.attr, x, y


def _numeric_arg(node: ast.AST) -> int | float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = _numeric_arg(node.operand)
        if value is not None:
            return -value
    return None


def _initial_observation(base_dir: Path) -> Observation | None:
    candidates = sorted(base_dir.glob("step_0_*.png"))
    if not candidates:
        return None
    return _observation_from_screenshot(candidates[0].name, base_dir, "initial")


def _post_observation_from_row(row: dict[str, Any], base_dir: Path) -> Observation | None:
    screenshot_file = row.get("screenshot_file")
    if not isinstance(screenshot_file, str) or not screenshot_file:
        return None
    return _observation_from_screenshot(
        screenshot_file,
        base_dir,
        f"post-{row.get('step_num', 'unknown')}-{row.get('action_timestamp', 'unknown')}",
    )


def _observation_from_screenshot(screenshot_file: str, base_dir: Path, observation_id: str) -> Observation:
    dimensions = _png_dimensions(base_dir / screenshot_file)
    width, height = dimensions if dimensions is not None else (None, None)
    return Observation(
        observation_id=observation_id,
        image_path=screenshot_file,
        width=width,
        height=height,
        viewport_width=width,
        viewport_height=height,
        timestamp=_timestamp_from_screenshot_name(screenshot_file),
    )


def _png_dimensions(path: Path) -> tuple[int, int] | None:
    if not path.is_file():
        return None
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", header[16:24])


def _timestamp_from_screenshot_name(name: str) -> datetime | None:
    stem = Path(name).stem
    parts = stem.split("_")
    if len(parts) < 3:
        return None
    return _timestamp(parts[-1])


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    for fmt in ("%Y%m%d@%H%M%S%f", "%Y%m%d@%H%M%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _source_model_step(row: dict[str, Any]) -> str:
    if row.get("step_num") is not None:
        return str(row["step_num"])
    response = row.get("response")
    if isinstance(response, str) and response:
        return response
    return "unknown"


def _trace_metadata(input_path: Path) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "source": "osworld",
        "source_format": "traj.jsonl",
    }

    result = _read_optional_text(input_path.with_name("result.txt"))
    if result is not None:
        metadata["task_result"] = result

    task_id = input_path.parent.name
    if task_id:
        metadata["task_id"] = task_id
    application = input_path.parent.parent.name
    if application and application != ".":
        metadata["application"] = application

    return metadata


def _read_optional_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None


def _trace_id(path: Path) -> str:
    task_id = path.parent.name
    return f"osworld-{task_id}" if task_id else path.stem


__all__ = ["OSWorldAdapter"]
