"""Observation-related reliability checks."""

from __future__ import annotations

from datetime import datetime

from mmtrace.checks.base import BaseCheck
from mmtrace.schema.finding import Finding, Severity
from mmtrace.schema.trace import Observation, Trace

OBSERVATION_REQUIRED_ACTION_TYPES = {"click", "drag", "move"}


class MissingObservationCheck(BaseCheck):
    rule_id = "MMTRACE001"
    title = "Missing Observation"
    description = (
        "Detects steps that contain a model decision or action without the "
        "corresponding visual observation."
    )
    category = "OBSERVATION"
    default_severity = Severity.ERROR

    def run(self, trace: Trace) -> list[Finding]:
        findings: list[Finding] = []

        for step in trace.steps:
            has_observation = step.observation is not None
            has_model_input = step.model_input is not None
            has_action = step.action is not None

            if has_observation or not has_action:
                continue

            action_type = step.action.type
            if not _requires_current_observation(action_type):
                continue

            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    severity=self.default_severity,
                    step_id=step.step_id,
                    title=self.title,
                    evidence={
                        "has_observation": has_observation,
                        "has_model_input": has_model_input,
                        "has_action": has_action,
                        "action_type": action_type,
                    },
                    explanation=(
                        "This step contains an action that requires current "
                        "environment observation, but the corresponding visual "
                        "Observation is missing. The step's multimodal execution "
                        "evidence is incomplete."
                    ),
                    suggestion=(
                        "Check screenshot capture, trace recording, or "
                        "observation-to-step binding for this step."
                    ),
                )
            )

        return findings


def _requires_current_observation(action_type: str | None) -> bool:
    if action_type is None:
        return False
    return action_type.strip().lower() in OBSERVATION_REQUIRED_ACTION_TYPES


class ObservationNotInModelContextCheck(BaseCheck):
    rule_id = "MMTRACE002"
    title = "Observation Not In Model Context"
    description = (
        "Detects steps where an observation was captured but was not referenced "
        "by the model input for that step."
    )
    category = "OBSERVATION"
    default_severity = Severity.ERROR

    def run(self, trace: Trace) -> list[Finding]:
        findings: list[Finding] = []

        for step in trace.steps:
            if step.observation is None or step.model_input is None:
                continue

            observation_id = step.observation.observation_id
            if not observation_id:
                continue

            model_observation_ids = step.model_input.observation_ids
            if observation_id in model_observation_ids:
                continue

            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    severity=self.default_severity,
                    step_id=step.step_id,
                    title=self.title,
                    evidence={
                        "observation_id": observation_id,
                        "model_call_id": step.model_input.model_call_id,
                        "model_observation_ids": model_observation_ids,
                    },
                    explanation=(
                        "This step has a captured Observation, but that "
                        "observation is not referenced by the model input. The "
                        "model decision may not be grounded in the captured "
                        "visual state."
                    ),
                    suggestion=(
                        "Check model input construction and observation-to-model "
                        "context binding for this step."
                    ),
                )
            )

        return findings


class StaleObservationCheck(BaseCheck):
    rule_id = "MMTRACE005"
    title = "Stale Observation"
    description = (
        "Detects actions that use an observation even though a newer environment "
        "observation is available before the action executes."
    )
    category = "OBSERVATION"
    default_severity = Severity.WARNING

    def run(self, trace: Trace) -> list[Finding]:
        findings: list[Finding] = []
        observations = _collect_observations(trace)

        for step in trace.steps:
            if step.observation is None or step.action is None:
                continue

            used_observation = step.observation
            if (
                not used_observation.observation_id
                or used_observation.timestamp is None
                or step.action.timestamp is None
            ):
                continue

            newer_observation = _find_newer_observation(
                observations=observations,
                used_observation=used_observation,
                action_timestamp=step.action.timestamp,
            )
            if newer_observation is None:
                continue

            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    severity=self.default_severity,
                    step_id=step.step_id,
                    title=self.title,
                    evidence={
                        "used_observation_id": used_observation.observation_id,
                        "used_observation_timestamp": used_observation.timestamp.isoformat(),
                        "newer_observation_id": newer_observation.observation_id,
                        "newer_observation_timestamp": newer_observation.timestamp.isoformat(),
                        "action_timestamp": step.action.timestamp.isoformat(),
                    },
                    explanation=(
                        "This action uses an observation, but a newer environment "
                        "Observation exists before the action timestamp. The action "
                        "may be grounded in stale visual evidence."
                    ),
                    suggestion=(
                        "Check observation selection, trace ordering, and action "
                        "binding so actions use the latest applicable observation."
                    ),
                )
            )

        return findings


def _collect_observations(trace: Trace) -> list[Observation]:
    observations: list[Observation] = []

    for step in trace.steps:
        if step.observation is not None:
            observations.append(step.observation)
        if step.post_state is not None and step.post_state.observation is not None:
            observations.append(step.post_state.observation)

    return observations


def _find_newer_observation(
    observations: list[Observation],
    used_observation: Observation,
    action_timestamp: datetime,
) -> Observation | None:
    candidates = [
        observation
        for observation in observations
        if observation.observation_id
        and observation.observation_id != used_observation.observation_id
        and observation.timestamp is not None
        and used_observation.timestamp is not None
        and used_observation.timestamp < observation.timestamp < action_timestamp
    ]

    if not candidates:
        return None

    return min(candidates, key=lambda observation: observation.timestamp or action_timestamp)


__all__ = [
    "MissingObservationCheck",
    "ObservationNotInModelContextCheck",
    "StaleObservationCheck",
]
