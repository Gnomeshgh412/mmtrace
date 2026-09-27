"""Minimal MMTrace check execution engine."""

from __future__ import annotations

from collections.abc import Sequence

from mmtrace.checks.base import BaseCheck
from mmtrace.checks.coordinate import (
    CoordinateOutOfFrameCheck,
    CoordinateSpaceMismatchCheck,
)
from mmtrace.checks.observation import (
    MissingObservationCheck,
    ObservationNotInModelContextCheck,
    StaleObservationCheck,
)
from mmtrace.checks.verification import MissingPostActionVerificationCheck
from mmtrace.schema.finding import Finding, Report
from mmtrace.schema.trace import Trace


DEFAULT_CHECKS: tuple[BaseCheck, ...] = (
    MissingObservationCheck(),
    ObservationNotInModelContextCheck(),
    CoordinateOutOfFrameCheck(),
    CoordinateSpaceMismatchCheck(),
    StaleObservationCheck(),
    MissingPostActionVerificationCheck(),
)


class CheckEngine:
    """Runs a fixed list of checks against a trace."""

    def __init__(self, checks: Sequence[BaseCheck] | None = None) -> None:
        self.checks = list(checks) if checks is not None else list(DEFAULT_CHECKS)

    def run(self, trace: Trace) -> Report:
        findings: list[Finding] = []

        for check in self.checks:
            findings.extend(check.run(trace))

        return Report.from_findings(trace_id=trace.trace_id or "", findings=findings)


__all__ = ["CheckEngine", "DEFAULT_CHECKS"]
