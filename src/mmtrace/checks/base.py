"""Base abstraction for MMTrace checks."""

from __future__ import annotations

from abc import ABC, abstractmethod

from mmtrace.schema.finding import Finding, Severity
from mmtrace.schema.trace import Trace


class BaseCheck(ABC):
    """Minimal interface implemented by independent trace checks."""

    rule_id: str
    title: str
    description: str
    category: str
    default_severity: Severity

    @abstractmethod
    def run(self, trace: Trace) -> list[Finding]:
        """Inspect a trace and return findings without mutating it."""

