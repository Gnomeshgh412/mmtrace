"""Execution-related reliability checks."""

from __future__ import annotations

from mmtrace.checks.base import BaseCheck
from mmtrace.schema.finding import Finding, Severity
from mmtrace.schema.trace import Trace


class ExplicitExecutionFailureCheck(BaseCheck):
    rule_id = "MMTRACE007"
    title = "Explicit Execution Failure"
    description = "Detects actions whose normalized execution result explicitly failed."
    category = "EXECUTION"
    default_severity = Severity.ERROR

    def run(self, trace: Trace) -> list[Finding]:
        findings: list[Finding] = []

        for step in trace.steps:
            if step.action is None or step.execution is None:
                continue
            if not _is_failed_status(step.execution.status):
                continue

            evidence = {
                "execution_status": step.execution.status,
                "action_type": step.action.type,
            }
            if step.execution.error:
                evidence["error"] = step.execution.error

            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    severity=self.default_severity,
                    step_id=step.step_id,
                    title=self.title,
                    evidence=evidence,
                    explanation=(
                        "The recorded executor or tool explicitly reported that "
                        "this action failed."
                    ),
                    suggestion=(
                        "Inspect the executor/tool error and verify whether the "
                        "agent recovered or retried with valid state."
                    ),
                )
            )

        return findings


def _is_failed_status(status: str | None) -> bool:
    return status is not None and status.strip().lower() == "failed"


__all__ = ["ExplicitExecutionFailureCheck"]
