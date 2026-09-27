"""Post-action verification checks."""

from __future__ import annotations

from mmtrace.checks.base import BaseCheck
from mmtrace.schema.finding import Finding, Severity
from mmtrace.schema.trace import Trace

STATE_CHANGING_ACTION_TYPES = {"click", "type", "drag", "keypress", "navigation"}
SUCCESS_STATUSES = {"success", "succeeded", "ok", "passed"}


class MissingPostActionVerificationCheck(BaseCheck):
    rule_id = "MMTRACE006"
    title = "Missing Post-Action Verification"
    description = "Detects successful state-changing actions without post-action state evidence."
    category = "STATE"
    default_severity = Severity.WARNING

    def run(self, trace: Trace) -> list[Finding]:
        findings: list[Finding] = []

        for step in trace.steps:
            if step.action is None or step.execution is None:
                continue
            if not _is_state_changing_action(step.action.type):
                continue
            if not _is_success_status(step.execution.status):
                continue
            if step.post_state is not None:
                continue

            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    severity=self.default_severity,
                    step_id=step.step_id,
                    title=self.title,
                    evidence={
                        "action_type": step.action.type,
                        "execution_status": step.execution.status,
                        "has_post_state": False,
                    },
                    explanation=(
                        "This action is recorded as successful, but the step has "
                        "no post-action state verification evidence."
                    ),
                    suggestion=(
                        "Capture post-action state, such as a screenshot, URL, "
                        "window title, or state metadata, after successful actions."
                    ),
                )
            )

        return findings


def _is_state_changing_action(action_type: str | None) -> bool:
    return action_type is not None and action_type.lower() in STATE_CHANGING_ACTION_TYPES


def _is_success_status(status: str | None) -> bool:
    return status is not None and status.lower() in SUCCESS_STATUSES


__all__ = ["MissingPostActionVerificationCheck"]
