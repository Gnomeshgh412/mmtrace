"""Browser Use history adapter for offline AgentHistoryList JSON exports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from mmtrace.adapters.base import AdapterError, BaseAdapter
from mmtrace.schema.trace import (
    Action,
    ExecutionResult,
    Observation,
    PostState,
    Step,
    Trace,
)


class BrowserUseAdapter(BaseAdapter):
    name = "browser-use"

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

        try:
            history = _extract_history(data)
            return Trace(
                trace_id=_trace_id(input_path),
                task=_extract_task(data),
                agent="browser-use",
                metadata=_trace_metadata(data, history),
                steps=_history_to_steps(history),
            )
        except (TypeError, ValueError, ValidationError) as exc:
            raise AdapterError(f"failed to load Browser Use history {input_path}: {exc}") from exc


def _extract_history(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        history = data
    elif isinstance(data, dict) and isinstance(data.get("history"), list):
        history = data["history"]
    else:
        raise ValueError("expected a Browser Use history list or an object with a history list")

    if not all(isinstance(item, dict) for item in history):
        raise ValueError("each Browser Use history item must be an object")

    return history


def _history_to_steps(history: list[dict[str, Any]]) -> list[Step]:
    steps: list[Step] = []
    next_step_id = 1

    for source_index, item in enumerate(history):
        source_step = _source_step_number(item, source_index)
        actions = _extract_actions(item)
        results = _extract_results(item)
        observation = _observation_from_state(item.get("state"), source_step)
        next_state = history[source_index + 1].get("state") if source_index + 1 < len(history) else None

        if not actions:
            steps.append(
                Step(
                    step_id=str(next_step_id),
                    observation=observation,
                    model_input=None,
                    action=None,
                    execution=None,
                    post_state=None,
                )
            )
            next_step_id += 1
            continue

        for action_index, raw_action in enumerate(actions):
            is_last_action = action_index == len(actions) - 1
            steps.append(
                Step(
                    step_id=str(next_step_id),
                    observation=observation,
                    model_input=None,
                    action=_action_from_browser_use(raw_action, source_step, action_index),
                    execution=_execution_from_result(
                        _matching_result(results, len(actions), action_index)
                    ),
                    post_state=(
                        _post_state_from_state(next_state, _source_step_number(history[source_index + 1], source_index + 1))
                        if is_last_action and next_state is not None
                        else None
                    ),
                )
            )
            next_step_id += 1

    return steps


def _extract_actions(item: dict[str, Any]) -> list[Any]:
    model_output = item.get("model_output")
    if not isinstance(model_output, dict):
        return []

    actions = model_output.get("action")
    if isinstance(actions, list):
        return actions
    if actions is None:
        return []
    return [actions]


def _extract_results(item: dict[str, Any]) -> list[dict[str, Any]]:
    results = item.get("result")
    if not isinstance(results, list):
        return []
    return [result for result in results if isinstance(result, dict)]


def _action_from_browser_use(raw_action: Any, source_step: str, action_index: int) -> Action:
    action_name, params = _action_name_and_params(raw_action)

    x = _number_value(params.get("coordinate_x"))
    y = _number_value(params.get("coordinate_y"))
    coordinate_space = "viewport" if x is not None and y is not None else None

    return Action(
        action_id=f"browser-use-step-{source_step}-action-{action_index}",
        type=action_name,
        x=x,
        y=y,
        target=_target_from_params(params),
        coordinate_space=coordinate_space,
        timestamp=None,
    )


def _action_name_and_params(raw_action: Any) -> tuple[str | None, dict[str, Any]]:
    if not isinstance(raw_action, dict):
        return str(raw_action), {}

    if isinstance(raw_action.get("type"), str):
        return raw_action["type"], raw_action
    if isinstance(raw_action.get("name"), str):
        return raw_action["name"], raw_action

    if len(raw_action) == 1:
        name, params = next(iter(raw_action.items()))
        return str(name), params if isinstance(params, dict) else {}

    for key, value in raw_action.items():
        if isinstance(value, dict):
            return str(key), value

    return None, raw_action


def _matching_result(
    results: list[dict[str, Any]],
    action_count: int,
    action_index: int,
) -> dict[str, Any] | None:
    if len(results) == action_count:
        return results[action_index]

    for result in results:
        explicit_index = result.get("action_index", result.get("action_idx"))
        if explicit_index == action_index:
            return result

    return None


def _execution_from_result(result: dict[str, Any] | None) -> ExecutionResult | None:
    if result is None:
        return None

    error = result.get("error")
    if error:
        return ExecutionResult(status="failed", error=str(error), timestamp=None)

    if result.get("success") is True:
        return ExecutionResult(status="success", error=None, timestamp=None)

    return ExecutionResult(status="unknown", error=None, timestamp=None)


def _observation_from_state(state: Any, source_step: str) -> Observation | None:
    if not isinstance(state, dict):
        return None

    screenshot_path = state.get("screenshot_path")
    if not screenshot_path:
        return None

    return Observation(
        observation_id=f"browser-use-step-{source_step}",
        image_path=str(screenshot_path),
        width=_optional_int(state.get("width")),
        height=_optional_int(state.get("height")),
        viewport_width=_optional_int(state.get("viewport_width")),
        viewport_height=_optional_int(state.get("viewport_height")),
        timestamp=None,
    )


def _post_state_from_state(state: Any, source_step: str) -> PostState | None:
    if not isinstance(state, dict):
        return None

    return PostState(
        observation=_observation_from_state(state, source_step),
        url=str(state["url"]) if state.get("url") is not None else None,
        window_title=str(state["title"]) if state.get("title") is not None else None,
        state_metadata=_state_metadata(state),
        timestamp=None,
    )


def _state_metadata(state: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key in ("tabs", "interacted_element"):
        if key in state:
            metadata[key] = state[key]
    return metadata


def _trace_metadata(data: Any, history: list[dict[str, Any]]) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "source": "browser-use",
        "source_format": "AgentHistoryList",
    }

    if isinstance(data, dict):
        for key in ("source_version", "browser_use_version", "version"):
            if data.get(key) is not None:
                metadata["source_version"] = data[key]
                break

    source_steps = []
    for source_index, item in enumerate(history):
        item_metadata = item.get("metadata")
        if isinstance(item_metadata, dict):
            source_steps.append(
                {
                    "source_step": _source_step_number(item, source_index),
                    "metadata": item_metadata,
                }
            )
    if source_steps:
        metadata["browser_use_steps"] = source_steps

    return metadata


def _extract_task(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None

    for key in ("task", "query", "instruction"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value

    return None


def _trace_id(path: Path) -> str:
    return path.stem


def _source_step_number(item: dict[str, Any], source_index: int) -> str:
    metadata = item.get("metadata")
    if isinstance(metadata, dict) and metadata.get("step_number") is not None:
        return str(metadata["step_number"])
    return str(source_index + 1)


def _number_value(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return value
    return None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _target_from_params(params: dict[str, Any]) -> str | None:
    for key in ("index", "text", "url", "target"):
        value = params.get(key)
        if value is not None:
            return str(value)
    return None


__all__ = ["BrowserUseAdapter"]
