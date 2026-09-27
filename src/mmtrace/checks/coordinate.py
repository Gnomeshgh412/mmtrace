"""Coordinate-related reliability checks."""

from __future__ import annotations

from typing import Any

from mmtrace.checks.base import BaseCheck
from mmtrace.schema.finding import Finding, Severity
from mmtrace.schema.trace import Observation, Trace

COORDINATE_ACTION_TYPES = {"click", "move", "drag"}
COORDINATE_SPACE_KEYS = (
    "expected_coordinate_space",
    "executor_coordinate_space",
    "required_coordinate_space",
)
TRANSFORM_KEYS = (
    "coordinate_transform",
    "coordinate_space_transform",
    "transform",
    "scaling",
    "scale",
)


class CoordinateOutOfFrameCheck(BaseCheck):
    rule_id = "MMTRACE003"
    title = "Coordinate Out Of Frame"
    description = "Detects explicit action coordinates that fall outside the target frame."
    category = "COORDINATE"
    default_severity = Severity.ERROR

    def run(self, trace: Trace) -> list[Finding]:
        findings: list[Finding] = []

        for step in trace.steps:
            if step.action is None or not _is_coordinate_action(step.action.type):
                continue
            if step.action.x is None or step.action.y is None:
                continue

            frame = _resolve_frame(step.observation, step.action.coordinate_space)
            if frame is None:
                continue

            frame_width, frame_height = frame
            x = step.action.x
            y = step.action.y
            if 0 <= x < frame_width and 0 <= y < frame_height:
                continue

            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    severity=self.default_severity,
                    step_id=step.step_id,
                    title=self.title,
                    evidence={
                        "x": x,
                        "y": y,
                        "frame_width": frame_width,
                        "frame_height": frame_height,
                        "coordinate_space": step.action.coordinate_space,
                    },
                    explanation=(
                        "This action uses explicit coordinates that fall outside "
                        "the applicable observation frame."
                    ),
                    suggestion=(
                        "Check coordinate generation, frame dimensions, and "
                        "coordinate-space binding before executing the action."
                    ),
                )
            )

        return findings


class CoordinateSpaceMismatchCheck(BaseCheck):
    rule_id = "MMTRACE004"
    title = "Coordinate Space Mismatch"
    description = "Detects explicit coordinate-space conflicts when metadata states the expected space."
    category = "COORDINATE"
    default_severity = Severity.ERROR

    def run(self, trace: Trace) -> list[Finding]:
        findings: list[Finding] = []

        for step in trace.steps:
            if (
                step.action is None
                or step.action.x is None
                or step.action.y is None
                or not step.action.coordinate_space
                or step.observation is None
                or not _has_coordinate_information(step.observation)
            ):
                continue

            expected_coordinate_space = _expected_coordinate_space(trace, step)
            if not expected_coordinate_space:
                continue

            available_transform = _available_transform(trace, step)
            if available_transform is not None:
                continue

            if _normalize_space(step.action.coordinate_space) == _normalize_space(expected_coordinate_space):
                continue

            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    severity=self.default_severity,
                    step_id=step.step_id,
                    title=self.title,
                    evidence={
                        "action_coordinate_space": step.action.coordinate_space,
                        "expected_coordinate_space": expected_coordinate_space,
                        "available_transform": available_transform,
                    },
                    explanation=(
                        "This action uses explicit coordinates in a coordinate "
                        "space that conflicts with the expected executor or "
                        "observation coordinate space, and no transform metadata "
                        "is available."
                    ),
                    suggestion=(
                        "Record the expected coordinate space consistently or "
                        "provide explicit transform/scaling metadata."
                    ),
                )
            )

        return findings


def _is_coordinate_action(action_type: str | None) -> bool:
    return action_type is not None and action_type.lower() in COORDINATE_ACTION_TYPES


def _resolve_frame(
    observation: Observation | None,
    coordinate_space: str | None,
) -> tuple[int, int] | None:
    if observation is None or coordinate_space is None:
        return None

    normalized_space = _normalize_space(coordinate_space)
    if normalized_space == "viewport":
        if observation.viewport_width is None or observation.viewport_height is None:
            return None
        return observation.viewport_width, observation.viewport_height

    if normalized_space in {"image", "frame"}:
        if observation.width is None or observation.height is None:
            return None
        return observation.width, observation.height

    return None


def _has_coordinate_information(observation: Observation) -> bool:
    return (
        observation.width is not None
        and observation.height is not None
        or observation.viewport_width is not None
        and observation.viewport_height is not None
    )


def _expected_coordinate_space(trace: Trace, step: Any) -> str | None:
    for metadata in _metadata_sources(trace, step):
        for key in COORDINATE_SPACE_KEYS:
            value = metadata.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _available_transform(trace: Trace, step: Any) -> Any:
    for metadata in _metadata_sources(trace, step):
        for key in TRANSFORM_KEYS:
            if key in metadata and metadata[key] is not None:
                return metadata[key]
    return None


def _metadata_sources(trace: Trace, step: Any) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []

    if trace.metadata:
        sources.append(trace.metadata)
    if step.post_state is not None and step.post_state.state_metadata:
        sources.append(step.post_state.state_metadata)

    return sources


def _normalize_space(space: str) -> str:
    return space.strip().lower().replace("-", "_")


__all__ = ["CoordinateOutOfFrameCheck", "CoordinateSpaceMismatchCheck"]

