"""Per-rule evaluability specifications for built-in MMTrace checks."""

from __future__ import annotations

from dataclasses import dataclass, field

from mmtrace.checks.coordinate import (
    _expected_coordinate_space,
    _has_coordinate_information,
    _is_coordinate_action,
    _resolve_frame,
)
from mmtrace.checks.execution import _is_failed_status
from mmtrace.checks.observation import (
    _requires_current_observation,
)
from mmtrace.checks.verification import (
    _is_state_changing_action,
    _is_success_status,
)
from mmtrace.schema.trace import Step, Trace


@dataclass(frozen=True)
class UnitEvaluation:
    applicable: bool
    evaluable: bool
    missing_evidence: tuple[str, ...] = field(default_factory=tuple)


def evaluate_unit(rule_id: str, trace: Trace, step: Step) -> UnitEvaluation:
    if rule_id == "MMTRACE001":
        return _evaluate_mmtrace001(step)
    if rule_id == "MMTRACE002":
        return _evaluate_mmtrace002(step)
    if rule_id == "MMTRACE003":
        return _evaluate_mmtrace003(step)
    if rule_id == "MMTRACE004":
        return _evaluate_mmtrace004(trace, step)
    if rule_id == "MMTRACE005":
        return _evaluate_mmtrace005(trace, step)
    if rule_id == "MMTRACE006":
        return _evaluate_mmtrace006(step)
    if rule_id == "MMTRACE007":
        return _evaluate_mmtrace007(step)
    raise ValueError(f"unsupported rule ID: {rule_id}")


def _evaluate_mmtrace001(step: Step) -> UnitEvaluation:
    if step.action is None or not _requires_current_observation(step.action.type):
        return _not_applicable()
    return _evaluable()


def _evaluate_mmtrace002(step: Step) -> UnitEvaluation:
    if step.observation is None:
        return _not_applicable()
    missing = []
    if not step.observation.observation_id:
        missing.append("observation.id")
    if step.model_input is None:
        missing.append("model_input")
    if missing:
        return _not_evaluable(*missing)
    return _evaluable()


def _evaluate_mmtrace003(step: Step) -> UnitEvaluation:
    if step.action is None or not _is_coordinate_action(step.action.type):
        return _not_applicable()
    if step.action.x is None or step.action.y is None:
        return _not_evaluable("action.coordinates")
    if _resolve_frame(step.observation, step.action.coordinate_space) is None:
        return _not_evaluable("observation.frame_dimensions")
    return _evaluable()


def _evaluate_mmtrace004(trace: Trace, step: Step) -> UnitEvaluation:
    if step.action is None or not _is_coordinate_action(step.action.type):
        return _not_applicable()
    if step.action.x is None or step.action.y is None:
        return _not_applicable()
    if not step.action.coordinate_space:
        return _not_evaluable("action.coordinate_space")
    if step.observation is None or not _has_coordinate_information(step.observation):
        return _not_evaluable("observation.frame_dimensions")
    if _expected_coordinate_space(trace, step) is None:
        return _not_evaluable("executor.coordinate_space")
    return _evaluable()


def _evaluate_mmtrace005(trace: Trace, step: Step) -> UnitEvaluation:
    if step.observation is None or step.action is None:
        return _not_applicable()
    missing = []
    if not step.observation.observation_id:
        missing.append("observation")
    if step.observation.timestamp is None:
        missing.append("observation.timestamp")
    if step.action.timestamp is None:
        missing.append("action.timestamp")
    if missing:
        return _not_evaluable(*missing)
    return _evaluable()


def _evaluate_mmtrace006(step: Step) -> UnitEvaluation:
    if step.action is None or not _is_state_changing_action(step.action.type):
        return _not_applicable()
    if step.execution is None:
        return _not_evaluable("execution")
    if _is_failed_status(step.execution.status):
        return _not_applicable()
    if not _is_success_status(step.execution.status):
        return _not_evaluable("execution.status")
    return _evaluable()


def _evaluate_mmtrace007(step: Step) -> UnitEvaluation:
    if step.action is None:
        return _not_applicable()
    if step.execution is None:
        return _not_evaluable("execution")
    if _is_failed_status(step.execution.status) or _is_success_status(step.execution.status):
        return _evaluable()
    return _not_evaluable("execution.status")


def _evaluable() -> UnitEvaluation:
    return UnitEvaluation(applicable=True, evaluable=True)


def _not_evaluable(*codes: str) -> UnitEvaluation:
    return UnitEvaluation(applicable=True, evaluable=False, missing_evidence=tuple(dict.fromkeys(codes)))


def _not_applicable() -> UnitEvaluation:
    return UnitEvaluation(applicable=False, evaluable=False)


__all__ = ["UnitEvaluation", "evaluate_unit"]
