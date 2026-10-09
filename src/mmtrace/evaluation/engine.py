"""Rule evaluability aggregation engine."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Sequence

from mmtrace.checks.base import BaseCheck
from mmtrace.engine import DEFAULT_CHECKS
from mmtrace.evaluation.models import (
    EvaluationCoverage,
    EvaluationOutcome,
    MissingEvidence,
    RuleEvaluation,
)
from mmtrace.evaluation.rules import evaluate_unit
from mmtrace.schema.finding import Finding, Severity
from mmtrace.schema.trace import Trace


class EvaluationEngine:
    """Evaluates rule applicability, evidence coverage, and outcomes."""

    def __init__(self, checks: Sequence[BaseCheck] | None = None) -> None:
        self.checks = list(checks) if checks is not None else list(DEFAULT_CHECKS)

    def evaluate(self, trace: Trace, findings: Sequence[Finding]) -> list[RuleEvaluation]:
        findings_by_rule: dict[str, list[Finding]] = {}
        for finding in findings:
            findings_by_rule.setdefault(finding.rule_id, []).append(finding)

        evaluations: list[RuleEvaluation] = []
        for check in self.checks:
            evaluations.append(
                _evaluate_rule(trace, check.rule_id, findings_by_rule.get(check.rule_id, []))
            )
        return evaluations


def evaluate_trace(trace: Trace, findings: Sequence[Finding]) -> list[RuleEvaluation]:
    return EvaluationEngine().evaluate(trace, findings)


def _evaluate_rule(
    trace: Trace,
    rule_id: str,
    findings: Sequence[Finding],
) -> RuleEvaluation:
    applicable_units = 0
    evaluable_units = 0
    missing_by_code: OrderedDict[str, tuple[int, list[str]]] = OrderedDict()

    for index, step in enumerate(trace.steps):
        unit = evaluate_unit(rule_id, trace, step)
        if not unit.applicable:
            continue
        applicable_units += 1
        if unit.evaluable:
            evaluable_units += 1
            continue

        step_id = step.step_id or str(index)
        for code in unit.missing_evidence:
            count, step_ids = missing_by_code.get(code, (0, []))
            missing_by_code[code] = (count + 1, [*step_ids, step_id])

    not_evaluable_units = applicable_units - evaluable_units
    return RuleEvaluation(
        rule_id=rule_id,
        coverage=_coverage(applicable_units, evaluable_units),
        outcome=_outcome(findings, evaluable_units),
        applicable_units=applicable_units,
        evaluable_units=evaluable_units,
        not_evaluable_units=not_evaluable_units,
        finding_count=len(findings),
        missing_evidence=[
            MissingEvidence(code=code, count=count, step_ids=step_ids)
            for code, (count, step_ids) in missing_by_code.items()
        ],
    )


def _coverage(applicable_units: int, evaluable_units: int) -> EvaluationCoverage:
    if applicable_units == 0:
        return EvaluationCoverage.NOT_APPLICABLE
    if evaluable_units == 0:
        return EvaluationCoverage.NOT_EVALUABLE
    if evaluable_units < applicable_units:
        return EvaluationCoverage.PARTIAL
    return EvaluationCoverage.FULL


def _outcome(findings: Sequence[Finding], evaluable_units: int) -> EvaluationOutcome:
    if any(finding.severity is Severity.ERROR for finding in findings):
        return EvaluationOutcome.ERROR
    if any(finding.severity is Severity.WARNING for finding in findings):
        return EvaluationOutcome.WARNING
    if evaluable_units > 0:
        return EvaluationOutcome.PASS
    return EvaluationOutcome.NONE


__all__ = ["EvaluationEngine", "evaluate_trace"]
